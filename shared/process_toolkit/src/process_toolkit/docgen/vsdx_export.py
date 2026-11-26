"""On-demand Visio (.vsdx) export for process/design flow diagrams and cloud
architecture -- the reverse direction of ingestion/extractors.py's own
_extract_vsdx_file. Deliberately NOT wired into either generate/review loop
(process.hocon's Process_Pipeline, design.hocon's own pipeline, cloudarch.
hocon's CloudArch_Pipeline) -- this is an explicit, standalone, on-demand
action, the same shape as process_subprocess_regenerate.hocon's own
Subprocess_Driver_Agent_Main.

Reuses already-correct data rather than re-deriving it: process/design calls
edge_inference._infer_edges_from_json (the same (name, edges, lane_map,
label_map) tuple generate_clean_diagram's own PNG renderer already consumes,
with zero matplotlib/networkx DRAWING dependency); cloud architecture parses
the already-saved cloudarch_drawio.xml via drawio.graph.parse_drawio_graph,
the same way CloudArch_Agent's own refinement step already does -- no
persisted structured cloudarch model exists to call into instead.
"""

import contextlib
import io
import os
import re
from typing import Any, Dict, List, Tuple

import networkx as nx
from vsdx import Connect, VisioFile

from process_toolkit import paths
from process_toolkit.docgen.edge_inference import _infer_edges_from_json
from process_toolkit.drawio.graph import parse_drawio_graph
from process_toolkit.drawio.persistence import load_drawio_xml

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "blank_shape.vsdx")

# vsdx coordinates are in inches, unlike edge_inference.py's own PNG
# renderer (an arbitrary matplotlib unit space) -- these spacings are sized
# for a normal flowchart box, not copied from that renderer's own values.
_X_SPACING = 3.0
_Y_SPACING = -2.5
_INCH_TO_PX = 96.0  # Standard CSS/SVG/mxGraph 96 DPI coordinate space

_MAX_VISIO_PAGE_NAME_LENGTH = 31  # Visio's own real limit on a page name

# Fixed names (one current process and one current design per session, same
# as process_data.json/design_data.json/cloudarch_drawio.xml themselves) --
# deliberately NOT named after the process/design's own title the way the
# PNG renderer's "<name>_flow.png" is, so artifact-download plumbing (a
# fixed filename per artifact kind) stays as simple as cloudarch's own.
PROCESS_FLOW_VSDX_FILENAME = "process_flow.vsdx"
DESIGN_FLOW_VSDX_FILENAME = "design_flow.vsdx"
CLOUDARCH_VSDX_FILENAME = "cloudarch_architecture.vsdx"


def process_flow_vsdx_exists() -> bool:
    return os.path.isfile(paths.output_path(PROCESS_FLOW_VSDX_FILENAME))


def design_flow_vsdx_exists() -> bool:
    return os.path.isfile(paths.output_path(DESIGN_FLOW_VSDX_FILENAME))


def cloudarch_vsdx_exists() -> bool:
    return os.path.isfile(paths.output_path(CLOUDARCH_VSDX_FILENAME))


def _compute_layout(
    edges: List[Tuple[str, str]], lane_map: Dict[str, str], default_lane: str,
) -> Tuple[Dict[str, Tuple[float, float]], List[str]]:
    """Deliberately a SEPARATE copy of edge_inference.py's own
    generate_clean_diagram layout algorithm (topological x-ordering +
    first-lane-appearance y-ordering) -- not extracted into a shared
    function. That PNG rendering path is already shipped and heavily
    tested; duplicating this small, stable layout math here avoids any
    risk of changing its existing behavior for an unrelated new feature.
    Keep both in sync by hand if the algorithm itself ever needs to change.

    Mutates lane_map in place (setdefault only) -- same behavior as the
    PNG renderer's own identical step.
    """
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    nodes = list(graph.nodes())
    for node in nodes:
        lane_map.setdefault(node, default_lane)

    try:
        sequence_order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        sequence_order = nodes
    x_index = {node: i for i, node in enumerate(sequence_order)}

    lanes: List[str] = []
    for node in sequence_order:
        lane = lane_map.get(node, default_lane)
        if lane not in lanes:
            lanes.append(lane)
    remaining_lanes = sorted(set(lane_map.get(node, default_lane) for node in nodes) - set(lanes))
    lanes += remaining_lanes
    lane_index = {lane: i for i, lane in enumerate(lanes)}

    pos = {}
    for node in nodes:
        lane = lane_map.get(node, default_lane)
        pos[node] = (x_index.get(node, 0) * _X_SPACING, lane_index[lane] * _Y_SPACING)
    return pos, nodes


