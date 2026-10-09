"""Mirrors the ADK original's tests/test_cloudarch_finops_agent.py -- same
scenarios, adapted to this project's pytest-function (not unittest.TestCase)
convention and drawio_graph test file's simpler freehand-XML fixture style
(see tests/test_drawio_graph.py)."""

import json
from unittest.mock import patch

from coded_tools.cloudarch import finops
from coded_tools.cloudarch.drawio_graph import parse_drawio_graph
from coded_tools.cloudarch import pricing

# node_ec2's value embeds real <b>/<br/>/<font> tags (escaped as XML
# entities in the source, as a real drawio file would have them, and
# un-escaped back to real tags by parse_drawio_graph) -- exercising
# _split_label_and_bullets' HTML-stripping against the exact shape
# cloudarch_layout_engine.py's own _html_value produces. "m5.xlarge" in
# the bullet should trip the size multiplier; the EC2 node has no
# autoscaling/reserved-capacity keywords anywhere in the diagram, so both
# of those recommendations should fire too. node_s3 has no edges at all
# (orphaned). node_mystery uses a shape slug that matches neither the
# direct pricing table nor any category keyword, to exercise the
# unclassified path.
_SAMPLE_XML = """
<mxGraphModel><root>
    <mxCell id="0" />
    <mxCell id="1" parent="0" />
    <mxCell id="box_layout" value="Layout Box" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1" />
    <mxCell id="node_ec2" value="&lt;b&gt;Web Server&lt;/b&gt;&lt;br/&gt;&lt;font style=&quot;font-size:10px;color:#5f6368&quot;&gt;m5.xlarge&lt;/font&gt;" style="shape=mxgraph.aws4.ec2;" vertex="1" parent="1" />
    <mxCell id="node_lambda" value="&lt;b&gt;Image Resizer&lt;/b&gt;" style="shape=mxgraph.aws4.lambda;" vertex="1" parent="1" />
    <mxCell id="node_s3" value="&lt;b&gt;Archive Bucket&lt;/b&gt;" style="shape=mxgraph.aws4.s3;" vertex="1" parent="1" />
    <mxCell id="node_mystery" value="&lt;b&gt;Mystery Box&lt;/b&gt;" style="shape=mxgraph.aws4.some_made_up_future_service;" vertex="1" parent="1" />
    <mxCell id="edge_ec2_lambda" value="invokes" edge="1" parent="1" source="node_ec2" target="node_lambda" />
</root></mxGraphModel>
"""


def _fixture_graph():
    return parse_drawio_graph(_SAMPLE_XML)


def test_split_label_and_bullets_strips_html():
    graph = _fixture_graph()
    node_ec2 = next(v for v in graph["vertices"] if v["id"] == "node_ec2")
    label, bullets = finops._split_label_and_bullets(node_ec2["value"])
    assert label == "Web Server"
    assert bullets == ["m5.xlarge"]


def test_split_label_and_bullets_with_no_bullets():
    graph = _fixture_graph()
    node_lambda = next(v for v in graph["vertices"] if v["id"] == "node_lambda")
    label, bullets = finops._split_label_and_bullets(node_lambda["value"])
    assert label == "Image Resizer"
    assert bullets == []


def test_classify_component_direct_table_match():
    category, cost, confidence = finops._classify_component("ec2", "ec2 web server")
    assert category == "compute"
    assert cost == 70.0
    assert confidence == "direct"


def test_classify_component_category_keyword_fallback():
    # "aurora_instance" isn't in the direct table, but contains "aurora"
    # which is a database keyword.
    category, cost, confidence = finops._classify_component("aurora_instance", "aurora_instance primary cluster")
    assert category == "database"
    assert cost == finops._CATEGORY_DEFAULT_USD_PER_MONTH["database"]
    assert confidence == "category"


def test_classify_component_unclassified_when_nothing_matches():
    category, cost, confidence = finops._classify_component(
        "some_made_up_future_service", "some_made_up_future_service mystery box"
    )
    assert category is None
    assert cost == 0.0
    assert confidence == "unclassified"


