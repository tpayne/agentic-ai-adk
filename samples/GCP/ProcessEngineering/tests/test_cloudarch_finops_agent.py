import json
import unittest
from unittest.mock import patch

from test_grounding_agent import _install_dependency_stubs

_install_dependency_stubs()
from process_agents.common import utils  # noqa: E402
from process_agents.cloudarch import cloudarch_finops_agent as finops  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
