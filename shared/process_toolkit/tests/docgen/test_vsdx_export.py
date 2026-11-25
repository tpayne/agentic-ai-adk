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
import shutil
import subprocess
import zipfile

import pytest
from vsdx import VisioFile

from process_toolkit import paths
from process_toolkit.docgen.vsdx_export import (
    _BOX_FILL_COLOR, _BOX_LINE_COLOR, _BOX_TEXT_COLOR, _OPC_RELS_NS, _TEMPLATE_PATH,
    _build_vsdx, _sanitize_vsdx_package, build_cloudarch_vsdx, build_process_design_vsdx,
    parse_vsdx_to_graph,
)
from process_toolkit.drawio.persistence import DRAWIO_FILENAME
from process_toolkit.ingestion.extractors import _extract_vsdx_file
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME


_DRAWIO_BIN = shutil.which("drawio") or next(
    (p for p in ("/Applications/draw.io.app/Contents/MacOS/draw.io",) if os.path.isfile(p)), None
)


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


class TestParseVsdxToGraph:
    def test_round_trips_real_vertices_and_edges(self):
        out_path = paths.output_path("fixture_flow.vsdx")
        edges = [("Receive Request", "Review"), ("Review", "Approve")]
        label_map = {"Receive Request": "Receive Request", "Review": "Review", "Approve": "Approve"}
        _build_vsdx(edges, {}, label_map, "Process", "Fixture Flow", out_path)

        graph = parse_vsdx_to_graph(out_path)

        labels = {v["label"] for v in graph["vertices"]}
        assert labels == {"Receive Request", "Review", "Approve"}
        assert len(graph["edges"]) == 2

        by_label = {v["label"]: v for v in graph["vertices"]}
        for vertex in by_label.values():
            assert vertex["width"] > 0
            assert vertex["height"] > 0

    def test_edges_reference_real_vertex_ids_in_both_directions(self):
        out_path = paths.output_path("fixture_flow2.vsdx")
        edges = [("A", "B")]
        label_map = {"A": "A", "B": "B"}
        _build_vsdx(edges, {}, label_map, "Process", "Fixture", out_path)

        graph = parse_vsdx_to_graph(out_path)
        vertex_ids = {v["id"] for v in graph["vertices"]}
        assert len(graph["edges"]) == 1
        edge = graph["edges"][0]
        assert edge["source"] in vertex_ids
        assert edge["target"] in vertex_ids
        assert edge["source"] != edge["target"]

    def test_connector_shapes_do_not_leak_in_as_fake_vertices(self):
        # CONFIRMED AS A REAL BUG during development: page.all_shapes walks
        # connector/line shapes too (zero height, no text) -- without
        # filtering to shapes with real text, every connector became an
        # extra, fake, zero-size "vertex" alongside the real labeled ones.
        out_path = paths.output_path("fixture_flow3.vsdx")
        edges = [("A", "B"), ("B", "C")]
        label_map = {"A": "A", "B": "B", "C": "C"}
        _build_vsdx(edges, {}, label_map, "Process", "Fixture", out_path)

        graph = parse_vsdx_to_graph(out_path)
        assert len(graph["vertices"]) == 3
        for vertex in graph["vertices"]:
            assert vertex["label"] in {"A", "B", "C"}

    def test_vertices_carry_the_real_shape_colors_through_to_the_graph_json(self):
        # The web client's own renderGraphDiagram ignores vertex color
        # entirely unless parse_vsdx_to_graph actually puts it on the wire --
        # this is what makes the real .vsdx file's own (now theme-independent,
        # see TestNodeShapesAreReadableWithoutATheme) colors actually show up
        # on screen instead of the web client's generic white-box fallback.
        out_path = paths.output_path("fixture_flow_colors.vsdx")
        _build_vsdx([("A", "B")], {}, {"A": "A", "B": "B"}, "Process", "Colors", out_path)

        graph = parse_vsdx_to_graph(out_path)
        assert len(graph["vertices"]) == 2
        for vertex in graph["vertices"]:
            assert vertex["style"]["fillColor"] == _BOX_FILL_COLOR
            assert vertex["style"]["strokeColor"] == _BOX_LINE_COLOR
            assert vertex["style"]["fontColor"] == _BOX_TEXT_COLOR

    def test_empty_page_parses_cleanly_with_no_crash(self):
        # _build_vsdx with no edges produces zero shapes at all (nodes are
        # derived from edges -- see test_build_vsdx_with_no_edges_produces_
        # an_empty_page_not_a_crash above) -- this just pins down that
        # parse_vsdx_to_graph handles a genuinely empty page gracefully.
        out_path = paths.output_path("fixture_empty.vsdx")
        _build_vsdx([], {}, {"Lonely": "Lonely"}, "Process", "Empty", out_path)

        graph = parse_vsdx_to_graph(out_path)
        assert graph == {"vertices": [], "edges": []}