def test_size_multiplier_xlarge_doubles_cost():
    assert finops._size_multiplier("ec2 web server m5.xlarge") == 2.0


def test_size_multiplier_2xlarge_quadruples_not_xlarge_rate():
    # "2xlarge" contains "xlarge" as a substring -- the biggest-tier rule
    # must win, not whichever rule happens to be checked first.
    assert finops._size_multiplier("ec2 web server m5.2xlarge") == 4.0


def test_size_multiplier_small_discounts_cost():
    assert finops._size_multiplier("ec2 web server t3.small") == 0.4


def test_size_multiplier_no_keyword_is_baseline():
    assert finops._size_multiplier("ec2 web server") == 1.0


def test_find_sku_and_region_for_each_provider():
    assert pricing._find_sku_and_region("aws4", "m5.xlarge in us-east-1") == (
        "m5.xlarge",
        "us-east-1",
    )
    assert pricing._find_sku_and_region("azure", "Standard_D2s_v3 in East US") == (
        "Standard_D2s_v3",
        "eastus",
    )
    assert pricing._find_sku_and_region("gcp2", "n2-standard-4 in us-central1") == (
        "n2-standard-4",
        "us-central1",
    )


def test_azure_price_catalog_returns_hourly_vm_rate():
    with patch.object(
        pricing,
        "_get_json",
        return_value={
            "Items": [
                {
                    "type": "Consumption",
                    "unitOfMeasure": "1 Hour",
                    "retailPrice": 0.12,
                    "effectiveStartDate": "2026-01-01T00:00:00Z",
                    "meterName": "D2s v3",
                },
                {
                    "type": "Consumption",
                    "unitOfMeasure": "1 Hour",
                    "retailPrice": 0.01,
                    "effectiveStartDate": "2026-06-01T00:00:00Z",
                    "meterName": "D2s v3 Spot",
                },
                {
                    "type": "DevTestConsumption",
                    "unitOfMeasure": "1 Hour",
                    "retailPrice": 0.02,
                    "effectiveStartDate": "2026-06-01T00:00:00Z",
                    "meterName": "D2s v3",
                },
            ]
        },
    ) as get_json:
        assert pricing._azure_hourly_price("Standard_D2s_v3", "eastus", windows=False) == 0.12

    request_url = get_json.call_args.args[0]
    assert "prices.azure.com/api/retail/prices" in request_url
    assert "armSkuName" in request_url
    assert "eastus" in request_url


def test_aws_price_list_parses_on_demand_hourly_price():
    from botocore.session import get_session

    price_list = {
        "terms": {
            "OnDemand": {
                "term": {
                    "priceDimensions": {
                        "dimension": {
                            "unit": "Hrs",
                            "pricePerUnit": {"USD": "0.192"},
                        }
                    }
                }
            }
        }
    }
    with patch("botocore.session.get_session") as make_session:
        client = make_session.return_value.create_client.return_value
        client.get_products.return_value = {"PriceList": [json.dumps(price_list)]}
        assert pricing._aws_hourly_price("m5.xlarge", "us-east-1", False) == 0.192

    make_session.return_value.create_client.assert_called_once_with("pricing", region_name="us-east-1")
    assert client.get_products.call_args.kwargs["Filters"][0]["Value"] == "us-east-1"


