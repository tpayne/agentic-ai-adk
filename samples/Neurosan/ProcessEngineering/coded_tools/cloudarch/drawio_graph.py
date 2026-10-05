"""Parses mxGraph/drawio XML into a plain vertices/edges structure.

Ported verbatim from the ADK sample's parse_drawio_graph (utils.py).
"""

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict

_SHAPE_TOKEN_RE = re.compile(r"shape=mxgraph\.(\w+)\.([\w_]+);")


def parse_drawio_graph(xml_content: str) -> Dict[str, Any]:
    """Vertices are REAL SERVICE NODES ONLY -- a cell counts as a vertex if
    EITHER it carries a shape=mxgraph.<provider>.<slug>; token on its own
    style (the freehand-XML convention, where the icon IS the cell), OR one
    of its CHILD cells does (the structured-layout-engine convention: an
    icon-bearing component is a plain labeled box whose icon is a separate
    small child cell -- see cloudarch_layout_engine.py's borderless-icon
    components). Layout/grouping boxes have neither and are excluded, since
    they aren't independently-failing components.

    NOTE: the child-cell case is NOT in the ADK original this was ported
    from -- found and fixed here. build_structured_drawio_xml (the
    now-default diagram-generation path, copied verbatim from the ADK
    original) puts the shape token on a CHILD icon cell, not the labeled
    parent cell edges actually reference as source/target. The ADK
    original's own parse_drawio_graph only checked a vertex's own style,
    so every edge from a structured-engine-generated diagram silently
    failed to match any "vertex" (since the id edges reference is the
    parent, not the icon child) -- not a crash, a silently wrong,
    all-isolated-nodes graph. The ADK original's own test fixture for this
    function predates the layout engine's icon-as-child-cell change and
    never exercised this combination, which is how it went unnoticed.
    Returns {"vertices": [], "edges": []} on any parse failure rather than
    raising."""
    try:
        root = ET.fromstring(xml_content)
    except Exception:
        return {"vertices": [], "edges": []}

    cells = root.findall(".//mxCell")
    cells_by_id = {cell.get("id"): cell for cell in cells}

    # First pass: does this cell (by id) have a child whose OWN style
    # carries the shape token, where the PARENT is itself a vertex cell?
    # (the structured-layout-engine convention specifically: a labeled
    # component -- vertex="1" -- containing a small icon child that is
    # ALSO vertex="1". The parent-is-a-vertex condition matters: in the
    # freehand-XML convention, a shape-bearing cell's parent is typically
    # the plain canvas layer (vertex != "1"), and that cell must remain
    # its own independent vertex, not get deferred to a non-vertex parent.
    # Also track which cell ids ARE such a shape-bearing child, so the
    # second pass can skip them -- otherwise an icon child would match
    # BOTH as its parent's shape source AND, independently, as a vertex
    # in its own right, double-counting the same component.
    child_shape_match_by_parent_id: Dict[str, "re.Match"] = {}
    shape_bearing_child_ids = set()
    for cell in cells:
        parent_id = cell.get("parent")
        if not parent_id:
            continue
        parent_cell = cells_by_id.get(parent_id)
        if parent_cell is None or parent_cell.get("vertex") != "1":
            continue
        match = _SHAPE_TOKEN_RE.search(cell.get("style") or "")
        if match:
            child_shape_match_by_parent_id[parent_id] = match
            shape_bearing_child_ids.add(cell.get("id"))

    vertices = []
    edges = []
    for cell in cells:
        style = cell.get("style") or ""
        if cell.get("vertex") == "1":
            cell_id = cell.get("id")
            if cell_id in shape_bearing_child_ids:
                continue  # represented via its parent instead, not independently
            match = _SHAPE_TOKEN_RE.search(style) or child_shape_match_by_parent_id.get(cell_id)
            if not match:
                continue
            vertices.append({
                "id": cell_id,
                "value": (cell.get("value") or "").strip(),
                "shape_provider": match.group(1),
                "shape_slug": match.group(2),
            })
        elif cell.get("edge") == "1":
            source, target = cell.get("source"), cell.get("target")
            if not source or not target:
                continue
            edges.append({
                "id": cell.get("id"),
                "value": (cell.get("value") or "").strip(),
                "source": source,
                "target": target,
            })

    return {"vertices": vertices, "edges": edges}