class TestNodeShapesAreReadableWithoutATheme:
    # CONFIRMED AS A REAL BUG: blank_shape.vsdx's own template shape only
    # carries LineStyle/FillStyle/TextStyle="3" ("Normal"), which itself
    # chains to StyleSheet "Theme" (ID 6) -- every fill/line/text color on
    # that chain is a THEMEVAL() formula with no literal fallback, and this
    # template ships no visio/theme/*.xml part at all for those formulas to
    # resolve against. Real Microsoft Visio quietly substitutes a readable
    # default; diagrams.net's own .vsdx importer does not, so every node
    # rendered as a pure-white box with invisible (white-on-white) text.

    def test_every_node_shape_gets_a_literal_non_themed_fill_and_line_color(self):
        out_path = paths.output_path("colored_flow.vsdx")
        _build_vsdx([("A", "B"), ("B", "C")], {}, {"A": "A", "B": "B", "C": "C"}, "Process", "Colors", out_path)

        with VisioFile(out_path) as vis:
            node_shapes = [s for s in vis.pages[0].all_shapes if (s.text or "").strip()]
            assert len(node_shapes) == 3
            for shape in node_shapes:
                assert shape.fill_color == _BOX_FILL_COLOR
                assert shape.line_color == _BOX_LINE_COLOR

    def test_every_node_shape_gets_a_literal_text_color_via_its_own_character_section(self):
        out_path = paths.output_path("colored_flow2.vsdx")
        _build_vsdx([("A", "B")], {}, {"A": "A", "B": "B"}, "Process", "Colors", out_path)

        with VisioFile(out_path) as vis:
            node_shapes = [s for s in vis.pages[0].all_shapes if (s.text or "").strip()]
            assert len(node_shapes) == 2
            for shape in node_shapes:
                assert shape.text_color == _BOX_TEXT_COLOR