def test_google_catalog_combines_cpu_and_memory_rates_for_vm_shape():
    def pricing_info(price, unit_description):
        return [{
            "effectiveTime": "2025-01-01T00:00:00Z",
            "pricingExpression": {
                "usageUnit": "h",
                "usageUnitDescription": unit_description,
                "tieredRates": [{
                    "startUsageAmount": 0,
                    "unitPrice": {"currencyCode": "USD", "units": 0, "nanos": int(price * 1e9)},
                }],
            },
        }]

    with patch.object(
        pricing,
        "_get_json",
        return_value={
            "skus": [
                {
                    "description": "N2 Instance Core running in Iowa",
                    "serviceRegions": ["us-central1"],
                    "pricingInfo": pricing_info(0.03, "hour"),
                },
                {
                    "description": "N2 Instance Ram running in Iowa",
                    "serviceRegions": ["us-central1"],
                    "pricingInfo": pricing_info(0.004, "gibibyte hour"),
                },
            ]
        },
    ):
        hourly = pricing._google_compute_hourly_price("n2-standard-4", "us-central1", "test-key")

    assert hourly == 0.184


def test_live_compute_price_uses_monthly_provider_rate_and_reuses_cache():
    cache = {}
    with patch.object(pricing, "_aws_hourly_price", return_value=0.2) as get_price:
        first = pricing.lookup_compute_price("aws4", "m5.xlarge in us-east-1", cache)
        second = pricing.lookup_compute_price("aws4", "web server m5.xlarge us-east-1", cache)

    assert first == second
    assert first["monthly_cost_usd"] == 146.0
    assert first["source"] == "AWS Price List API (On-Demand)"
    get_price.assert_called_once_with("m5.xlarge", "us-east-1", False)


def test_unavailable_provider_catalog_returns_to_heuristic_estimate():
    with patch.object(pricing, "_aws_hourly_price", side_effect=TimeoutError):
        assert pricing.lookup_compute_price("aws4", "m5.xlarge us-east-1") is None


def test_full_estimate_uses_provider_rate_without_double_applying_size():
    live_price = {
        "monthly_cost_usd": 219.0,
        "hourly_rate_usd": 0.3,
        "sku": "m5.xlarge",
        "region": "us-east-1",
        "source": "AWS Price List API (On-Demand)",
        "assumption": "On-demand, 730 operating hours per month",
    }
    with patch.object(finops, "lookup_compute_price", return_value=live_price):
        result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))

    compute = next(c for c in result["cost_estimate"]["components"] if c["id"] == "node_ec2")
    assert compute["monthly_cost_usd"] == 219.0
    assert compute["size_multiplier"] == 2.0
    assert compute["pricing_basis"] == "provider_catalog"
    assert result["cost_estimate"]["provider_priced_component_count"] == 1
    assert result["cost_estimate"]["heuristic_component_count"] == 3
    assert result["cost_estimate"]["pricing_sources"] == ["AWS Price List API (On-Demand)"]


def test_missing_google_billing_key_keeps_catalog_lookup_optional():
    with patch.dict("os.environ", {}, clear=True):
        assert pricing.lookup_compute_price("gcp2", "n2-standard-4 us-central1") is None


def test_google_catalog_lookup_uses_api_key_when_configured():
    with (
        patch.dict("os.environ", {"GOOGLE_CLOUD_BILLING_API_KEY": "test-key"}),
        patch.object(pricing, "_google_compute_hourly_price", return_value=0.1) as get_price,
    ):
        result = pricing.lookup_compute_price("gcp2", "n2-standard-4 us-central1")

    assert result["monthly_cost_usd"] == 73.0
    assert result["source"] == "Google Cloud Billing Catalog API"
    get_price.assert_called_once_with("n2-standard-4", "us-central1", "test-key")


def test_explicit_usage_parser_accepts_multiple_monthly_meters():
    assert pricing._explicit_usages(
        "sku: gateway-plan; usage: 730 hours/month; usage: 1,000,000 requests/month"
    ) == [(730.0, "hours"), (1000000.0, "requests")]


def test_catalog_price_sums_all_explicit_non_compute_meters():
    records = [
        {"sku": "gateway-plan", "unit": "Hrs", "rate": "0.05", "source": "AWS Price List API"},
        {"sku": "gateway-plan", "unit": "Requests", "rate": "0.000001", "source": "AWS Price List API"},
    ]
    with patch.object(pricing, "_aws_catalog_records", return_value=records):
        result = pricing.lookup_catalog_resource_price(
            "aws4",
            "api_gateway",
            "service code: AmazonApiGateway\nsku: gateway-plan\n"
            "usage: 730 hours/month\nusage: 1,000,000 requests/month",
        )

    assert result["monthly_cost_usd"] == 37.5
    assert result["source"] == "AWS Price List API"
    assert len(result["usage_meters"]) == 2


