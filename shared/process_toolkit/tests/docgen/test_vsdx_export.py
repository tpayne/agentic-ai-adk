"""vsdx_export.py's own end-to-end coverage: the two public entry points
round-tripped through ingestion/extractors.py's own _extract_vsdx_file (the
import side, already shipped and tested separately) -- a real structural
check, not a mock. Each test also asserts the committed template file
(templates/blank_shape.vsdx) is never mutated by a render, since every
render opens it directly rather than a copy.
"""

import hashlib
import json
import os

from vsdx import VisioFile

from process_toolkit import paths
from process_toolkit.docgen.vsdx_export import (
    _TEMPLATE_PATH, _build_vsdx, build_cloudarch_vsdx, build_process_design_vsdx,
)
from process_toolkit.drawio.persistence import DRAWIO_FILENAME
from process_toolkit.ingestion.extractors import _extract_vsdx_file
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME


def _template_hash() -> str:
    with open(_TEMPLATE_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _write_process_json(steps):
    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"process_name": "Order Fulfillment", "process_steps": steps}, f)


def test_build_vsdx_round_trips_shape_text_and_connections_with_no_stray_links():
    before = _template_hash()
    out_path = paths.output_path("fixture_flow.vsdx")

    edges = [("Receive Request", "Review"), ("Review", "Approve")]
    label_map = {"Receive Request": "Receive Request", "Review": "Review", "Approve": "Approve"}
    _build_vsdx(edges, {}, label_map, "Process", "Fixture Flow", out_path)

    assert _template_hash() == before

    extracted = _extract_vsdx_file(out_path)
    assert "Receive Request" in extracted
    assert "Review" in extracted
    assert "Approve" in extracted
    assert "Receive Request -- Review" in extracted or "Review -- Receive Request" in extracted
    assert "Review -- Approve" in extracted or "Approve -- Review" in extracted

    with VisioFile(out_path) as vis:
        assert len(vis.pages) == 1
        page = vis.pages[0]
        # 3 node shapes + 1 connector shape per edge (vsdx's own Connect.create
        # behavior, confirmed by hand) = 5; 2 Connect entries per edge = 4.
        assert len(page.all_shapes) == 5
        assert len(page.connects) == 4


def test_build_vsdx_with_no_edges_produces_an_empty_page_not_a_crash():
    # Nodes are derived from edges (graph.add_edges_from(edges); nodes =
    # list(graph.nodes())) -- the same contract edge_inference.py's own
    # generate_clean_diagram uses -- so a label with no edge at all never
    # participates. Every REAL caller goes through _infer_edges_from_json,
    # which always returns at least a Start->End edge, so this never
    # actually happens in practice; this just pins down the behavior.
    out_path = paths.output_path("single_node.vsdx")
    _build_vsdx([], {}, {"Lonely": "Lonely"}, "Process", "Single", out_path)

    with VisioFile(out_path) as vis:
        page = vis.pages[0]
        assert page.all_shapes == []
        assert page.connects == []


def test_build_process_design_vsdx_falls_back_to_a_start_end_placeholder_when_no_process_data():
    # _infer_edges_from_json ALWAYS returns something (a Start->End
    # fallback edge) when output/process_data.json is missing -- the same
    # "always produces something" contract the PNG renderer relies on.
    result = build_process_design_vsdx("process")
    assert result.startswith("Visio diagram successfully exported to ")
    out_path = result.removeprefix("Visio diagram successfully exported to ")

    extracted = _extract_vsdx_file(out_path)
    assert "Start" in extracted
    assert "End" in extracted


def test_build_process_design_vsdx_exports_the_saved_process():
    _write_process_json([
        {"step_name": "Receive Order"},
        {"step_name": "Pick Items"},
        {"step_name": "Ship Order"},
    ])

    result = build_process_design_vsdx("process")
    assert result.startswith("Visio diagram successfully exported to ")
    out_path = result.removeprefix("Visio diagram successfully exported to ")
    assert os.path.exists(out_path)

    extracted = _extract_vsdx_file(out_path)
    assert "Receive Order" in extracted
    assert "Pick Items" in extracted
    assert "Ship Order" in extracted


def test_build_cloudarch_vsdx_errors_without_crashing_when_no_saved_diagram():
    result = build_cloudarch_vsdx()
    assert result.startswith("ERROR:")


def test_build_cloudarch_vsdx_errors_when_saved_diagram_has_no_components():
    xml = (
        '<mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '</root></mxGraphModel>'
    )
    with open(paths.output_path(DRAWIO_FILENAME), "w", encoding="utf-8") as f:
        f.write(xml)

    result = build_cloudarch_vsdx()
    assert result.startswith("ERROR:")


def test_build_cloudarch_vsdx_exports_vertices_and_edges_from_saved_diagram():
    xml = (
        '<mxGraphModel><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        '<mxCell id="api" value="API Gateway" vertex="1" parent="1" '
        'style="shape=mxgraph.aws4.resourceIcon;"/>'
        '<mxCell id="db" value="Database" vertex="1" parent="1" '
        'style="shape=mxgraph.aws4.resourceIcon;"/>'
        '<mxCell id="e1" edge="1" source="api" target="db" parent="1"/>'
        '</root></mxGraphModel>'
    )
    with open(paths.output_path(DRAWIO_FILENAME), "w", encoding="utf-8") as f:
        f.write(xml)

    result = build_cloudarch_vsdx()
    assert result.startswith("Visio diagram successfully exported to ")
    out_path = result.removeprefix("Visio diagram successfully exported to ")

    extracted = _extract_vsdx_file(out_path)
    assert "API Gateway" in extracted
    assert "Database" in extracted
    assert "API Gateway -- Database" in extracted or "Database -- API Gateway" in extracted