_OPC_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OPC_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_VISIO_MAIN_NS = "http://schemas.microsoft.com/office/visio/2012/main"
_OOXML_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Every real Visio content part vsdx's own save path re-serializes through
# ElementTree -- see _renormalize_visio_namespace_prefixes's own docstring
# for why these specifically (and only these) need re-registering.
_VISIO_PART_RE = re.compile(
    r"^visio/(document\.xml|windows\.xml|pages/pages\.xml|masters/masters\.xml"
    r"|pages/page\d+\.xml|masters/master\d+\.xml)$"
)


def _renormalize_visio_namespace_prefixes(entries: Dict[str, bytes]) -> None:
    """CONFIRMED AS A REAL BUG, empirically, against the real draw.io desktop
    binary (`draw.io -x -f xml`): vsdx's own vsdxfile.py registers SIX
    different namespaces to the SAME empty ElementTree prefix at module
    import time (the Visio main namespace, extended-properties, the OPC
    relationships namespace, and the OPC content-types namespace all via
    register_namespace('', ...)) -- ET.register_namespace() can only hold one
    namespace per prefix, so each later call silently evicts the one before
    it, leaving only the LAST registration (content-types) with the
    canonical unprefixed form. Every other part this library re-serializes
    via ET.tostring() -- document.xml, every page*.xml, every master*.xml,
    pages.xml -- therefore comes out wrapped in an auto-generated ns0:
    prefix instead.

    This alone was enough to make a real draw.io import refuse the file
    outright (exit code 1, "cannot import VSDX file") -- reproduced even for
    an otherwise byte-for-byte untouched, known-good .vsdx merely opened and
    re-saved once through this library with zero other modifications.
    Re-parsing and re-serializing each affected part with the correct
    namespace re-registered immediately beforehand restores the canonical
    form real Visio/drawio expect; draw.io -x then imports the result with
    exit code 0.
    """
    import xml.etree.ElementTree as ET

    ET.register_namespace("", _VISIO_MAIN_NS)
    ET.register_namespace("r", _OOXML_R_NS)
    for name in list(entries.keys()):
        if _VISIO_PART_RE.match(name):
            try:
                tree = ET.fromstring(entries[name])
                entries[name] = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
            except Exception:
                pass