def test_default_catalog_lookup_prices_without_explicit_sku_or_usage():
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
        patch.object(pricing, "_aws_catalog_records", return_value=[record]),
    ):
        result = pricing.lookup_catalog_resource_price(
            "aws4", "s3", "aws4 s3 archive bucket"
        )

    assert result["monthly_cost_usd"] == 2.3
    assert result["pricing_basis"] == "provider_catalog_baseline"
    assert "100 GB-Mo per month" in result["assumption"]


def test_default_catalog_lookup_supports_azure_and_google():
    azure_record = {
        "sku": "Standard_LRS",
        "skuName": "Standard LRS",
        "description": "Storage Standard LRS",
        "unit": "1 GB/Month",
        "rate": 0.02,
        "region": "eastus",
        "source": "Azure Retail Prices API",
    }
    with patch.object(pricing, "_azure_catalog_records", return_value=[azure_record]) as azure:
        azure_result = pricing.lookup_catalog_resource_price(
            "azure", "storage_accounts", "azure storage accounts archive bucket"
        )
    assert azure_result["monthly_cost_usd"] == 2.0
    assert azure.call_args.args[2] == "Storage"

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
        patch.object(pricing, "_google_catalog_records", return_value=[google_record]),
    ):
        google_result = pricing.lookup_catalog_resource_price(
            "gcp2", "cloud_storage", "gcp2 cloud storage archive bucket"
        )
    assert google_result["monthly_cost_usd"] == 2.0


def test_catalog_price_matches_storage_capacity_month_units():
    record = {
        "sku": "Standard_LRS",
        "unit": "1 GB/Month",
        "rate": 0.02,
        "region": "eastus",
        "source": "Azure Retail Prices API",
    }
    with patch.object(pricing, "_azure_catalog_records", return_value=[record]):
        result = pricing.lookup_catalog_resource_price(
            "azure",
            "storage_account",
            "service: Storage\nsku: Standard_LRS\nregion: eastus\nusage: 500 GB/month",
        )

    assert result["monthly_cost_usd"] == 10.0
    assert result["usage_meters"][0]["catalog_unit"] == "1 GB/Month"


def test_google_catalog_prices_a_resource_with_explicit_usage():
    record = {
        "sku": "catalog-sku-id",
        "unit": "gibibyte month",
        "rate": 0.02,
        "region": "us-central1",
        "source": "Google Cloud Billing Catalog API",
    }
    with (
        patch.dict("os.environ", {"GOOGLE_CLOUD_BILLING_API_KEY": "test-key"}),
        patch.object(pricing, "_google_catalog_records", return_value=[record]),
    ):
        result = pricing.lookup_catalog_resource_price(
            "gcp2",
            "cloud_storage",
            "service id: storage-service-id\nsku: catalog-sku-id\n"
            "region: us-central1\nusage: 500 GiB/month",
        )

    assert result["monthly_cost_usd"] == 10.0
    assert result["source"] == "Google Cloud Billing Catalog API"


def test_catalog_price_falls_back_when_meter_is_ambiguous_or_missing():
    records = [
        {"sku": "gateway-plan", "unit": "Requests", "rate": 0.000001},
        {"sku": "gateway-plan", "unit": "Requests", "rate": 0.000002},
    ]
    with patch.object(pricing, "_aws_catalog_records", return_value=records):
        ambiguous_diagnostic = {}
        ambiguous = pricing.lookup_catalog_resource_price(
            "aws4",
            "api_gateway",
            "service code: AmazonApiGateway\nsku: gateway-plan\nusage: 1000 requests/month",
            diagnostics=ambiguous_diagnostic,
        )
        incomplete = pricing.lookup_catalog_resource_price(
            "aws4",
            "api_gateway",
            "service code: AmazonApiGateway\nsku: gateway-plan\n"
            "usage: 1000 requests/month\nusage: 100 hours/month",
        )

    assert ambiguous is None
    assert incomplete is None
    assert "no unique USD rate" in ambiguous_diagnostic["reason"]


