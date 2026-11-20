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

import os
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


def _build_vsdx(
    edges: List[Tuple[str, str]], lane_map: Dict[str, str], label_map: Dict[str, str],
    default_lane: str, page_name: str, out_path: str,
) -> None:
    """The one place this module's own vsdx write mechanics live -- domain-
    specific callers below just assemble (edges, lane_map, label_map) and
    hand them here. Copies the template's one real shape once per node,
    positions/labels each copy, connects them, then discards the template
    page entirely (by INDEX, not name, so a page_name that happens to
    collide with the template's own name can never remove the wrong page)
    -- confirmed directly, by hand, that Shape.remove() alone leaves
    dangling Connect entries referencing the deleted shapes' own IDs,
    so the ORIGINAL template page (which has none, by construction -- see
    templates/blank_shape.vsdx's own header comment) is dropped wholesale
    rather than edited in place.
    """
    pos, nodes = _compute_layout(edges, lane_map, default_lane)

    safe_page_name = (page_name or "Flow").strip()[:_MAX_VISIO_PAGE_NAME_LENGTH] or "Flow"

    with VisioFile(_TEMPLATE_PATH) as vis:
        template_shape = vis.pages[0].all_shapes[0]
        page = vis.add_page(safe_page_name)

        shapes_by_node = {}
        for node in nodes:
            shape = template_shape.copy(page=page)
            shape.text = label_map.get(node, node)
            x, y = pos[node]
            shape.move(x - shape.x, y - shape.y)
            shapes_by_node[node] = shape

        for source, target in edges:
            if source in shapes_by_node and target in shapes_by_node and source != target:
                Connect.create(page=page, from_shape=shapes_by_node[source], to_shape=shapes_by_node[target])

        vis.remove_page_by_index(0)  # the template page -- always index 0, added before "page" above

        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        vis.save_vsdx(out_path)


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
    label_map = {v["id"]: (v.get("value") or v["id"]) for v in graph.get("vertices", [])}
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
    draw either source. A deliberately SEPARATE walk from ingestion/
    extractors.py's own _extract_vsdx_file (which does the identical
    shape/connect walk for its own text-extraction job) -- same "duplicate
    rather than share" discipline this module's own _compute_layout already
    follows for edge_inference.py's layout math, so a future change to one
    job's own output shape can never silently alter the other's.

    Shape.x/.y are Visio's own PinX/PinY (the shape's CENTER point, in
    inches, Y increasing UPWARD) -- converted here to a top-left corner
    with Y increasing downward, matching the SVG/mxGraph convention the
    client's existing renderer already assumes. Connect direction isn't
    recoverable from vsdx's own data model (same caveat _extract_vsdx_file
    already documents), so edges are emitted undirected.

    Only shapes with real text become vertices -- a connector/line shape
    carries no text of its own (confirmed directly: it has zero height and
    an empty .text), so skipping textless shapes is how _extract_vsdx_file
    already avoids treating a connector as content; without the same
    check here, every connector would leak into "vertices" as a second,
    fake, zero-size node alongside the two real shapes it actually joins.
    """
    vertices: List[Dict[str, Any]] = []
    id_to_vertex: Dict[str, Dict[str, Any]] = {}
    by_connector: Dict[str, List[str]] = {}

    with VisioFile(path) as vis:
        page = vis.pages[0]
        for shape in page.all_shapes:
            text = (shape.text or "").strip()
            if not text:
                continue
            width = shape.width or 0.0
            height = shape.height or 0.0
            x = shape.x if shape.x is not None else 0.0
            y = shape.y if shape.y is not None else 0.0
            vertex = {
                "id": shape.ID,
                "label": text,
                "x": x - width / 2,
                "y": -(y + height / 2),
                "width": width,
                "height": height,
            }
            vertices.append(vertex)
            id_to_vertex[shape.ID] = vertex

        for connect in page.connects:
            by_connector.setdefault(connect.connector_shape_id, []).append(connect.shape_id)

    edges: List[Dict[str, Any]] = []
    for shape_ids in by_connector.values():
        real_ids = [sid for sid in dict.fromkeys(shape_ids) if sid in id_to_vertex]
        if len(real_ids) >= 2:
            edges.append({"source": real_ids[0], "target": real_ids[1]})

    return {"vertices": vertices, "edges": edges}
