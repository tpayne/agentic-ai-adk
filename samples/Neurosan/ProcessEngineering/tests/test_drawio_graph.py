"""Regression test for a real bug found while porting: the ADK original's
parse_drawio_graph only recognized a vertex via a shape token on the
cell's OWN style. build_structured_drawio_xml (the now-default diagram
path, copied verbatim from the ADK original) puts the shape token on a
separate CHILD icon cell instead -- the labeled parent cell edges actually
reference as source/target carries no shape token itself. The ADK
original's own test fixture for this function predates that layout-engine
change and never exercised the combination, so every edge from a
structured-engine-generated diagram silently matched no real vertex there
(not a crash -- a silently wrong, all-isolated-nodes graph)."""

from coded_tools.cloudarch.cloudarch_layout_engine import build_structured_drawio_xml
from coded_tools.cloudarch.drawio_graph import parse_drawio_graph


def test_recognizes_vertices_from_the_structured_layout_engines_output():
    xml = build_structured_drawio_xml(
        title="Checkout", subtitle=None,
        zones=[{"id": "edge", "label": "Edge"}, {"id": "app", "label": "App"}],
        components=[
            {"id": "waf", "zone_id": "edge", "label": "WAF", "shape": "mxgraph.aws4.waf"},
            {"id": "api", "zone_id": "edge", "label": "API Gateway", "shape": "mxgraph.aws4.api_gateway"},
        ],
        edges=[{"source": "waf", "target": "api"}],
    )

    graph = parse_drawio_graph(xml)

    vertex_ids = {v["id"] for v in graph["vertices"]}
    # The vertex must be keyed by the LABELED component id ("waf"), which is
    # what the edge's source/target actually reference -- not by the icon
    # child cell's id ("waf_icon"), and not duplicated as both.
    assert vertex_ids == {"waf", "api"}
    assert len(graph["vertices"]) == 2

    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["source"] == "waf"
    assert graph["edges"][0]["target"] == "api"


def test_still_recognizes_freehand_xml_vertices_with_the_shape_on_the_cell_itself():
    xml = """
    <mxGraphModel><root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="node_a" value="Lambda A" style="shape=mxgraph.aws4.lambda;" vertex="1" parent="1" />
        <mxCell id="node_b" value="RDS B" style="shape=mxgraph.aws4.rds;" vertex="1" parent="1" />
        <mxCell id="e1" edge="1" parent="1" source="node_a" target="node_b" />
    </root></mxGraphModel>
    """
    graph = parse_drawio_graph(xml)
    assert {v["id"] for v in graph["vertices"]} == {"node_a", "node_b"}
    assert graph["edges"][0]["source"] == "node_a"


def test_layout_only_boxes_are_excluded():
    xml = """
    <mxGraphModel><root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="zone1" value="Edge" style="swimlane;" vertex="1" parent="1" />
        <mxCell id="title_banner" value="Title" style="rounded=1;" vertex="1" parent="1" />
    </root></mxGraphModel>
    """
    graph = parse_drawio_graph(xml)
    assert graph["vertices"] == []


def test_invalid_xml_returns_empty_graph_not_an_exception():
    assert parse_drawio_graph("<not><valid") == {"vertices": [], "edges": []}