def test_catalog_diagnostics_explain_missing_key_and_unavailable_api():
    google_diagnostic = {}
    with patch.dict("os.environ", {}, clear=True):
        result = pricing.lookup_catalog_resource_price(
            "gcp2", "cloud_storage", "gcp2 cloud storage", diagnostics=google_diagnostic
        )
    assert result is None
    assert "GOOGLE_CLOUD_BILLING_API_KEY" in google_diagnostic["reason"]
    assert "skipped" in google_diagnostic["reason"]

    aws_diagnostic = {}
    with patch.object(pricing, "_aws_catalog_records", side_effect=TimeoutError):
        result = pricing.lookup_catalog_resource_price(
            "aws4",
            "s3",
            "service code: AmazonS3",
            diagnostics=aws_diagnostic,
        )
    assert result is None
    assert "timeout or network" in aws_diagnostic["reason"]


def test_google_generic_catalog_refuses_differential_tiers():
    sku = {
        "pricingInfo": [{
            "effectiveTime": "2025-01-01T00:00:00Z",
            "pricingExpression": {
                "usageUnit": "GiBy",
                "usageUnitDescription": "gibibyte month",
                "tieredRates": [
                    {"startUsageAmount": 0, "unitPrice": {"currencyCode": "USD", "units": 0}},
                    {"startUsageAmount": 10, "unitPrice": {"currencyCode": "USD", "units": 0.02}},
                ],
            },
        }],
    }
    assert pricing._google_unit_price(sku) is None


def test_full_estimate_can_catalog_price_a_non_compute_component():
    catalog_price = {
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
        side_effect=lambda _, slug, __, ___, _____: catalog_price if slug == "s3" else None,
    ):
        result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))

    storage = next(c for c in result["cost_estimate"]["components"] if c["id"] == "node_s3")
    assert storage["monthly_cost_usd"] == 10.0
    assert storage["pricing_basis"] == "provider_catalog"
    assert storage["pricing_usage_meters"][0]["usage_quantity"] == 500
    assert "1 of 4 component costs are grounded" in result["cost_estimate"]["pricing_method_summary"]
    assert "Azure Retail Prices API" in result["cost_estimate"]["pricing_method_summary"]


def test_full_estimate_reports_default_catalog_baseline():
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
        side_effect=lambda _, slug, __, ___, _____: baseline_cost if slug == "s3" else None,
    ):
        result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))

    storage = next(c for c in result["cost_estimate"]["components"] if c["id"] == "node_s3")
    assert storage["pricing_basis"] == "provider_catalog_baseline"
    assert "baseline usage assumptions" in result["cost_estimate"]["pricing_method_summary"]
    assert result["cost_estimate"]["provider_priced_component_count"] == 1


def test_estimate_explicitly_reports_heuristic_only_costs():
    result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))
    assert result["cost_estimate"]["pricing_method_summary"].startswith(
        "No component costs were grounded in provider pricing catalogs; "
        "all 4 component costs use heuristic estimates."
    )


