# process_agents/cloudarch_layout_agent.py
#
# Deterministic drawio/mxGraph layout engine for CloudArch diagrams, mirroring
# the split already used for BPMN process diagrams elsewhere in this codebase
# (edge_inference_agent.py / step_diagram_agent.py): the LLM supplies WHAT to
# draw (zones, components, icons, labels, connections) as plain structured
# data, and this module is the ONLY thing that ever computes WHERE anything
# goes. No coordinate ever originates from the model.
#
# This exists because, across many rounds of instruction tuning this session,
# the model reliably picked the right services/icons/relationships but
# reliably got PIXEL LAYOUT wrong in a shifting variety of ways (icons
# swallowing boxes, icons overlapping labels, boxes too short for their own
# text, edge labels landing on top of unrelated boxes, swimlane headers
# overlapping their own icons) -- a different failure each round, because a
# repair pass patching one cell at a time can never see the whole diagram at
# once, and prose instructions about pixel math don't reliably stick. A
# layout engine sees every box at layout time and can guarantee: every box is
# tall enough for its own text, icons sit in a fixed reserved slot, and every
# edge (including its label) is routed through space that is NEVER occupied
# by a box, by construction rather than by hoping the model got the numbers
# right.
#
# SCHEMA (all inputs are plain dicts/lists -- no XML, no coordinates):
#
#   zones: [{
#       "id": str,                       # unique
#       "label": str,                    # bold header title
#       "sublabel": str (optional),      # smaller header subtitle line
#       "row": int (optional, default 0),# zones with the same row are columns
#                                         # side by side; higher rows stack
#                                         # below all lower rows, full-width.
#       "stack": "vertical"|"horizontal" (optional, default "vertical"),
#                                         # how this zone arranges ITS OWN
#                                         # components -- "vertical" for a
#                                         # normal tier column, "horizontal"
#                                         # for a full-width row of side-by-
#                                         # side boxes (e.g. a governance strip).
#       "color": str (optional hex),     # header/border accent color
#       "width": int (optional),         # override the default column width
#   }, ...]
#
#   components: [{
#       "id": str,                       # unique
#       "zone_id": str,                  # which zone this lives in
#       "label": str,                    # bold title line
#       "bullets": [str, ...] (optional),# each becomes its own body line
#       "shape": str (optional),         # e.g. "mxgraph.gcp2.cloud_run" --
#                                         # if given, a correctly-sized/
#                                         # positioned icon child cell is
#                                         # added automatically
#       "icon_color": str (optional hex),
#       "color": str (optional hex),     # box border/accent color
#       "width": int (optional),         # override this component's width
#   }, ...]
#
#   edges: [{
#       "source": str, "target": str,    # component (or zone) ids
#       "label": str (optional),
#       "number": int (optional),        # prefixes the label "N. "
#       "color": str (optional hex),
#       "dashed": bool (optional),
#   }, ...]
#
# Everything else (title/subtitle, overall provider accent) is passed
# separately to build_structured_drawio_xml.

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# LAYOUT CONSTANTS
# ============================================================
PAGE_MARGIN = 40
TITLE_HEIGHT = 70
ZONE_GAP = 50          # horizontal gap between row-0 (column) zones -- the
                        # reserved channel inter-zone edges route through
ROW_GAP = 45            # vertical gap between one row of zones and the next
                        # -- the reserved channel drop-down edges route through
ZONE_HEADER_H_PLAIN = 45
ZONE_HEADER_H_SUBLABEL = 62
ZONE_INNER_MARGIN = 18   # margin inside a zone, above/below/beside its children
COMPONENT_GAP = 30       # vertical gap between stacked components in the
                        # same zone -- the reserved channel same-zone edges
                        # route through
COMPONENT_H_MARGIN = 15  # left/right margin inside a zone for its components
DEFAULT_ZONE_WIDTH = 340
ICON_SIZE = 40
ICON_TOP_MARGIN = 10
SPACING_TOP_WITH_ICON = ICON_TOP_MARGIN + ICON_SIZE + 8   # = 58, matches the
                        # formula given to the LLM elsewhere in this pipeline
SPACING_TOP_NO_ICON = 12
LINE_HEIGHT = 16
COMPONENT_BOTTOM_MARGIN = 20
DEFAULT_COMPONENT_COLOR = "#4285F4"
DEFAULT_ZONE_COLOR = "#4285F4"


def _line_count(component: Dict[str, Any]) -> int:
    return 1 + len(component.get("bullets") or [])  # title line + each bullet