def _sanitize_vsdx_package(path: str) -> None:
    """Post-save package sanitation to guarantee 100% strict OPC (Open Packaging
    Conventions) compliance and seamless import in third-party viewers (e.g. Draw.io /
    diagrams.net, Microsoft Visio):
    1. Ensures each page part (e.g. visio/pages/page1.xml) has its corresponding
       relationships file (_rels/page1.xml.rels) -- AND the reverse: strips any
       page _rels file left behind for a page part that no longer exists (observed
       directly in a real exported file: a dangling visio/pages/_rels/page1.xml.rels
       with no visio/pages/page1.xml of its own, left over after the vsdx library
       renumbered the page to page2.xml on save). An orphaned relationship part is
       invalid OPC, and a strict importer can refuse the whole package over it.
    2. Strips any dangling or duplicate relationships in visio/pages/_rels/pages.xml.rels
       and visio/_rels/document.xml.rels (the vsdx library re-adds a duplicate "masters"
       relationship to the latter on every single Shape.copy() call).
    3. Strips any dangling or duplicate <Override> tags in [Content_Types].xml.
    4. Re-registers the un-prefixed default namespace for whichever OPC namespace is
       about to be re-serialized, and (see _renormalize_visio_namespace_prefixes, run
       last) renormalizes every Visio-main-namespace part vsdx's own save path
       corrupts with an auto-generated ns0: prefix. Empirically confirmed against the
       real draw.io desktop binary: a .vsdx with this prefix corruption is refused
       outright ("cannot import VSDX file"), even for an otherwise byte-for-byte
       untouched, known-good file merely re-saved once through the vsdx library.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    with zipfile.ZipFile(path, "r") as z:
        entries = {name: z.read(name) for name in z.namelist()}

    if "visio/_rels/document.xml.rels" in entries:
        try:
            ET.register_namespace("", _OPC_RELS_NS)
            doc_rels_tree = ET.fromstring(entries["visio/_rels/document.xml.rels"])
            seen_rels = set()
            dupes = []
            for elem in list(doc_rels_tree):
                key = (elem.attrib.get("Type"), elem.attrib.get("Target"))
                if key in seen_rels:
                    dupes.append(elem)
                else:
                    seen_rels.add(key)
            for elem in dupes:
                doc_rels_tree.remove(elem)
            entries["visio/_rels/document.xml.rels"] = ET.tostring(
                doc_rels_tree, encoding="utf-8", xml_declaration=True
            )
        except Exception:
            pass

    # Strip orphaned page _rels files whose own page part no longer exists.
    for name in list(entries.keys()):
        if name.startswith("visio/pages/_rels/page") and name.endswith(".xml.rels"):
            page_filename = name.rsplit("/", 1)[-1][: -len(".rels")]
            if f"visio/pages/{page_filename}" not in entries:
                del entries[name]

    # Check referenced page rel_ids from visio/pages/pages.xml
    referenced_rel_ids = set()
    if "visio/pages/pages.xml" in entries:
        try:
            pages_tree = ET.fromstring(entries["visio/pages/pages.xml"])
            for page_elem in pages_tree.findall(".//{http://schemas.microsoft.com/office/visio/2012/main}Page"):
                for child in page_elem:
                    if child.tag.endswith("Rel"):
                        for k, v in child.attrib.items():
                            if k.endswith("id"):
                                referenced_rel_ids.add(v)
        except Exception:
            pass

    # Ensure every page file has a corresponding .rels file
    for name in list(entries.keys()):
        if name.startswith("visio/pages/page") and name.endswith(".xml"):
            page_filename = name.split("/")[-1]
            rels_name = f"visio/pages/_rels/{page_filename}.rels"
            if rels_name not in entries:
                fallback = entries.get("visio/pages/_rels/page1.xml.rels")
                if fallback:
                    entries[rels_name] = fallback

    # Clean visio/pages/_rels/pages.xml.rels
    if "visio/pages/_rels/pages.xml.rels" in entries:
        try:
            ET.register_namespace("", _OPC_RELS_NS)
            tree = ET.fromstring(entries["visio/pages/_rels/pages.xml.rels"])
            to_remove = []
            seen_targets = set()
            seen_ids = set()
            for elem in list(tree):
                target = elem.attrib.get("Target")
                rel_id = elem.attrib.get("Id")
                full_path = f"visio/pages/{target}" if target else ""
                if referenced_rel_ids:
                    if rel_id not in referenced_rel_ids or full_path not in entries:
                        to_remove.append(elem)
                else:
                    if not target or target in seen_targets or rel_id in seen_ids or full_path not in entries:
                        to_remove.append(elem)
                    else:
                        seen_targets.add(target)
                        seen_ids.add(rel_id)
            for elem in to_remove:
                tree.remove(elem)
            entries["visio/pages/_rels/pages.xml.rels"] = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
        except Exception:
            pass

    # Clean [Content_Types].xml
    if "[Content_Types].xml" in entries:
        try:
            ET.register_namespace("", _OPC_CONTENT_TYPES_NS)
            ct_tree = ET.fromstring(entries["[Content_Types].xml"])
            seen_overrides = set()
            to_remove = []
            for elem in list(ct_tree):
                tag = elem.tag.split("}")[-1]
                if tag == "Override":
                    part = elem.attrib.get("PartName")
                    zip_target = part.lstrip("/") if part else ""
                    if not part or part in seen_overrides or (zip_target and zip_target not in entries):
                        to_remove.append(elem)
                    else:
                        seen_overrides.add(part)
            for elem in to_remove:
                ct_tree.remove(elem)
            entries["[Content_Types].xml"] = ET.tostring(ct_tree, encoding="utf-8", xml_declaration=True)
        except Exception:
            pass

    # Last, and most consequential: see _renormalize_visio_namespace_prefixes's
    # own docstring. Run after the OPC-namespace cleanups above (each of
    # which transiently registers its OWN empty-prefix namespace) so this
    # function's own registration of the Visio main namespace is the final,
    # authoritative one in effect when its parts get re-serialized below.
    _renormalize_visio_namespace_prefixes(entries)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)


_BOX_FILL_COLOR = "#DAE8FC"  # same default rectangle fill drawio/diagrams.net itself uses
_BOX_LINE_COLOR = "#6C8EBF"  # matching drawio/diagrams.net's own default rectangle stroke
_BOX_TEXT_COLOR = "#000000"


def _ensure_character_section(shape) -> None:
    """blank_shape.vsdx's own template shape (and therefore every Shape.copy() of it)
    carries no <Section N="Character"> of its own -- its text color resolves purely
    through the LineStyle/FillStyle/TextStyle="3" ("Normal") -> "Theme" stylesheet chain,
    and this template ships no actual Visio theme part for those THEMEVAL() formulas to
    resolve against. Real Microsoft Visio quietly falls back to a readable default;
    diagrams.net's own .vsdx importer does not, rendering pure-white, textless boxes.
    Inserting an empty Character row here gives vsdx's own Shape.text_color setter
    (which only ever edits an EXISTING Color cell -- it never creates one) something to
    write into.
    """
    ns = "{http://schemas.microsoft.com/office/visio/2012/main}"
    if shape.xml.find(f'{ns}Section[@N="Character"]') is not None:
        return
    import xml.etree.ElementTree as ET

    section = ET.Element(f"{ns}Section", {"N": "Character", "IX": "0"})
    row = ET.SubElement(section, f"{ns}Row", {"IX": "0"})
    ET.SubElement(row, f"{ns}Cell", {"N": "Color", "V": "0"})
    children = list(shape.xml)
    text_el = shape.xml.find(f"{ns}Text")
    insert_at = children.index(text_el) if text_el is not None else len(children)
    shape.xml.insert(insert_at, section)


def _build_vsdx(
    edges: List[Tuple[str, str]], lane_map: Dict[str, str], label_map: Dict[str, str],
    default_lane: str, page_name: str, out_path: str,
) -> None:
    """The one place this module's own vsdx write mechanics live -- domain-
    specific callers below just assemble (edges, lane_map, label_map) and
    hand them here. Edits the canonical template page in-place, populates
    positioned shapes and connectors, then sanitizes the package to maintain
    full compatibility with external tools like Draw.io / diagrams.net.
    """
    pos, nodes = _compute_layout(edges, lane_map, default_lane)

    safe_page_name = (page_name or "Flow").strip()[:_MAX_VISIO_PAGE_NAME_LENGTH] or "Flow"

    with contextlib.redirect_stdout(io.StringIO()):
        with VisioFile(_TEMPLATE_PATH) as vis:
            page = vis.pages[0]
            page.name = safe_page_name
            template_shape = page.all_shapes[0]

            shapes_by_node = {}
            for i, node in enumerate(nodes):
                if i == 0:
                    shape = template_shape
                else:
                    shape = template_shape.copy(page=page)
                shape.text = label_map.get(node, node)
                _ensure_character_section(shape)
                shape.fill_color = _BOX_FILL_COLOR
                shape.line_color = _BOX_LINE_COLOR
                shape.text_color = _BOX_TEXT_COLOR
                x, y = pos[node]
                shape.move(x - shape.x, y - shape.y)
                shapes_by_node[node] = shape

            if not nodes:
                template_shape.remove()

            for source, target in edges:
                if source in shapes_by_node and target in shapes_by_node and source != target:
                    Connect.create(page=page, from_shape=shapes_by_node[source], to_shape=shapes_by_node[target])

            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            vis.save_vsdx(out_path)

    _sanitize_vsdx_package(out_path)


def build_process_design_vsdx(schema_type: str) -> str:
    """Exports the current saved process/design as a Visio flow diagram.
    Same "ERROR: ..." string convention as edge_inference.generate_clean_
    diagram (which this intentionally mirrors, targeting vsdx instead of
    PNG) rather than raising, so a CodedTool wrapper can relay it directly.
    """
    result = _infer_edges_from_json(schema_type)
    if not result:
        kind = "design" if schema_type == "design" else "process"
        return f"ERROR: Could not infer edges. Ensure output/{kind}_data.json exists."

    inferred_name, edges, lane_map, label_map = result
    is_design = schema_type == "design"
    default_lane = "Component" if is_design else "Process"
    default_title = "System Architecture" if is_design else "Process Architecture"
    final_name = (inferred_name or default_title).strip()

    out_filename = DESIGN_FLOW_VSDX_FILENAME if is_design else PROCESS_FLOW_VSDX_FILENAME
    out_path = paths.output_path(out_filename)

    try:
        _build_vsdx(edges or [], dict(lane_map), dict(label_map), default_lane, final_name, out_path)
    except Exception as e:  # pylint: disable=broad-except
        return f"Visio export failed: {e}"
    return f"Visio diagram successfully exported to {out_path}"


_DRAWIO_BR_RE = re.compile(r"(?i)<br\s*/?>")
_DRAWIO_TAG_RE = re.compile(r"<[^>]+>")


def _drawio_value_to_plain_text(value: str) -> str:
    """A cloudarch vertex's raw drawio "value" is HTML -- `<b>Label</b>
    <br/><font style="...">bullet</font>...`, the same markup cloudarch/
    layout.py's own _html_value constructs and cloudarch/finops.py's own
    _split_label_and_bullets already un-does for cost analysis. Visio shape
    text is plain text only: CONFIRMED AS A REAL BUG against a live
    session's own exported .vsdx -- every box's text was the raw HTML
    string verbatim (literal "<b>", "<br/>", "<font style=...>" substrings
    visible in Visio), passed straight through with no stripping.
    """
    text = _DRAWIO_BR_RE.sub("\n", value or "")
    return _DRAWIO_TAG_RE.sub("", text).strip()


def build_cloudarch_vsdx() -> str:
    """Exports the current saved cloud architecture diagram as a Visio
    file. Parses the already-saved cloudarch_drawio.xml (the same source
    CloudArch_Agent's own refinement step already re-parses on every
    turn) rather than requiring any new structured input -- no persisted
    zones/components/edges model exists between turns to call into
    instead.
    """
    loaded = load_drawio_xml()
    if loaded.get("status") != "OK" or not loaded.get("xml"):
        return "ERROR: No saved cloud architecture diagram found. Generate one first."

    graph = parse_drawio_graph(loaded["xml"])
    label_map = {}
    for v in graph.get("vertices", []):
        plain = _drawio_value_to_plain_text(v.get("value"))
        label_map[v["id"]] = plain or v["id"]
    if not label_map:
        return "ERROR: The saved cloud architecture diagram has no components to export."
    edges = [
        (edge["source"], edge["target"])
        for edge in graph.get("edges", [])
        if edge.get("source") in label_map and edge.get("target") in label_map
    ]

    out_path = paths.output_path(CLOUDARCH_VSDX_FILENAME)
    try:
        _build_vsdx(edges, {}, label_map, "Component", "Cloud Architecture", out_path)
    except Exception as e:  # pylint: disable=broad-except
        return f"Visio export failed: {e}"
    return f"Visio diagram successfully exported to {out_path}"


def parse_vsdx_to_graph(path: str) -> Dict[str, Any]:
    """Parses an existing .vsdx file's first page into the same generic
    {"vertices": [...], "edges": [...]} shape drawio.graph.parse_drawio_graph
    already produces for cloudarch -- so a single client-side renderer can
    draw either source.

    Shape coordinates in vsdx are in inches -- converted here to pixels
    (_INCH_TO_PX = 96.0), matching the CSS/SVG/mxGraph coordinate space the
    web client's renderer expects. Shape.x/.y are Visio's own PinX/PinY
    (the shape's CENTER point, in inches, Y increasing UPWARD) -- converted
    to top-left corner with Y increasing downward.

    Connect direction is determined by from_rel: 'BeginX' marks the connector
    origin (source shape), and 'EndX' marks the connector terminus (target
    shape), preserving the true flowchart arrow direction.
    """
    vertices: List[Dict[str, Any]] = []
    id_to_vertex: Dict[str, Dict[str, Any]] = {}

    with VisioFile(path) as vis:
        page = vis.pages[0]
        for shape in page.all_shapes:
            text = (shape.text or "").strip()
            if not text:
                continue
            width = (shape.width or 0.0) * _INCH_TO_PX
            height = (shape.height or 0.0) * _INCH_TO_PX
            x = (shape.x if shape.x is not None else 0.0) * _INCH_TO_PX
            y = (shape.y if shape.y is not None else 0.0) * _INCH_TO_PX
            vertex = {
                "id": shape.ID,
                "label": text,
                "x": x - width / 2,
                "y": -(y + height / 2),
                "width": width,
                "height": height,
                # None for any of these (e.g. a .vsdx authored outside this
                # app's own _build_vsdx, or one predating its literal color
                # cells) is intentional -- JSON null survives to the web
                # client's own `style.fillColor || "..."` fallback unchanged.
                "style": {
                    "fillColor": shape.fill_color,
                    "strokeColor": shape.line_color,
                    "fontColor": shape.text_color,
                },
            }
            vertices.append(vertex)
            id_to_vertex[shape.ID] = vertex

        connector_endpoints: Dict[str, Dict[str, str]] = {}
        for connect in page.connects:
            cid = connect.connector_shape_id
            endpoints = connector_endpoints.setdefault(cid, {})
            if connect.from_rel == "BeginX":
                endpoints["source"] = connect.shape_id
            elif connect.from_rel == "EndX":
                endpoints["target"] = connect.shape_id
            else:
                endpoints.setdefault("fallback", []).append(connect.shape_id)

    edges: List[Dict[str, Any]] = []
    for cid, endpoints in connector_endpoints.items():
        src = endpoints.get("source")
        tgt = endpoints.get("target")
        if src and tgt and src in id_to_vertex and tgt in id_to_vertex and src != tgt:
            edges.append({"source": src, "target": tgt})
        elif "fallback" in endpoints and len(endpoints["fallback"]) >= 2:
            real_ids = [sid for sid in dict.fromkeys(endpoints["fallback"]) if sid in id_to_vertex]
            if len(real_ids) >= 2:
                edges.append({"source": real_ids[0], "target": real_ids[1]})

    return {"vertices": vertices, "edges": edges}
