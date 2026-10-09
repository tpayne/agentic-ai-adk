"""Mirrors the ADK original's tests/test_cloudarch_finops_agent.py -- same
scenarios, adapted to this project's pytest-function (not unittest.TestCase)
convention and drawio_graph test file's simpler freehand-XML fixture style
(see tests/test_drawio_graph.py)."""

import json
from unittest.mock import patch

from coded_tools.cloudarch import finops
from coded_tools.cloudarch.drawio_graph import parse_drawio_graph

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