def _component_height(component: Dict[str, Any]) -> int:
    has_icon = bool(component.get("shape"))
    spacing_top = SPACING_TOP_WITH_ICON if has_icon else SPACING_TOP_NO_ICON
    return spacing_top + _line_count(component) * LINE_HEIGHT + COMPONENT_BOTTOM_MARGIN


def _zone_header_height(zone: Dict[str, Any]) -> int:
    return ZONE_HEADER_H_SUBLABEL if zone.get("sublabel") else ZONE_HEADER_H_PLAIN


def _html_value(label: str, bullets: Optional[List[str]]) -> str:
    parts = [f"<b>{label}</b>"]
    for bullet in (bullets or []):
        parts.append(f"<font style=\"font-size:10px;color:#5f6368\">{bullet}</font>")
    return "<br/>".join(parts)


class _Box:
    """A component's or zone's resolved absolute bounding box, kept around
    after layout so the edge router can compute collision-free routes
    without re-deriving positions."""
    __slots__ = ("id", "x", "y", "w", "h", "zone_id", "row")

    def __init__(self, id_: str, x: float, y: float, w: float, h: float,
                 zone_id: Optional[str] = None, row: int = 0):
        self.id = id_
        self.x, self.y, self.w, self.h = x, y, w, h
        self.zone_id = zone_id
        self.row = row

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


def _layout_zones_and_components(
    zones: List[Dict[str, Any]], components: List[Dict[str, Any]]
) -> Tuple[Dict[str, _Box], Dict[str, _Box], float, float]:
    """
    Computes absolute boxes for every zone and every component.
    Returns (zone_boxes, component_boxes, canvas_width, canvas_height).
    """
    comps_by_zone: Dict[str, List[Dict[str, Any]]] = {}
    for c in components:
        comps_by_zone.setdefault(c["zone_id"], []).append(c)

    rows: Dict[int, List[Dict[str, Any]]] = {}
    for z in zones:
        rows.setdefault(int(z.get("row", 0)), []).append(z)

    zone_boxes: Dict[str, _Box] = {}
    component_boxes: Dict[str, _Box] = {}

    y_cursor = PAGE_MARGIN + TITLE_HEIGHT
    canvas_width = PAGE_MARGIN  # grows as row-0 columns are placed

    for row_num in sorted(rows.keys()):
        row_zones = rows[row_num]
        x_cursor = PAGE_MARGIN
        row_height = 0

        for zone in row_zones:
            zone_id = zone["id"]
            zone_children = comps_by_zone.get(zone_id, [])
            header_h = _zone_header_height(zone)
            stack = zone.get("stack", "vertical")

            if stack == "horizontal":
                # A full-width strip of side-by-side boxes (e.g. a governance
                # row). Width is however wide its children need to be; if
                # that's less than the full remaining canvas width, it's
                # stretched to fill it so the row still reads as one band.
                child_w = max(
                    (c.get("width") or DEFAULT_ZONE_WIDTH for c in zone_children),
                    default=DEFAULT_ZONE_WIDTH,
                )
                content_h = max((_component_height(c) for c in zone_children), default=0)
                zone_w = zone.get("width") or (
                    len(zone_children) * child_w
                    + max(0, len(zone_children) - 1) * ZONE_GAP
                    + 2 * COMPONENT_H_MARGIN
                )
                zone_h = header_h + content_h + 2 * ZONE_INNER_MARGIN

                cx = x_cursor
                cy = y_cursor
                zone_boxes[zone_id] = _Box(zone_id, cx, cy, zone_w, zone_h, row=row_num)

                inner_x = cx + COMPONENT_H_MARGIN
                inner_y = cy + header_h + ZONE_INNER_MARGIN
                for child in zone_children:
                    w = child.get("width") or child_w
                    h = _component_height(child)
                    component_boxes[child["id"]] = _Box(
                        child["id"], inner_x, inner_y, w, h, zone_id=zone_id, row=row_num
                    )
                    inner_x += w + ZONE_GAP

                x_cursor += zone_w + ZONE_GAP
                row_height = max(row_height, zone_h)

            else:
                zone_w = zone.get("width") or DEFAULT_ZONE_WIDTH
                inner_w = zone_w - 2 * COMPONENT_H_MARGIN
                child_y = y_cursor + header_h + ZONE_INNER_MARGIN
                for child in zone_children:
                    h = _component_height(child)
                    w = child.get("width") or inner_w
                    component_boxes[child["id"]] = _Box(
                        child["id"],
                        x_cursor + COMPONENT_H_MARGIN, child_y, w, h,
                        zone_id=zone_id, row=row_num,
                    )
                    child_y += h + COMPONENT_GAP

                content_bottom = (
                    child_y - COMPONENT_GAP if zone_children else y_cursor + header_h
                )
                zone_h = (content_bottom + ZONE_INNER_MARGIN) - y_cursor
                zone_boxes[zone_id] = _Box(zone_id, x_cursor, y_cursor, zone_w, zone_h, row=row_num)

                x_cursor += zone_w + ZONE_GAP
                row_height = max(row_height, zone_h)

        canvas_width = max(canvas_width, x_cursor - ZONE_GAP + PAGE_MARGIN)
        y_cursor += row_height + ROW_GAP

    canvas_height = y_cursor - ROW_GAP + PAGE_MARGIN
    return zone_boxes, component_boxes, canvas_width, canvas_height