def test_heuristic_components_expose_catalog_fallback_reasons():
    def unavailable(provider, slug, haystack, cache, diagnostics):
        diagnostics["reason"] = "Catalog access was denied."
        return None

    with patch.object(finops, "lookup_catalog_resource_price", side_effect=unavailable):
        result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))

    estimate = result["cost_estimate"]
    fallback_reasons = {
        item["reason"]: item["components"]
        for item in estimate["pricing_fallback_reasons"]
    }
    assert fallback_reasons["Catalog access was denied."] == [
        "Image Resizer", "Archive Bucket", "Mystery Box"
    ]
    assert fallback_reasons[
        "Catalog access was denied. Legacy compute catalog lookup: "
        "The legacy compute catalog lookup requires an explicit VM SKU and region."
    ] == ["Web Server"]
    assert "Catalog access was denied." in estimate["pricing_method_summary"]
    component_reasons = {
        component["label"]: component["pricing_fallback_reason"]
        for component in estimate["components"]
    }
    assert component_reasons["Web Server"].startswith("Catalog access was denied.")


def test_no_diagram_available():
    with patch.object(finops, "load_drawio_xml", return_value={"status": "NOT_FOUND", "xml": None}):
        result = json.loads(finops.estimate_cloudarch_finops())
    assert result["error"] == "no_diagram_available"


def test_full_estimate_against_the_fixture_diagram():
    result = json.loads(finops.estimate_cloudarch_finops(_SAMPLE_XML))

    assert "error" not in result
    assert result["component_count"] == 4

    components_by_id = {c["id"]: c for c in result["cost_estimate"]["components"]}

    # EC2 is a direct match (compute, $70 base) with an xlarge bullet -> 2x multiplier.
    assert components_by_id["node_ec2"]["category"] == "compute"
    assert components_by_id["node_ec2"]["confidence"] == "direct"
    assert components_by_id["node_ec2"]["monthly_cost_usd"] == 140.0

    # Lambda is a direct match (serverless, $5 base), no size keyword -> 1x.
    assert components_by_id["node_lambda"]["category"] == "serverless"
    assert components_by_id["node_lambda"]["monthly_cost_usd"] == 5.0

    # S3 is a direct match (storage, $25 base).
    assert components_by_id["node_s3"]["category"] == "storage"
    assert components_by_id["node_s3"]["monthly_cost_usd"] == 25.0

    # The made-up shape matches nothing -> unclassified, $0.
    assert components_by_id["node_mystery"]["confidence"] == "unclassified"
    assert components_by_id["node_mystery"]["monthly_cost_usd"] == 0.0

    assert result["cost_estimate"]["total_monthly_cost_usd"] == 140.0 + 5.0 + 25.0 + 0.0
    assert result["cost_estimate"]["unclassified_component_count"] == 1

    titles = {r["title"] for r in result["optimization_recommendations"]}
    assert "Verify large/high-tier instance sizing against real load" in titles
    assert "No autoscaling noted for always-on resources" in titles
    assert "No reserved-capacity/savings-plan commitment mentioned" in titles
    # node_s3 has no edges in/out of it at all.
    assert "Component(s) with no connections in this diagram" in titles
    orphan_rec = next(
        r for r in result["optimization_recommendations"]
        if r["title"] == "Component(s) with no connections in this diagram"
    )
    assert "Archive Bucket" in orphan_rec["components_involved"]

    # 3+ recommendations -> High.
    assert result["cost_risk_rating"] == "High"


def test_diagram_with_no_recognizable_service_icons():
    layout_only_xml = """
    <mxGraphModel><root>
        <mxCell id="0" /><mxCell id="1" parent="0" />
        <mxCell id="box" value="Just a box" style="rounded=1;" vertex="1" parent="1" />
    </root></mxGraphModel>
    """
    result = json.loads(finops.estimate_cloudarch_finops(layout_only_xml))
    assert result["error"] == "no_cost_data_available"


