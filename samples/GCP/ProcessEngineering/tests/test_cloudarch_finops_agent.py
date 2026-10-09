import json
import unittest
from unittest.mock import patch

from test_grounding_agent import _install_dependency_stubs

_install_dependency_stubs()
from process_agents.common import utils  # noqa: E402
from process_agents.cloudarch import cloudarch_finops_agent as finops  # noqa: E402
from process_agents.cloudarch import pricing  # noqa: E402


# Mirrors test_cloudarch_simulation_agent.py's own fixture shape/style.
# node_ec2's value embeds real <b>/<br/>/<font> tags (escaped as XML
# entities in the source, as a real drawio file would have them, and
# un-escaped back to real tags by the time parse_drawio_graph reads
# `value` via ElementTree) -- exercising _split_label_and_bullets'
# HTML-stripping against the exact shape cloudarch_layout_agent.py's own
# _html_value produces. "m5.xlarge" in the bullet should trip the size
# multiplier; the EC2 node has no autoscaling/reserved-capacity keywords
# anywhere in the diagram, so both of those recommendations should fire
# too. node_s3 has no edges at all (orphaned). node_mystery uses a shape
# slug that matches neither the direct pricing table nor any category
# keyword, to exercise the unclassified path.
_SAMPLE_XML = """
<mxfile host="app.diagrams.net">
  <diagram id="d1" name="Page-1">
    <mxGraphModel dx="800" dy="600">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="box_layout" value="Layout Box" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F9FAFB;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="100" height="60" as="geometry" />
        </mxCell>
        <mxCell id="node_ec2" value="&lt;b&gt;Web Server&lt;/b&gt;&lt;br/&gt;&lt;font style=&quot;font-size:10px;color:#5f6368&quot;&gt;m5.xlarge&lt;/font&gt;" style="sketch=0;shape=mxgraph.aws4.ec2;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="node_lambda" value="&lt;b&gt;Image Resizer&lt;/b&gt;" style="sketch=0;shape=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="node_s3" value="&lt;b&gt;Archive Bucket&lt;/b&gt;" style="sketch=0;shape=mxgraph.aws4.s3;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="node_mystery" value="&lt;b&gt;Mystery Box&lt;/b&gt;" style="sketch=0;shape=mxgraph.aws4.some_made_up_future_service;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="edge_ec2_lambda" value="invokes" style="edgeStyle=orthogonalEdgeStyle;" edge="1" parent="1" source="node_ec2" target="node_lambda">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


def _fixture_graph():
    return utils.parse_drawio_graph(_SAMPLE_XML)


class SplitLabelAndBulletsTests(unittest.TestCase):
    def test_strips_html_and_separates_label_from_bullets(self):
        graph = _fixture_graph()
        node_ec2 = next(v for v in graph["vertices"] if v["id"] == "node_ec2")
        label, bullets = finops._split_label_and_bullets(node_ec2["value"])
        self.assertEqual(label, "Web Server")
        self.assertEqual(bullets, ["m5.xlarge"])

    def test_no_bullets_returns_empty_list(self):
        graph = _fixture_graph()
        node_lambda = next(v for v in graph["vertices"] if v["id"] == "node_lambda")
        label, bullets = finops._split_label_and_bullets(node_lambda["value"])
        self.assertEqual(label, "Image Resizer")
        self.assertEqual(bullets, [])


class ClassifyComponentTests(unittest.TestCase):
    def test_direct_table_match(self):
        category, cost, confidence = finops._classify_component("ec2", "ec2 web server")
        self.assertEqual(category, "compute")
        self.assertEqual(cost, 70.0)
        self.assertEqual(confidence, "direct")

    def test_category_keyword_fallback_for_an_uncatalogued_slug(self):
        # "aurora_instance" isn't in the direct table, but contains "aurora"
        # which is a database keyword.
        category, cost, confidence = finops._classify_component(
            "aurora_instance", "aurora_instance primary cluster"
        )
        self.assertEqual(category, "database")
        self.assertEqual(cost, finops._CATEGORY_DEFAULT_USD_PER_MONTH["database"])
        self.assertEqual(confidence, "category")

    def test_unclassified_when_nothing_matches(self):
        category, cost, confidence = finops._classify_component(
            "some_made_up_future_service", "some_made_up_future_service mystery box"
        )
        self.assertIsNone(category)
        self.assertEqual(cost, 0.0)
        self.assertEqual(confidence, "unclassified")


class SizeMultiplierTests(unittest.TestCase):
    def test_xlarge_doubles_cost(self):
        self.assertEqual(finops._size_multiplier("ec2 web server m5.xlarge"), 2.0)

    def test_2xlarge_quadruples_cost_not_xlarge_rate(self):
        # "2xlarge" contains "xlarge" as a substring -- the biggest-tier
        # rule must win, not whichever rule happens to be checked first.
        self.assertEqual(finops._size_multiplier("ec2 web server m5.2xlarge"), 4.0)

    def test_small_discounts_cost(self):
        self.assertEqual(finops._size_multiplier("ec2 web server t3.small"), 0.4)

    def test_no_keyword_is_baseline(self):
        self.assertEqual(finops._size_multiplier("ec2 web server"), 1.0)


class EstimateCloudarchFinopsTests(unittest.TestCase):
    def test_no_diagram_available(self):
        with patch.object(finops, "load_drawio", return_value={"status": "NOT_FOUND", "xml": None}):
            result = json.loads(finops.estimate_cloudarch_finops())
        self.assertEqual(result["error"], "no_diagram_available")

    def test_full_estimate_against_the_fixture_diagram(self):
        result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))

        self.assertNotIn("error", result)
        self.assertEqual(result["component_count"], 4)

        components_by_id = {c["id"]: c for c in result["cost_estimate"]["components"]}

        # EC2 is a direct match (compute, $70 base) with an xlarge bullet -> 2x multiplier.
        self.assertEqual(components_by_id["node_ec2"]["category"], "compute")
        self.assertEqual(components_by_id["node_ec2"]["confidence"], "direct")
        self.assertEqual(components_by_id["node_ec2"]["monthly_cost_usd"], 140.0)

        # Lambda is a direct match (serverless, $5 base), no size keyword -> 1x.
        self.assertEqual(components_by_id["node_lambda"]["category"], "serverless")
        self.assertEqual(components_by_id["node_lambda"]["monthly_cost_usd"], 5.0)

        # S3 is a direct match (storage, $25 base).
        self.assertEqual(components_by_id["node_s3"]["category"], "storage")
        self.assertEqual(components_by_id["node_s3"]["monthly_cost_usd"], 25.0)

        # The made-up shape matches nothing -> unclassified, $0.
        self.assertEqual(components_by_id["node_mystery"]["confidence"], "unclassified")
        self.assertEqual(components_by_id["node_mystery"]["monthly_cost_usd"], 0.0)

        self.assertEqual(result["cost_estimate"]["total_monthly_cost_usd"], 140.0 + 5.0 + 25.0 + 0.0)
        self.assertEqual(result["cost_estimate"]["unclassified_component_count"], 1)

        titles = {r["title"] for r in result["optimization_recommendations"]}
        self.assertIn("Verify large/high-tier instance sizing against real load", titles)
        self.assertIn("No autoscaling noted for always-on resources", titles)
        self.assertIn("No reserved-capacity/savings-plan commitment mentioned", titles)
        # node_s3 has no edges in/out of it at all.
        self.assertIn("Component(s) with no connections in this diagram", titles)
        orphan_rec = next(
            r for r in result["optimization_recommendations"]
            if r["title"] == "Component(s) with no connections in this diagram"
        )
        self.assertIn("Archive Bucket", orphan_rec["components_involved"])

        # 3+ recommendations -> High.
        self.assertEqual(result["cost_risk_rating"], "High")

    def test_diagram_with_no_recognizable_service_icons(self):
        layout_only_xml = """
        <mxfile><diagram><mxGraphModel><root>
          <mxCell id="0" /><mxCell id="1" parent="0" />
          <mxCell id="box" value="Just a box" style="rounded=1;" vertex="1" parent="1">
            <mxGeometry x="0" y="0" width="100" height="60" as="geometry" />
          </mxCell>
        </root></mxGraphModel></diagram></mxfile>
        """
        result = json.loads(finops.estimate_cloudarch_finops(layout_only_xml))
        self.assertEqual(result["error"], "no_cost_data_available")


class CatalogPricingTests(unittest.TestCase):
    def test_multiple_usage_meters_are_parsed_and_priced(self):
        details = (
            "service code: AmazonApiGateway\nsku: gateway-plan\n"
            "usage: 730 hours/month\nusage: 1,000,000 requests/month"
        )
        self.assertEqual(pricing._usages(details), [(730.0, "hours"), (1000000.0, "requests")])
        result = pricing._catalog_price([
            {"sku": "gateway-plan", "unit": "Hrs", "rate": "0.05", "source": "AWS Price List API"},
            {"sku": "gateway-plan", "unit": "Requests", "rate": "0.000001", "source": "AWS Price List API"},
        ], details)
        self.assertEqual(result["monthly_cost_usd"], 37.5)
        self.assertEqual(len(result["usage_meters"]), 2)

    def test_default_catalog_lookup_uses_disclosed_baseline_without_sku_usage(self):
        record = {
            "sku": "Amazon S3 Standard",
            "skuName": "Amazon S3 Standard",
            "description": "Amazon S3 Standard storage",
            "unit": "GB-Mo",
            "rate": 0.023,
            "region": "us-east-1",
            "source": "AWS Price List API (On-Demand)",
        }
        with (
            patch.object(pricing, "_aws_service_code", return_value="AmazonS3"),
            patch.object(pricing, "_aws_records", return_value=[record]),
        ):
            result = pricing.lookup_catalog_resource_price("aws4", "s3", "aws4 s3 archive bucket")
        self.assertIsNotNone(result)
        self.assertEqual(result["monthly_cost_usd"], 2.3)
        self.assertEqual(result["pricing_basis"], "provider_catalog_baseline")
        self.assertIn("100 GB-Mo per month", result["assumption"])

    def test_default_catalog_lookup_supports_azure_and_google(self):
        azure_record = {
            "sku": "Standard_LRS",
            "skuName": "Standard LRS",
            "description": "Storage Standard LRS",
            "unit": "1 GB/Month",
            "rate": 0.02,
            "region": "eastus",
            "source": "Azure Retail Prices API",
        }
        with patch.object(pricing, "_azure_records", return_value=[azure_record]) as azure:
            azure_result = pricing.lookup_catalog_resource_price(
                "azure", "storage_accounts", "azure storage accounts archive bucket"
            )
        self.assertEqual(azure_result["monthly_cost_usd"], 2.0)
        self.assertEqual(azure.call_args.args[2], "Storage")

        google_record = {
            "sku": "google-storage-sku",
            "skuName": "Cloud Storage Standard",
            "description": "Cloud Storage Standard storage",
            "unit": "GiB-month",
            "rate": 0.02,
            "region": "us-central1",
            "source": "Google Cloud Billing Catalog API",
        }
        with (
            patch.dict("os.environ", {"GOOGLE_CLOUD_BILLING_API_KEY": "test-key"}),
            patch.object(pricing, "_google_service_id", return_value="storage-service"),
            patch.object(pricing, "_google_records", return_value=[google_record]),
        ):
            google_result = pricing.lookup_catalog_resource_price(
                "gcp2", "cloud_storage", "gcp2 cloud storage archive bucket"
            )
        self.assertEqual(google_result["monthly_cost_usd"], 2.0)

    def test_ambiguous_or_incomplete_meter_falls_back(self):
        records = [
            {"sku": "gateway-plan", "unit": "Requests", "rate": 0.000001},
            {"sku": "gateway-plan", "unit": "Requests", "rate": 0.000002},
        ]
        self.assertIsNone(pricing._catalog_price(
            records, "sku: gateway-plan\nusage: 1000 requests/month"
        ))
        self.assertIsNone(pricing._catalog_price(
            records,
            "sku: gateway-plan\nusage: 1000 requests/month\nusage: 100 hours/month",
        ))

    def test_storage_capacity_unit_and_full_noncompute_estimate(self):
        record = {
            "sku": "Standard_LRS", "unit": "1 GB/Month", "rate": 0.02,
            "region": "eastus", "source": "Azure Retail Prices API",
        }
        with patch.object(pricing, "_azure_records", return_value=[record]):
            cost = pricing.lookup_catalog_resource_price(
                "azure",
                "s3",
                "Storage Bucket sku: Standard_LRS region: eastus "
                "service: Storage usage: 500 GB/month",
            )
        self.assertEqual(cost["monthly_cost_usd"], 10.0)

        catalog_cost = {
            "monthly_cost_usd": 10.0,
            "sku": "Standard_LRS",
            "region": "eastus",
            "source": "Azure Retail Prices API",
            "usage_meters": [{"usage_quantity": 500, "usage_unit": "GB"}],
            "assumption": "Explicitly stated monthly usage: 500 GB",
        }
        with patch.object(
            finops,
            "lookup_catalog_resource_price",
            side_effect=lambda _, slug, __, ___: catalog_cost if slug == "s3" else None,
        ):
            result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))
        storage = next(
            component for component in result["cost_estimate"]["components"]
            if component["id"] == "node_s3"
        )
        self.assertEqual(storage["monthly_cost_usd"], 10.0)
        self.assertEqual(storage["pricing_basis"], "provider_catalog")
        self.assertEqual(result["cost_estimate"]["provider_priced_component_count"], 1)
        self.assertIn("1 of 4 component costs are grounded", result["cost_estimate"]["pricing_method_summary"])
        self.assertIn("Azure Retail Prices API", result["cost_estimate"]["pricing_method_summary"])

    def test_default_catalog_basis_is_reported_in_full_estimate(self):
        baseline_cost = {
            "monthly_cost_usd": 2.3,
            "sku": "Amazon S3 Standard",
            "region": "us-east-1",
            "source": "AWS Price List API (On-Demand)",
            "usage_meters": [{"usage_quantity": 100, "usage_unit": "GB-Mo"}],
            "assumption": "Catalog-grounded baseline assumption: 100 GB-Mo per month.",
            "pricing_basis": "provider_catalog_baseline",
        }
        with patch.object(
            finops,
            "lookup_catalog_resource_price",
            side_effect=lambda _, slug, __, ___: baseline_cost if slug == "s3" else None,
        ):
            result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))
        storage = next(
            component for component in result["cost_estimate"]["components"]
            if component["id"] == "node_s3"
        )
        self.assertEqual(storage["pricing_basis"], "provider_catalog_baseline")
        self.assertIn("baseline usage assumptions", result["cost_estimate"]["pricing_method_summary"])
        self.assertEqual(result["cost_estimate"]["provider_priced_component_count"], 1)
        self.assertIn("1 of 4 component costs are grounded", result["cost_estimate"]["pricing_method_summary"])
        self.assertIn("AWS Price List API", result["cost_estimate"]["pricing_method_summary"])

    def test_estimate_explicitly_reports_heuristic_only_costs(self):
        result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))
        self.assertEqual(
            result["cost_estimate"]["pricing_method_summary"],
            "No component costs were grounded in provider pricing catalogs; "
            "all 4 component costs use heuristic estimates.",
        )

    def test_aws_and_google_catalog_paths_use_explicit_service_identifiers(self):
        aws_record = {
            "sku": "gateway-plan",
            "unit": "Requests",
            "rate": 0.000001,
            "source": "AWS Price List API (On-Demand)",
        }
        with patch.object(pricing, "_aws_records", return_value=[aws_record]):
            aws_result = pricing.lookup_catalog_resource_price(
                "aws4",
                "api_gateway",
                "service code: AmazonApiGateway sku: gateway-plan usage: 1,000,000 requests/month",
            )
        self.assertEqual(aws_result["monthly_cost_usd"], 1.0)

        google_record = {
            "sku": "google-storage-sku",
            "unit": "gibibyte month",
            "rate": 0.02,
            "source": "Google Cloud Billing Catalog API",
        }
        with (
            patch.dict("os.environ", {"GOOGLE_CLOUD_BILLING_API_KEY": "test-key"}),
            patch.object(pricing, "_google_records", return_value=[google_record]),
        ):
            google_result = pricing.lookup_catalog_resource_price(
                "gcp2",
                "cloud_storage",
                "service id: storage-service sku: google-storage-sku usage: 500 GiB/month",
            )
        self.assertEqual(google_result["monthly_cost_usd"], 10.0)

    def test_google_tiered_price_is_not_treated_as_flat_rate(self):
        item = {
            "pricingInfo": [{
                "pricingExpression": {
                    "usageUnit": "GiBy",
                    "tieredRates": [
                        {"startUsageAmount": 0, "unitPrice": {"currencyCode": "USD", "units": 0}},
                        {"startUsageAmount": 10, "unitPrice": {"currencyCode": "USD", "units": 0.02}},
                    ],
                }
            }]
        }
        self.assertIsNone(pricing._google_unit_price(item))


if __name__ == "__main__":
    unittest.main()