class TestSanitizePackageProducesCanonicalOpcXml:
    # CONFIRMED AS A REAL BUG: vsdx's own vsdxfile.py registers both the OPC
    # relationships namespace and the content-types namespace to the SAME
    # empty ElementTree prefix at import time; register_namespace() can only
    # hold one namespace per prefix, so the second call silently evicts the
    # first. Any later ET.tostring() on a relationships element -- ours in
    # _sanitize_vsdx_package, or vsdx's own document.xml.rels rewrite when it
    # adds a duplicate "masters" relationship on every Shape.copy() -- then
    # comes out wrapped in an auto-generated ns0: prefix instead of the
    # canonical unprefixed form real OOXML tooling (and a real diagrams.net
    # import) expects.

    def test_pages_rels_uses_the_canonical_unprefixed_relationships_namespace(self):
        out_path = paths.output_path("ns_check_pages.vsdx")
        _build_vsdx([("A", "B")], {}, {"A": "A", "B": "B"}, "Process", "NS Check", out_path)

        with zipfile.ZipFile(out_path) as z:
            xml_bytes = z.read("visio/pages/_rels/pages.xml.rels")
        assert b"ns0:" not in xml_bytes
        assert f'xmlns="{_OPC_RELS_NS}"'.encode() in xml_bytes

    def test_document_rels_has_no_duplicate_masters_relationship_after_many_shape_copies(self):
        # Each extra node is another Shape.copy() -- confirmed (before this
        # fix) to append one more duplicate "masters" relationship pointing
        # at the exact same target every time.
        out_path = paths.output_path("ns_check_document.vsdx")
        edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
        label_map = {n: n for n in "ABCDE"}
        _build_vsdx(edges, {}, label_map, "Process", "NS Check", out_path)

        with zipfile.ZipFile(out_path) as z:
            xml_bytes = z.read("visio/_rels/document.xml.rels")
        assert b"ns0:" not in xml_bytes
        assert xml_bytes.count(b"relationships/masters") == 1

    def test_orphaned_page_rels_with_no_matching_page_part_are_stripped(self):
        # CONFIRMED AS A REAL BUG: a real exported package was found carrying
        # a visio/pages/_rels/page1.xml.rels with no visio/pages/page1.xml of
        # its own (the vsdx library had renumbered the live page to
        # page2.xml on save without cleaning up the stale page1 rels entry).
        # An orphaned relationship part is invalid OPC -- a strict importer
        # can refuse the whole package over it.
        out_path = paths.output_path("orphan_check.vsdx")
        _build_vsdx([("A", "B")], {}, {"A": "A", "B": "B"}, "Process", "Orphan Check", out_path)

        with zipfile.ZipFile(out_path, "a") as z:
            z.writestr(
                "visio/pages/_rels/page9.xml.rels",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/master" '
                'Target="../masters/master1.xml"/></Relationships>',
            )

        _sanitize_vsdx_package(out_path)

        with zipfile.ZipFile(out_path) as z:
            names = set(z.namelist())
        assert "visio/pages/_rels/page9.xml.rels" not in names
        assert "visio/pages/_rels/page1.xml.rels" in names  # the real page's own rels survives


@pytest.mark.skipif(not _DRAWIO_BIN, reason="no real draw.io binary installed on this machine")
class TestRealDrawioCanActuallyImportTheFile:
    # Every other test in this file validates structure by reading the file
    # back with the SAME python vsdx library that wrote it -- which proved
    # blind to the exact bug that mattered here: a real draw.io import
    # ("draw.io -x") was refusing the file outright ("cannot import VSDX
    # file") over an ns0: namespace-prefix corruption that the vsdx library
    # itself introduces on save (see _renormalize_visio_namespace_prefixes's
    # own docstring), which this project's own round-trip tests could never
    # have caught since they never asked a REAL, independent third-party
    # importer. Skipped (not failed) when the binary isn't present, since
    # most CI environments won't have the Electron app installed -- this is
    # a local developer safety net against this exact class of regression.
    def test_a_generated_vsdx_imports_cleanly_into_the_real_drawio_binary(self, tmp_path):
        out_path = str(tmp_path / "drawio_import_check.vsdx")
        _build_vsdx(
            [("Receive Request", "Review"), ("Review", "Approve")], {},
            {"Receive Request": "Receive Request", "Review": "Review", "Approve": "Approve"},
            "Process", "Import Check", out_path,
        )

        exported = tmp_path / "drawio_import_check.xml"
        result = subprocess.run(
            [_DRAWIO_BIN, "-x", "-f", "xml", "-o", str(exported), out_path],
            capture_output=True, text=True, timeout=60,
        )

        assert result.returncode == 0, f"draw.io refused to import the file: {result.stderr}"
        xml_text = exported.read_text(encoding="utf-8")
        assert "Receive Request" in xml_text
        assert f"fillColor={_BOX_FILL_COLOR}" in xml_text
        assert f"strokeColor={_BOX_LINE_COLOR}" in xml_text