def test_google_catalog_records_pages_through_all_results():
    # Regression test for a bug where the page token returned by the API
    # was never read, so every iteration silently re-fetched page 1 and
    # results beyond it were never seen.
    def tiered_price(value):
        return [{
            "pricingExpression": {
                "usageUnit": "GiBy.mo",
                "tieredRates": [{
                    "startUsageAmount": 0,
                    "unitPrice": {"currencyCode": "USD", "units": 0, "nanos": int(value * 1e9)},
                }],
            }
        }]

    page_one = {
        "skus": [{"skuId": "sku-a", "description": "Resource A", "pricingInfo": tiered_price(0.01)}],
        "nextPageToken": "page-2",
    }
    page_two = {
        "skus": [{"skuId": "sku-b", "description": "Resource B", "pricingInfo": tiered_price(0.02)}],
    }
    with patch.object(pricing, "_get_json", side_effect=[page_one, page_two]) as get_json:
        records = pricing._google_catalog_records("service-id", None, None, "test-key")

    assert get_json.call_count == 2
    assert "pageToken=page-2" in get_json.call_args_list[1].args[0]
    assert {r["sku"] for r in records} == {"sku-a", "sku-b"}


def test_aws_catalog_records_narrows_by_sku_field_before_falling_back():
    # Regression test for a bug where the AWS query was never narrowed by
    # the known SKU, so a large service's desired instance type could
    # silently fall outside the page cap and never be found.
    from unittest.mock import MagicMock

    wanted_product = json.dumps({
        "product": {"sku": "WANTED", "attributes": {"instanceType": "m5.xlarge", "regionCode": "us-east-1"}},
        "terms": {"OnDemand": {"term": {"priceDimensions": {"dim": {
            "unit": "Hrs", "pricePerUnit": {"USD": "0.192"},
        }}}}},
    })
    irrelevant_product = json.dumps({
        "product": {"sku": "IRRELEVANT", "attributes": {"instanceType": "t3.micro", "regionCode": "us-east-1"}},
        "terms": {"OnDemand": {"term": {"priceDimensions": {"dim": {
            "unit": "Hrs", "pricePerUnit": {"USD": "0.01"},
        }}}}},
    })

    def get_products(**kwargs):
        field_values = {f["Field"]: f["Value"] for f in kwargs.get("Filters", [])}
        if field_values.get("instanceType") == "m5.xlarge":
            return {"PriceList": [wanted_product]}
        if any(k in field_values for k in ("instanceType", "volumeType", "storageClass")):
            return {"PriceList": []}
        return {"PriceList": [irrelevant_product]}

    client = MagicMock()
    client.get_products.side_effect = get_products
    with patch("botocore.session.get_session") as make_session:
        make_session.return_value.create_client.return_value = client
        records = pricing._aws_catalog_records("AmazonEC2", "us-east-1", "m5.xlarge")

    assert any(r["sku"] == "WANTED" for r in records)
    assert not any(r["skuName"] == "t3.micro" for r in records)
    assert any(
        f["Field"] == "instanceType" and f["Value"] == "m5.xlarge"
        for call in client.get_products.call_args_list
        for f in call.kwargs["Filters"]
    )


def test_aws_catalog_records_falls_back_to_unfiltered_fetch_when_no_sku_field_matches():
    # If none of the known SKU field names apply to this service, the old
    # best-effort unfiltered fetch should still run rather than returning
    # nothing at all.
    from unittest.mock import MagicMock

    fallback_product = json.dumps({
        "product": {
            "sku": "OBSCURE-1",
            "attributes": {"regionCode": "us-east-1", "instanceType": "custom-sku"},
        },
        "terms": {"OnDemand": {"term": {"priceDimensions": {"dim": {
            "unit": "Hrs", "pricePerUnit": {"USD": "1.5"},
        }}}}},
    })

    def get_products(**kwargs):
        field_values = {f["Field"]: f["Value"] for f in kwargs.get("Filters", [])}
        if any(k in field_values for k in ("instanceType", "volumeType", "storageClass")):
            return {"PriceList": []}
        return {"PriceList": [fallback_product]}

    client = MagicMock()
    client.get_products.side_effect = get_products
    with patch("botocore.session.get_session") as make_session:
        make_session.return_value.create_client.return_value = client
        records = pricing._aws_catalog_records("SomeObscureService", "us-east-1", "custom-sku")

    assert any(r["sku"] == "OBSCURE-1" for r in records)