def _route_edge(
    edge: Dict[str, Any],
    src: _Box,
    tgt: _Box,
    edge_index: int,
    row_bottoms: Dict[int, float],
) -> List[Tuple[float, float]]:
    """
    Returns a list of intermediate waypoints (possibly empty) for this edge,
    chosen so the route -- and therefore its default-midpoint label -- never
    passes through a box: same-zone edges use the fixed vertical gap between
    stacked components; different-zone-same-row edges use the fixed
    horizontal gap between columns; cross-row edges drop through the fixed
    horizontal channel between rows. All three gaps are reserved space no
    box is ever placed in, by construction.

    row_bottoms maps a row number to the bottom edge of the TALLEST zone in
    that row (not any single component's, and not even just its own zone's --
    a shorter zone in the same row would otherwise still have components
    poking into what should be the shared inter-row channel).
    """
    stagger = (edge_index % 5) * 8  # keeps multiple edges sharing a channel from drawing on top of each other

    if src.zone_id == tgt.zone_id and src.row == tgt.row:
        # Same zone: components are stacked vertically (or, for a horizontal
        # zone, side by side) -- either way they're immediate neighbors with
        # a reserved gap between them; mxGraph's own point-to-point routing
        # through that gap needs no explicit waypoint.
        return []

    if src.row == tgt.row:
        # Different zones, same row: route through the fixed horizontal gap
        # between the two zone columns -- the x midway between whichever
        # pair of edges actually face each other.
        if src.right <= tgt.x:
            gap_x = (src.right + tgt.x) / 2
        elif tgt.right <= src.x:
            gap_x = (tgt.right + src.x) / 2
        else:
            gap_x = (src.cx + tgt.cx) / 2
        gap_y = (src.cy + tgt.cy) / 2 + stagger
        return [(gap_x, gap_y)]

    # Different rows: drop into the horizontal channel between rows, travel
    # across it, then drop into the target. The channel sits below the
    # TALLEST zone in the upper row, regardless of which component/zone
    # within that row the edge actually starts from.
    upper_row = min(src.row, tgt.row)
    channel_y = row_bottoms[upper_row] + ROW_GAP / 2 + stagger
    return [(src.cx, channel_y), (tgt.cx, channel_y)]


def build_structured_drawio_xml(
    title: str,
    subtitle: Optional[str],
    zones: List[Dict[str, Any]],
    components: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> str:
    """
    The only function that turns structured content into drawio XML with
    real coordinates. Every box is guaranteed tall enough for its own text
    (see _component_height) and every edge is routed through space no box
    occupies (see _route_edge) -- both computed from the whole layout at
    once, not guessed one cell at a time.
    """
    zone_boxes, component_boxes, canvas_w, canvas_h = _layout_zones_and_components(
        zones, components
    )

    mxfile = ET.Element("mxfile", {"host": "Electron"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "structured", "name": title[:40] or "Architecture"})
    graph_model = ET.SubElement(diagram, "mxGraphModel", {
        "dx": "1600", "dy": "900", "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": str(int(canvas_w)), "pageHeight": str(int(canvas_h)),
        "math": "0", "shadow": "0",
    })
    root = ET.SubElement(graph_model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    # --- Title banner ---
    title_value = f"<b style=\"font-size:18px\">{title}</b>"
    if subtitle:
        title_value += f"<br/><span style=\"font-size:11px;color:#5f6368\">{subtitle}</span>"
    title_cell = ET.SubElement(root, "mxCell", {
        "id": "title_banner", "value": title_value, "vertex": "1", "parent": "1",
        "style": (
            "rounded=1;arcSize=4;fillColor=#FFFFFF;strokeColor=#4285F4;strokeWidth=1.5;"
            "html=1;whiteSpace=wrap;align=left;spacingLeft=20;verticalAlign=middle;"
        ),
    })
    ET.SubElement(title_cell, "mxGeometry", {
        "x": str(PAGE_MARGIN), "y": str(PAGE_MARGIN),
        "width": str(int(canvas_w - 2 * PAGE_MARGIN)), "height": str(TITLE_HEIGHT - 15),
        "as": "geometry",
    })

    # --- Zones ---
    for zone in zones:
        box = zone_boxes[zone["id"]]
        color = zone.get("color", DEFAULT_ZONE_COLOR)
        value = f"<b>{zone['label']}</b>"
        if zone.get("sublabel"):
            value += f"<br/><span style=\"font-size:10px;color:#5f6368\">{zone['sublabel']}</span>"
        header_h = _zone_header_height(zone)
        cell = ET.SubElement(root, "mxCell", {
            "id": zone["id"], "value": value, "vertex": "1", "parent": "1",
            "style": (
                f"swimlane;startSize={header_h};rounded=1;arcSize=4;fillColor=#F8F9FA;"
                f"strokeColor={color};strokeWidth=1.5;html=1;fontStyle=1;fontSize=12;"
                f"align=center;verticalAlign=middle;container=1;collapsible=0;"
            ),
        })
        ET.SubElement(cell, "mxGeometry", {
            "x": str(int(box.x)), "y": str(int(box.y)),
            "width": str(int(box.w)), "height": str(int(box.h)), "as": "geometry",
        })

    # --- Components (+ their icons) ---
    for component in components:
        box = component_boxes[component["id"]]
        zone_box = zone_boxes[component["zone_id"]]
        # Position relative to the zone (swimlane children use zone-local coords)
        local_x = box.x - zone_box.x
        local_y = box.y - zone_box.y

        has_icon = bool(component.get("shape"))
        spacing_top = SPACING_TOP_WITH_ICON if has_icon else SPACING_TOP_NO_ICON
        color = component.get("color", DEFAULT_COMPONENT_COLOR)
        value = _html_value(component["label"], component.get("bullets"))

        comp_cell = ET.SubElement(root, "mxCell", {
            "id": component["id"], "value": value, "vertex": "1", "parent": component["zone_id"],
            "style": (
                f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={color};"
                f"strokeWidth=1.5;verticalAlign=top;align=center;fontSize=11;fontColor=#202124;"
                f"spacingTop={spacing_top};"
            ),
        })
        ET.SubElement(comp_cell, "mxGeometry", {
            "x": str(int(local_x)), "y": str(int(local_y)),
            "width": str(int(box.w)), "height": str(int(box.h)), "as": "geometry",
        })

        if has_icon:
            icon_color = component.get("icon_color", color)
            icon_cell = ET.SubElement(root, "mxCell", {
                "id": f"{component['id']}_icon", "value": "", "vertex": "1", "parent": component["id"],
                "style": f"shape={component['shape']};fillColor={icon_color};strokeColor=none;html=1;",
            })
            ET.SubElement(icon_cell, "mxGeometry", {
                "x": str(int((box.w - ICON_SIZE) / 2)), "y": str(ICON_TOP_MARGIN),
                "width": str(ICON_SIZE), "height": str(ICON_SIZE), "as": "geometry",
            })

    # --- Edges ---
    all_boxes: Dict[str, _Box] = {**component_boxes, **zone_boxes}
    row_bottoms: Dict[int, float] = {}
    for zbox in zone_boxes.values():
        row_bottoms[zbox.row] = max(row_bottoms.get(zbox.row, 0.0), zbox.bottom)

    for i, edge in enumerate(edges):
        src = all_boxes.get(edge["source"])
        tgt = all_boxes.get(edge["target"])
        if src is None or tgt is None:
            continue  # dangling reference -- skip rather than emit a broken edge

        waypoints = _route_edge(edge, src, tgt, i, row_bottoms)
        label = edge.get("label", "")
        if edge.get("number") is not None and label:
            label = f"{edge['number']}. {label}"
        color = edge.get("color", "#5f6368")
        dashed = "dashed=1;" if edge.get("dashed") else ""

        edge_cell = ET.SubElement(root, "mxCell", {
            "id": f"edge_{i}_{edge['source']}_{edge['target']}",
            "value": f"<b>{label}</b>" if label else "",
            "edge": "1", "parent": "1", "source": edge["source"], "target": edge["target"],
            "style": (
                f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
                f"html=1;startArrow=classic;endArrow=classic;strokeColor={color};strokeWidth=2;"
                f"{dashed}fontColor=#202124;fontSize=10;labelBackgroundColor=#ffffff;"
            ),
        })
        geom = ET.SubElement(edge_cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        if waypoints:
            points_el = ET.SubElement(geom, "Array", {"as": "points"})
            for wx, wy in waypoints:
                ET.SubElement(points_el, "mxPoint", {"x": str(int(wx)), "y": str(int(wy))})

    return ET.tostring(mxfile, encoding="unicode")
