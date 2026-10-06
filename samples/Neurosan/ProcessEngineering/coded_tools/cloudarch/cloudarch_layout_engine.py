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

import math
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# LAYOUT CONSTANTS
# ============================================================
PAGE_MARGIN = 40
TITLE_HEIGHT = 70
ZONE_GAP = 50          # horizontal gap between row-0 (column) zones -- the
                        # reserved channel inter-zone edges route through
ROW_GAP = 60            # vertical gap between one row of zones and the next
                        # -- the reserved channel drop-down edges route through.
                        # Wider than the bare minimum so several staggered
                        # edge labels sharing one row boundary have room to
                        # separate without touching either zone's edge.
ZONE_HEADER_H_PLAIN = 45
ZONE_HEADER_H_SUBLABEL = 62
ZONE_INNER_MARGIN = 18   # margin inside a zone, above/below/beside its children
COMPONENT_GAP = 30       # vertical gap between stacked components in the
                        # same zone -- the reserved channel same-zone edges
                        # route through
COMPONENT_H_MARGIN = 26  # left/right margin inside a zone for its components --
                        # also the reserved channel non-adjacent same-zone
                        # edges route through (see _route_edge's "zone_skip"
                        # case), so it needs a bit more than pure visual
                        # breathing room
DEFAULT_ZONE_WIDTH = 340
ICON_SIZE = 56          # deliberately large/dominant -- matches official AWS/
                        # Azure/GCP Architecture Icons reference-diagram
                        # conventions, where the icon is the primary visual
                        # element, not a small decoration above a text block
ICON_TOP_MARGIN = 10
SPACING_TOP_WITH_ICON = ICON_TOP_MARGIN + ICON_SIZE + 8   # = 74, matches the
                        # formula given to the LLM elsewhere in this pipeline
SPACING_TOP_NO_ICON = 12
LINE_HEIGHT = 16
COMPONENT_BOTTOM_MARGIN = 20
DEFAULT_COMPONENT_COLOR = "#5F6368"  # neutral gray -- deliberately NOT a
                        # provider brand color (the old default, Google's
                        # own #4285F4 "Google Blue", silently tinted every
                        # AWS/Azure diagram whose components didn't
                        # explicitly set their own color) -- a safety net
                        # for a forgotten color, not a provider's identity
DEFAULT_ZONE_COLOR = "#5F6368"

# Stagger step sizes for edges that share a routing channel with other
# edges (see _channel_key/_stagger_offset). Each channel kind has very
# different amounts of real room to spread out in, so each gets its own
# step and, for the tightest channel, a hard clamp.
STAGGER_STEP_ZONE_GAP = 20    # horizontal inter-zone gap -- spans a whole
                               # row's height, so there's ample vertical room
STAGGER_STEP_ROW_GAP = 10     # inter-row channel -- bounded by ROW_GAP
ROW_GAP_STAGGER_CLAMP = ROW_GAP / 2 - 10  # never let a waypoint get within
                               # 10px of either zone edge bounding the channel
SAME_PAIR_OFFSET = 18         # perpendicular nudge for the 2nd+ edge between
                               # the exact same two components (e.g. a
                               # request/response pair) -- with no offset at
                               # all these would draw as two edges on the
                               # identical straight line, midpoint labels
                               # rendering on top of each other
ZONE_SKIP_STEP = 6            # stagger step within a zone's own side margin,
                               # for edges connecting NON-adjacent components
                               # in the same zone (see _route_edge)
ZONE_SKIP_CLAMP_VERTICAL = COMPONENT_H_MARGIN / 2 - 4
ZONE_SKIP_CLAMP_HORIZONTAL = ZONE_INNER_MARGIN / 2 - 4
SAFE_X_SEARCH_STEP = 6        # step size when _safe_x_for_vertical_span has
                               # to search away from its preferred x -- see
                               # that function's own docstring


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
    without re-deriving positions.

    order and stack are only meaningful for COMPONENT boxes: order is this
    component's position (0, 1, 2, ...) within its own zone's stacking
    order, and stack is that zone's "vertical"/"horizontal" arrangement --
    together they let the edge router tell whether two components in the
    same zone are immediate neighbors (safe to connect with a bare
    straight line through the gap between them) or not (a straight line
    would cut through every sibling box in between)."""
    __slots__ = ("id", "x", "y", "w", "h", "zone_id", "row", "order", "stack")

    def __init__(self, id_: str, x: float, y: float, w: float, h: float,
                 zone_id: Optional[str] = None, row: int = 0,
                 order: int = 0, stack: str = "vertical"):
        self.id = id_
        self.x, self.y, self.w, self.h = x, y, w, h
        self.zone_id = zone_id
        self.row = row
        self.order = order
        self.stack = stack

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


def _validate_unique_ids(zones: List[Dict[str, Any]], components: List[Dict[str, Any]]) -> None:
    """
    Every zone id and every component id must be unique across the WHOLE
    diagram, not just within its own zone -- edges, and this module's own
    id-keyed box lookups, both assume one id maps to exactly one box.

    A duplicate component id is silently destructive rather than merely
    wrong: component_boxes is a dict keyed by id, so the second component
    sharing an id overwrites the first's entry, and BOTH components (still
    two separate entries in the input list) end up emitted at the exact
    same coordinates -- two boxes' text and icons rendered on top of each
    other -- and any edge connected to that id gets routed against
    whichever one won the overwrite. This has been observed in practice:
    an LLM-generated payload reused an id (e.g. two different "Vertex..."
    services both called "vertex") across two conceptually-similar
    services, and the result was fused, unreadable overlapping boxes with
    edge labels bleeding into them. Failing loudly and immediately here,
    with the exact offending ids named, lets the caller fix its input
    instead of silently getting a corrupted diagram back.

    Same-kind duplicates (two zones sharing an id, or two components
    sharing an id) are the common case, but not the only way two boxes can
    collide: build_structured_drawio_xml's `all_boxes = {**component_boxes,
    **zone_boxes}` means a zone id equal to a component id lets one
    silently overwrite the other in that merge, and any component with a
    "shape" gets an auto-generated icon cell id of "<component id>_icon" --
    which collides just as destructively with a DIFFERENT component or
    zone that happens to already use that exact string as its own id.
    Every id that will actually end up as an XML id= attribute must be
    globally unique, across all of these sources at once.
    """
    zone_id_counts = Counter(z.get("id") for z in zones)
    component_id_counts = Counter(c.get("id") for c in components)
    dup_zone_ids = sorted(zid for zid, n in zone_id_counts.items() if zid is not None and n > 1)
    dup_component_ids = sorted(cid for cid, n in component_id_counts.items() if cid is not None and n > 1)

    zone_id_set = {zid for zid in zone_id_counts if zid is not None}
    component_id_set = {cid for cid in component_id_counts if cid is not None}
    icon_id_set = {
        f"{c['id']}_icon" for c in components
        if c.get("shape") and c.get("id") is not None
    }
    cross_collisions = sorted(
        (zone_id_set & component_id_set)
        | (icon_id_set & (zone_id_set | component_id_set))
    )

    if dup_zone_ids or dup_component_ids or cross_collisions:
        parts = []
        if dup_zone_ids:
            parts.append(f"duplicate zone id(s): {dup_zone_ids}")
        if dup_component_ids:
            parts.append(f"duplicate component id(s): {dup_component_ids}")
        if cross_collisions:
            parts.append(
                "id(s) reused across zones, components, or a component's "
                f"auto-generated icon cell id: {cross_collisions}"
            )
        raise ValueError(
            "Every zone id, component id, and component-generated icon id "
            "(\"<component id>_icon\") must be unique across the whole "
            "diagram -- " + "; ".join(parts) + ". Give each one a "
            "distinct id (e.g. a more specific suffix) and retry."
        )


def _zone_natural_width(zone: Dict[str, Any], zone_children: List[Dict[str, Any]]) -> float:
    """
    This zone's own width with NO row-level stretching applied -- an explicit
    override if given, else (for a horizontal-stack zone) however wide its
    own children actually need, else (vertical-stack) the plain default
    column width. Used to compute each row's natural total width in PASS 1
    of _layout_zones_and_components, and as the baseline every eligible
    zone in a short row gets stretched FROM in PASS 2.
    """
    if zone.get("width"):
        return zone["width"]
    if zone.get("stack", "vertical") == "horizontal":
        child_w = max(
            (c.get("width") or DEFAULT_ZONE_WIDTH for c in zone_children),
            default=DEFAULT_ZONE_WIDTH,
        )
        return (
            len(zone_children) * child_w
            + max(0, len(zone_children) - 1) * ZONE_GAP
            + 2 * COMPONENT_H_MARGIN
        )
    return DEFAULT_ZONE_WIDTH


def _layout_zones_and_components(
    zones: List[Dict[str, Any]], components: List[Dict[str, Any]]
) -> Tuple[Dict[str, _Box], Dict[str, _Box], float, float]:
    """
    Computes absolute boxes for every zone and every component.
    Returns (zone_boxes, component_boxes, canvas_width, canvas_height).

    Two passes, deliberately -- a single forward pass that stretches each
    row to "whatever canvas_width happens to be so far" was confirmed (in
    practice, against a real generated diagram) to compound: a row with two
    horizontal-stack zones, each independently stretching to the full width
    established by the row above, ends up roughly DOUBLE that width (not
    matching it) -- and that doubled width then becomes the next row's own
    stretch target, doubling again. Earlier, never-restretched rows are left
    stranded at a fraction of the final, inflated canvas width -- exactly
    the "wasted space" this was rewritten to fix.
    """
    _validate_unique_ids(zones, components)

    comps_by_zone: Dict[str, List[Dict[str, Any]]] = {}
    for c in components:
        comps_by_zone.setdefault(c["zone_id"], []).append(c)

    rows: Dict[int, List[Dict[str, Any]]] = {}
    for z in zones:
        rows.setdefault(int(z.get("row", 0)), []).append(z)

    def row_natural_width(row_zones: List[Dict[str, Any]]) -> float:
        widths = [_zone_natural_width(z, comps_by_zone.get(z["id"], [])) for z in row_zones]
        return sum(widths) + max(0, len(widths) - 1) * ZONE_GAP

    # PASS 1: the one true target content width every row should fill -- the
    # widest row's own natural (unstretched) width, computed once, up front,
    # from every row at once rather than incrementally from whatever's been
    # placed so far.
    target_width = max((row_natural_width(rows[r]) for r in rows), default=0.0)

    zone_boxes: Dict[str, _Box] = {}
    component_boxes: Dict[str, _Box] = {}

    y_cursor = PAGE_MARGIN + TITLE_HEIGHT
    canvas_width = PAGE_MARGIN + target_width

    # PASS 2: position every row, stretching it to target_width -- shared out
    # across THIS row's own eligible zones (any zone without an explicit
    # "width" override), not independently re-claimed in full by each one.
    # A row with no eligible zones (every zone has an explicit width) is
    # centered within target_width instead, so it reads as intentional
    # rather than stuck flush-left with space only on the right.
    for row_num in sorted(rows.keys()):
        row_zones = rows[row_num]
        natural_widths = {
            z["id"]: _zone_natural_width(z, comps_by_zone.get(z["id"], [])) for z in row_zones
        }
        row_natural_total = sum(natural_widths.values()) + max(0, len(row_zones) - 1) * ZONE_GAP
        shortfall = max(0.0, target_width - row_natural_total)

        eligible_ids = {z["id"] for z in row_zones if not z.get("width")}
        extra_per_eligible = shortfall / len(eligible_ids) if eligible_ids else 0.0
        row_x_offset = shortfall / 2 if not eligible_ids else 0.0  # center an unstretchable row

        x_cursor = PAGE_MARGIN + row_x_offset
        row_height = 0

        for zone in row_zones:
            zone_id = zone["id"]
            zone_children = comps_by_zone.get(zone_id, [])
            header_h = _zone_header_height(zone)
            stack = zone.get("stack", "vertical")
            zone_w = natural_widths[zone_id] + (
                extra_per_eligible if zone_id in eligible_ids else 0.0
            )

            if stack == "horizontal":
                child_w = max(
                    (c.get("width") or DEFAULT_ZONE_WIDTH for c in zone_children),
                    default=DEFAULT_ZONE_WIDTH,
                )
                content_h = max((_component_height(c) for c in zone_children), default=0)
                zone_h = header_h + content_h + 2 * ZONE_INNER_MARGIN

                cx = x_cursor
                cy = y_cursor
                zone_boxes[zone_id] = _Box(zone_id, cx, cy, zone_w, zone_h, row=row_num)

                # Redistribute any slack between zone_w and what the children
                # actually need as EXTRA GAP between them, so a stretched (or
                # explicitly wide) zone's children spread out to use its full
                # width instead of clustering at the left edge with dead
                # space past the last one.
                content_w = (
                    len(zone_children) * child_w
                    + max(0, len(zone_children) - 1) * ZONE_GAP
                    + 2 * COMPONENT_H_MARGIN
                )
                n = len(zone_children)
                if n == 0:
                    inner_x = cx + COMPONENT_H_MARGIN
                    gap = ZONE_GAP
                elif n == 1:
                    w0 = zone_children[0].get("width") or child_w
                    inner_x = cx + (zone_w - w0) / 2
                    gap = ZONE_GAP
                else:
                    inner_x = cx + COMPONENT_H_MARGIN
                    gap = ZONE_GAP + (zone_w - content_w) / (n - 1)
                inner_y = cy + header_h + ZONE_INNER_MARGIN
                for order_idx, child in enumerate(zone_children):
                    w = child.get("width") or child_w
                    h = _component_height(child)
                    component_boxes[child["id"]] = _Box(
                        child["id"], inner_x, inner_y, w, h, zone_id=zone_id, row=row_num,
                        order=order_idx, stack=stack,
                    )
                    inner_x += w + gap

                x_cursor += zone_w + ZONE_GAP
                row_height = max(row_height, zone_h)

            else:
                inner_w = zone_w - 2 * COMPONENT_H_MARGIN
                child_y = y_cursor + header_h + ZONE_INNER_MARGIN
                for order_idx, child in enumerate(zone_children):
                    h = _component_height(child)
                    w = child.get("width") or inner_w
                    component_boxes[child["id"]] = _Box(
                        child["id"],
                        x_cursor + COMPONENT_H_MARGIN, child_y, w, h,
                        zone_id=zone_id, row=row_num,
                        order=order_idx, stack=stack,
                    )
                    child_y += h + COMPONENT_GAP

                content_bottom = (
                    child_y - COMPONENT_GAP if zone_children else y_cursor + header_h
                )
                zone_h = (content_bottom + ZONE_INNER_MARGIN) - y_cursor
                zone_boxes[zone_id] = _Box(zone_id, x_cursor, y_cursor, zone_w, zone_h, row=row_num)

                x_cursor += zone_w + ZONE_GAP
                row_height = max(row_height, zone_h)

        y_cursor += row_height + ROW_GAP

    canvas_height = y_cursor - ROW_GAP + PAGE_MARGIN
    return zone_boxes, component_boxes, canvas_width, canvas_height


def _same_row_zones_adjacent(src: _Box, tgt: _Box, all_boxes: Dict[str, "_Box"]) -> bool:
    """
    Whether src's and tgt's own zones are immediate neighbors within their
    shared row -- True trivially if they're the same zone. Shared by
    _route_edge (to pick a routing strategy) and _channel_key (so edges
    that end up sharing the SAME physical channel because they're routed
    the same way -- see _route_edge -- also share a stagger channel, and
    don't coincidentally land on top of each other instead).
    """
    if src.zone_id == tgt.zone_id:
        return True
    row_zones = sorted(
        (b for b in all_boxes.values() if b.zone_id is None and b.row == src.row),
        key=lambda z: z.x,
    )
    src_zone = next((z for z in row_zones if z.id == src.zone_id), None)
    tgt_zone = next((z for z in row_zones if z.id == tgt.zone_id), None)
    if src_zone is None or tgt_zone is None:
        return True
    left_z, right_z = (src_zone, tgt_zone) if src_zone.x < tgt_zone.x else (tgt_zone, src_zone)
    return row_zones.index(right_z) - row_zones.index(left_z) == 1


def _channel_key(src: _Box, tgt: _Box, all_boxes: Dict[str, "_Box"]) -> Tuple[str, Any]:
    """
    Identifies which shared routing channel an edge falls into. Two edges
    with the same key will draw through the exact same reserved space (the
    same gap, the same inter-row band, or -- worst case -- the exact same
    straight line between two boxes) unless given different stagger slots,
    so this is the grouping _stagger_offset's slot-per-channel counter uses.

    Keys for the row-gap channel ("v") must match _route_edge's own choice
    of which row-gap it actually routes through -- confirmed directly
    against a real generated diagram that a same-row edge between
    non-adjacent zones and a cross-row edge landing in that SAME physical
    gap, but computing DIFFERENT channel keys, got no stagger coordination
    at all and rendered as overlapping lines.
    """
    # zone_id is None for zone-level boxes (a zone-to-zone edge), so the
    # None-vs-None case is excluded -- two DIFFERENT zones in the same row
    # must not be misread as "the same zone".
    if src.zone_id is not None and src.zone_id == tgt.zone_id and src.row == tgt.row:
        if abs(src.order - tgt.order) == 1:
            # Immediate neighbors in the zone's stack -- a request and its
            # response between this identical pair draw the identical
            # straight line with no waypoint at all otherwise, so this is
            # its own, tightest channel.
            return ("pair", frozenset({src.id, tgt.id}))
        # Non-adjacent components in the same zone all share the same
        # reserved margin channel (see _route_edge) regardless of which
        # specific pair -- grouped by zone so they still fan out from
        # each other rather than overlapping by coincidence.
        return ("zone_skip", src.zone_id)
    if src.row == tgt.row:
        if _same_row_zones_adjacent(src, tgt, all_boxes):
            return ("h", frozenset({src.zone_id, tgt.zone_id}))
        # Routed via this row's own below-row channel, same as a cross-row
        # edge leaving this row -- see _route_edge.
        return ("v", src.row)
    return ("v", max(src.row, tgt.row) - 1)


def _stagger_offset(slot: int, step: float, clamp: Optional[float] = None) -> float:
    """
    Maps a per-channel slot index (0, 1, 2, ...) to a signed offset that
    alternates and grows outward from the channel's center: 0, +step,
    -step, +2*step, -2*step, ... so edges sharing a channel fan out evenly
    on both sides of the "natural" route instead of drifting one direction.
    """
    if slot == 0:
        return 0.0
    magnitude = ((slot + 1) // 2) * step
    if clamp is not None:
        magnitude = min(magnitude, clamp)
    return magnitude if slot % 2 == 1 else -magnitude


def _safe_x_for_vertical_span(
    preferred_x: float,
    y_lo: float,
    y_hi: float,
    exclude_ids: Tuple[str, str],
    all_boxes: Dict[str, "_Box"],
) -> float:
    """
    An x-coordinate, as close to `preferred_x` as possible, that no
    component (other than `exclude_ids`, the edge's own source and target)
    occupies anywhere across the vertical span [y_lo, y_hi].

    _route_edge's same-row-different-zone and different-row branches both
    route a long vertical leg through a single x -- previously always
    src.cx/tgt.cx, or the raw midpoint between two facing box edges, on the
    assumption that coordinate is automatically clear. Confirmed directly
    against a real generated diagram that it often isn't: (a) a component
    with siblings stacked between it and the direction of travel (e.g. the
    first of several stacked components routing down to a later row) shares
    its own x with those siblings, and (b) a same-row edge between two
    zones that are NOT actually adjacent (another zone sits between them)
    had its naive midpoint land inside that intervening zone. Both render
    as a line cutting straight through an unrelated box.

    Searches outward in fixed steps rather than solving analytically, since
    the obstacle can be an arbitrary mix of same-zone siblings and
    unrelated zones' own components -- when `preferred_x` is already clear
    (the common case), this returns it immediately, so every previously
    correct route is unchanged.
    """
    def blocked(x: float) -> bool:
        for box_id, box in all_boxes.items():
            if box_id in exclude_ids or box.zone_id is None:
                continue  # zone containers aren't obstacles, only components
            if box.x <= x <= box.right and box.y < y_hi and box.bottom > y_lo:
                return True
        return False

    if not blocked(preferred_x):
        return preferred_x
    for step in range(1, 300):
        for candidate in (preferred_x - step * SAFE_X_SEARCH_STEP, preferred_x + step * SAFE_X_SEARCH_STEP):
            if not blocked(candidate):
                return candidate
    return preferred_x  # exhausted the search -- fall back rather than loop forever


def _route_edge(
    edge: Dict[str, Any],
    src: _Box,
    tgt: _Box,
    channel_slot: int,
    row_bottoms: Dict[int, float],
    all_boxes: Dict[str, "_Box"],
) -> Tuple[List[Tuple[float, float]], str, str]:
    """
    Returns (waypoints, exit_side, entry_side) for this edge, chosen so the
    route -- and therefore its default-midpoint label -- never passes
    through a box: adjacent same-zone edges use the fixed gap between
    neighboring stacked components; non-adjacent same-zone edges use the
    zone's own side margin; different-zone-same-row and different-row edges
    route through a shared x/y channel that is VERIFIED clear (see
    _safe_x_for_vertical_span) rather than assumed clear, since real
    diagrams showed both of those previously cutting straight through a
    box: a same-row edge between two zones that are not actually adjacent
    (another zone sits between them) landed its naive midpoint inside that
    intervening zone, and a cross-row edge from a component with siblings
    stacked between it and the direction of travel (or skipping an entire
    intervening row's own zone) shared its exit/entry x with those boxes.

    exit_side/entry_side ("left"/"right"/"top"/"bottom") are each branch's
    OWN, explicit, known-by-construction choice -- NOT inferred after the
    fact from a waypoint's raw position relative to the box center (the
    previous approach, via _connection_side). That inference breaks for
    the two channel-routed branches below once _safe_x_for_vertical_span
    has to search far from a box's own center to dodge an obstacle: the
    found x can end up far enough from the box's cx that a comparison of
    |dx| vs |dy| flips to "left"/"right" even though the edge is
    conceptually a vertical, top/bottom-flowing one -- confirmed directly
    against a real generated diagram rendering as a diagonal line jumping
    from a box's LEFT-center straight to a point far below and to the
    right of it, instead of a clean right-angle drop from its bottom edge.

    row_bottoms maps a row number to the bottom edge of the TALLEST zone in
    that row (not any single component's, and not even just its own zone's --
    a shorter zone in the same row would otherwise still have components
    poking into what should be the shared inter-row channel).

    channel_slot is this edge's position (0, 1, 2, ...) among all edges that
    share its _channel_key -- the caller assigns these per-channel, not
    globally, so two edges sharing a channel always get visibly different
    offsets regardless of how many unrelated edges exist elsewhere.

    all_boxes is every zone's and every component's own box, keyed by id --
    needed to verify a candidate route coordinate is actually clear of every
    OTHER component, not just the ones src/tgt's own zone or row would
    suggest.
    """
    # zone_id is None for zone-level boxes themselves (a zone-to-zone
    # edge), so the None-vs-None check below must be excluded explicitly --
    # otherwise two DIFFERENT zones in the same row would be misread as
    # "the same zone" and fall into logic keyed off a component's own
    # margin, which doesn't apply to a zone box at all.
    if src.zone_id is not None and src.zone_id == tgt.zone_id and src.row == tgt.row:
        if src.stack == "horizontal":
            exit_side, entry_side = ("right", "left") if tgt.order > src.order else ("left", "right")
        else:
            exit_side, entry_side = ("bottom", "top") if tgt.order > src.order else ("top", "bottom")

        if abs(src.order - tgt.order) == 1:
            if channel_slot == 0:
                # The common case: a single edge between immediate
                # neighbors draws a plain straight line through the
                # reserved inter-component gap, no waypoint needed.
                return [], exit_side, entry_side
            # A 2nd+ edge between the identical pair (e.g. a reply edge)
            # would otherwise draw on the exact same line -- nudge it
            # perpendicular to whichever axis the two boxes are actually
            # separated along. The nudge is perpendicular to the PRIMARY
            # separation axis, so it never changes which side the edge
            # conceptually leaves/enters from.
            mid_x = (src.cx + tgt.cx) / 2
            mid_y = (src.cy + tgt.cy) / 2
            offset = _stagger_offset(channel_slot, SAME_PAIR_OFFSET)
            if abs(tgt.cy - src.cy) >= abs(tgt.cx - src.cx):
                return [(mid_x + offset, mid_y)], exit_side, entry_side
            return [(mid_x, mid_y + offset)], exit_side, entry_side

        # Non-adjacent components in the same zone: a bare straight line
        # between them would cut straight through every sibling box
        # stacked in between. Every component in a zone shares the same
        # left edge (vertical stack) or the same top edge (horizontal
        # stack), so the thin margin strip just inside the zone border is
        # reserved space no component ever occupies -- route through that
        # instead, exactly like the cross-zone/cross-row channels below.
        if src.stack == "horizontal":
            offset = _stagger_offset(channel_slot, ZONE_SKIP_STEP, clamp=ZONE_SKIP_CLAMP_HORIZONTAL)
            margin_y = src.y - ZONE_INNER_MARGIN / 2 + offset
            return [(src.cx, margin_y), (tgt.cx, margin_y)], "top", "top"
        offset = _stagger_offset(channel_slot, ZONE_SKIP_STEP, clamp=ZONE_SKIP_CLAMP_VERTICAL)
        margin_x = src.x - COMPONENT_H_MARGIN / 2 + offset
        return [(margin_x, src.cy), (margin_x, tgt.cy)], "left", "left"

    if src.row == tgt.row:
        if _same_row_zones_adjacent(src, tgt, all_boxes):
            # Different zones, same row, immediate neighbors: route through
            # the horizontal gap between the two zone columns -- the x
            # midway between whichever pair of edges actually face each
            # other. Verified (and corrected if needed) against every
            # component in the row rather than trusted outright, since a
            # sibling edge's stagger can still push this x into a shorter
            # row-mate zone's interior.
            if src.right <= tgt.x:
                base_gap_x = (src.right + tgt.x) / 2
                exit_side, entry_side = "right", "left"
            elif tgt.right <= src.x:
                base_gap_x = (tgt.right + src.x) / 2
                exit_side, entry_side = "left", "right"
            else:
                base_gap_x = (src.cx + tgt.cx) / 2
                exit_side, entry_side = ("right", "left") if tgt.cx >= src.cx else ("left", "right")
            naive_gap_x = base_gap_x + _stagger_offset(channel_slot, STAGGER_STEP_ZONE_GAP)
            row_zones = [b for b in all_boxes.values() if b.zone_id is None and b.row == src.row]
            row_y_lo = min((z.y for z in row_zones), default=src.y)
            row_y_hi = max((z.bottom for z in row_zones), default=src.bottom)
            gap_x = _safe_x_for_vertical_span(naive_gap_x, row_y_lo, row_y_hi, (src.id, tgt.id), all_boxes)
            if src.cy == tgt.cy:
                # Already vertically aligned -- a single waypoint at the
                # shared y is already a clean right-angle path (exit ->
                # waypoint is horizontal, waypoint -> entry is horizontal,
                # no vertical segment needed at all).
                return [(gap_x, src.cy)], exit_side, entry_side
            # NOT vertically aligned (the common case -- src/tgt are rarely
            # at the exact same stack position within their own,
            # independently-stacked zones). A SINGLE waypoint at the
            # midpoint of the two centers was the previous approach here,
            # but that produces two DIAGONAL segments (confirmed against a
            # real generated diagram: exit and entry points are each
            # pinned to their own box's own cy, which does not equal the
            # midpoint y, so neither segment ends up horizontal OR
            # vertical). Two waypoints at the SAME gap_x instead give three
            # axis-aligned segments: exit (src's own cy) -> horizontal ->
            # (gap_x, src.cy) -> vertical -> (gap_x, tgt.cy) -> horizontal
            # -> entry (tgt's own cy).
            return [(gap_x, src.cy), (gap_x, tgt.cy)], exit_side, entry_side

        # Same row, but NOT immediate neighbors -- at least one other zone
        # sits between src's and tgt's own zones. A "safe" gap_x found by
        # search still needs a horizontal leg connecting it to src/tgt at
        # their own cy, and that leg would cut straight through the
        # intervening zone's content at that height. Confirmed directly
        # against a real generated diagram: a "same row" edge between two
        # non-adjacent zones rendered as a line slicing through whatever
        # component happened to occupy the zone physically between them.
        # Routed instead through this row's own below-row channel, exactly
        # like the cross-row case below -- reserved, clear space across
        # the FULL row width, so no interior zone is ever in the way. Both
        # ends connect from their own BOTTOM edge (dropping into, then
        # rising back out of, that below-row channel).
        channel_y = row_bottoms[src.row] + ROW_GAP / 2 + _stagger_offset(
            channel_slot, STAGGER_STEP_ROW_GAP, clamp=ROW_GAP_STAGGER_CLAMP
        )
        exit_x = _safe_x_for_vertical_span(
            src.cx, min(src.cy, channel_y), max(src.cy, channel_y), (src.id, tgt.id), all_boxes
        )
        entry_x = _safe_x_for_vertical_span(
            tgt.cx, min(tgt.cy, channel_y), max(tgt.cy, channel_y), (src.id, tgt.id), all_boxes
        )
        return [(exit_x, channel_y), (entry_x, channel_y)], "bottom", "bottom"

    # Different rows: drop into the horizontal channel immediately ABOVE
    # whichever of src/tgt is in the lower (higher row-number) row, travel
    # across it, then drop into the target. Anchoring to the row right
    # before the lower one (rather than the row right after the upper one)
    # means this is still a single reserved, always-clear channel even
    # when the edge SKIPS an entire intervening row -- e.g. row 0 straight
    # to row 2 -- where the two would otherwise differ.
    #
    # The two vertical legs (src down/up to the channel, and the channel
    # down/up into tgt) are NOT guaranteed clear at src.cx/tgt.cx, though:
    # a component with siblings stacked between it and the direction of
    # travel shares its own x with them, and a leg spanning a SKIPPED
    # row's own zone can land inside whatever that zone's own components
    # occupy at that x. Both confirmed directly against a real generated
    # diagram. Each leg's x is therefore verified (and nudged aside if
    # needed) against every component its own vertical span actually
    # passes, same as the same-row branch above -- the horizontal segment
    # at channel_y itself needs no such check, since that gap is reserved
    # and clear at every x, by construction, regardless of row count.
    going_down = src.row < tgt.row
    exit_side, entry_side = ("bottom", "top") if going_down else ("top", "bottom")
    lower_row = max(src.row, tgt.row)
    channel_y = row_bottoms[lower_row - 1] + ROW_GAP / 2 + _stagger_offset(
        channel_slot, STAGGER_STEP_ROW_GAP, clamp=ROW_GAP_STAGGER_CLAMP
    )
    exit_x = _safe_x_for_vertical_span(
        src.cx, min(src.cy, channel_y), max(src.cy, channel_y), (src.id, tgt.id), all_boxes
    )
    entry_x = _safe_x_for_vertical_span(
        tgt.cx, min(tgt.cy, channel_y), max(tgt.cy, channel_y), (src.id, tgt.id), all_boxes
    )
    return [(exit_x, channel_y), (entry_x, channel_y)], exit_side, entry_side


def _slot_fraction(slot_index: int, slot_count: int) -> float:
    """
    Evenly spaced fractional position along one side of a box for this
    edge, among `slot_count` edges total sharing that same box+side.
    Stays inside [0.2, 0.8] so no connection point sits right at a
    corner; slot_count <= 1 is the common case (one edge on this side)
    and stays dead-center, matching the old fixed-0.5 behavior exactly.
    """
    if slot_count <= 1:
        return 0.5
    lo, hi = 0.2, 0.8
    return lo + (hi - lo) * slot_index / (slot_count - 1)


def _connection_point_for_side(side: str, fraction: float) -> Tuple[float, float]:
    """Converts a side + along-side fraction into the (fractional X,
    fractional Y) box-boundary point drawio's exitX/exitY/entryX/entryY
    expect."""
    if side == "right":
        return (1.0, fraction)
    if side == "left":
        return (0.0, fraction)
    if side == "bottom":
        return (fraction, 1.0)
    return (fraction, 0.0)  # "top"


def _assign_connection_slots(
    edges: List[Dict[str, Any]],
    all_boxes: Dict[str, "_Box"],
    row_bottoms: Dict[int, float],
    channel_slots: List[int],
) -> List[Optional[Dict[str, Any]]]:
    """
    Pre-computes, for every edge, its waypoints AND which exact fractional
    point on its source/target box it connects to -- spreading multiple
    edges that share the same box+side across that side instead of every
    one of them pinning to the identical center point.

    Without this, two or more edges leaving/entering the same box toward
    the same general direction (e.g. one API Gateway fanning out to two
    availability-zone clusters) all got the IDENTICAL connection point --
    confirmed directly against a real generated diagram: their line
    segments visibly coincide near the shared box, and their labels (both
    anchored near that shared segment) read as doubled, overlapping text.

    Returns a list (parallel to `edges`) of {"waypoints", "exit_frac",
    "entry_frac"} dicts, or None for a dangling edge reference.
    """
    raw: List[Optional[Dict[str, Any]]] = []
    for i, edge in enumerate(edges):
        src = all_boxes.get(edge["source"])
        tgt = all_boxes.get(edge["target"])
        if src is None or tgt is None:
            raw.append(None)
            continue
        waypoints, exit_side, entry_side = _route_edge(edge, src, tgt, channel_slots[i], row_bottoms, all_boxes)
        raw.append({
            "waypoints": waypoints,
            "exit_side": exit_side,
            "entry_side": entry_side,
        })

    # Group every edge-endpoint touching a given (box, side) together, so
    # slots can be assigned per side rather than per individual edge.
    groups: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}
    for i, edge in enumerate(edges):
        r = raw[i]
        if r is None:
            continue
        groups.setdefault((edge["source"], r["exit_side"]), []).append((i, "exit"))
        groups.setdefault((edge["target"], r["entry_side"]), []).append((i, "entry"))

    exit_frac: List[Optional[Tuple[float, float]]] = [None] * len(edges)
    entry_frac: List[Optional[Tuple[float, float]]] = [None] * len(edges)

    for (box_id, side), items in groups.items():
        vertical_side = side in ("left", "right")

        def _sort_key(item: Tuple[int, str]) -> float:
            idx, role = item
            other_id = edges[idx]["target"] if role == "exit" else edges[idx]["source"]
            other_box = all_boxes[other_id]
            # Sort by the OTHER endpoint's perpendicular coordinate, so
            # slots are assigned in a spatially sensible order (the edge
            # going to the topmost target gets the topmost slot, etc.)
            # instead of arbitrary edge-list order, which would cross
            # lines unnecessarily.
            return other_box.cy if vertical_side else other_box.cx

        ordered = sorted(items, key=_sort_key)
        for slot, (idx, role) in enumerate(ordered):
            point = _connection_point_for_side(side, _slot_fraction(slot, len(ordered)))
            if role == "exit":
                exit_frac[idx] = point
            else:
                entry_frac[idx] = point

    result: List[Optional[Dict[str, Any]]] = []
    for i, r in enumerate(raw):
        if r is None:
            result.append(None)
            continue
        src = all_boxes[edges[i]["source"]]
        tgt = all_boxes[edges[i]["target"]]
        exit_pt = (src.x + exit_frac[i][0] * src.w, src.y + exit_frac[i][1] * src.h)
        entry_pt = (tgt.x + entry_frac[i][0] * tgt.w, tgt.y + entry_frac[i][1] * tgt.h)
        waypoints = _reconcile_connection_points(
            r["waypoints"], r["exit_side"], r["entry_side"], exit_pt, entry_pt
        )
        result.append({**r, "waypoints": waypoints, "exit_frac": exit_frac[i], "entry_frac": entry_frac[i]})
    return result


def _reconcile_connection_points(
    waypoints: List[Tuple[float, float]],
    exit_side: str,
    entry_side: str,
    exit_point: Tuple[float, float],
    entry_point: Tuple[float, float],
) -> List[Tuple[float, float]]:
    """
    Rebuilds `waypoints` so the path actually starts at `exit_point` and
    ends at `entry_point` -- the REAL, slot-assigned connection pixels
    (see the slot-spreading loop just above) -- with every segment axis-
    aligned, inserting a jog at either end if needed.

    _route_edge computes its own waypoints using each box's CENTER as an
    assumed connection point; `_slot_fraction`'s later spreading can move
    the ACTUAL connection point elsewhere along that side whenever more
    than one edge shares a box+side, with nothing reconciling the two.
    Confirmed directly against a real generated diagram: a box with two
    outgoing edges on the same side (correctly spread apart, each at its
    own point along that edge, by the Bug #2 fix) had EVERY edge touching
    it render as a diagonal line cutting in from an angle, because each
    edge's own route was still built assuming it started from the box's
    center.
    """
    def _jog(side: str, point: Tuple[float, float], anchor: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        # "top"/"bottom" pin the box's Y (point.y); the connection point's
        # X is the only coordinate slot-spreading can have moved, so no
        # jog is needed if anchor already shares that X. When it doesn't,
        # the jog must sit at (anchor.x, point.y) -- NOT (point.x,
        # anchor.y) -- so the segment from `point` is a short HORIZONTAL
        # hop along the box's own edge to the anchor's (already verified
        # safe, see _safe_x_for_vertical_span) x, before the EXISTING,
        # pre-verified segment from the jog to `anchor` takes over. The
        # reverse choice would instead draw a brand new, unverified
        # VERTICAL segment straight down from the box edge at the
        # connection point's own x -- confirmed directly against a real
        # generated diagram to cut straight through boxes nothing had
        # ever checked that specific x against.
        px, py = point
        ax, ay = anchor
        if side in ("top", "bottom"):
            return None if ax == px else (ax, py)
        return None if ay == py else (px, ay)

    path = list(waypoints)
    if path:
        exit_jog = _jog(exit_side, exit_point, path[0])
        if exit_jog is not None:
            path.insert(0, exit_jog)
        entry_jog = _jog(entry_side, entry_point, path[-1])
        if entry_jog is not None:
            path.append(entry_jog)
        return path

    # No internal waypoints at all -- the route was a bare straight line
    # directly between the two boxes' own (assumed-center) connection
    # points (e.g. immediate same-zone neighbors). If the ACTUAL
    # connection points no longer share the coordinate that made that
    # line axis-aligned, route through the midpoint between the two box
    # edges instead -- the same shape already used for a 2nd+ edge
    # between an identical pair, and safe for the same reason: this is a
    # short hop between immediate neighbors, through the reserved gap
    # between them, which nothing is ever placed in.
    ex, ey = exit_point
    enx, eny = entry_point
    if exit_side in ("top", "bottom"):
        if ex == enx:
            return []
        mid_y = (ey + eny) / 2
        return [(ex, mid_y), (enx, mid_y)]
    if ey == eny:
        return []
    mid_x = (ex + enx) / 2
    return [(mid_x, ey), (mid_x, eny)]


def _resolve_label_collisions(
    label_points: List[Optional[Tuple[float, float]]],
    threshold: float = 40.0,
) -> List[Optional[Tuple[float, float]]]:
    """
    Nudges labels that land within `threshold` px of another label apart
    so they end up EXACTLY `threshold` px apart, alternating perpendicular
    to the line between the colliding pair.

    _label_position_fraction only keeps a label off corners/bends on its
    OWN edge's path -- it has no visibility into where every OTHER edge's
    label lands, so two entirely unrelated edges (different source AND
    target) can still coincidentally compute to nearly the same point, as
    confirmed directly against a real generated diagram (two labels 5px
    apart). A single O(n^2) pass over the handful of labels a real diagram
    has is a deliberate, cheap choice over an iterative constraint solver
    -- this is a cosmetic nudge away from a near-coincidence, not a
    general label-layout optimizer, so one pass resolving each label at
    most once is enough to fix the real collisions observed without
    risking the nudges themselves cascading into new ones.

    The nudge distance is derived from `threshold` itself (via
    `sqrt(threshold**2 - dist**2)`) rather than a fixed pixel amount --
    a fixed nudge only guarantees the two points end up `nudge` px apart
    in the worst case (two points starting at the exact same spot, where
    no direction is defined to add to), which can still be well under
    `threshold` and therefore still read as a collision after "fixing" it.
    """
    adjusted = list(label_points)
    already_nudged = [False] * len(adjusted)

    for i in range(len(adjusted)):
        for j in range(i + 1, len(adjusted)):
            if already_nudged[i] or already_nudged[j]:
                continue
            pi, pj = adjusted[i], adjusted[j]
            if pi is None or pj is None:
                continue
            dx, dy = pj[0] - pi[0], pj[1] - pi[1]
            dist = math.hypot(dx, dy)
            if dist >= threshold:
                continue
            # Perpendicular unit vector to the line between the two
            # points (falls back to a horizontal nudge for two points
            # that coincide exactly, where no direction is defined).
            if dist > 0:
                perp_x, perp_y = -dy / dist, dx / dist
            else:
                perp_x, perp_y = 1.0, 0.0
            # Total perpendicular separation needed so the final distance
            # (hypotenuse of the original gap and this added perpendicular
            # push) comes out to exactly `threshold`.
            nudge = math.sqrt(max(threshold * threshold - dist * dist, 0.0))
            adjusted[i] = (pi[0] - perp_x * nudge / 2, pi[1] - perp_y * nudge / 2)
            adjusted[j] = (pj[0] + perp_x * nudge / 2, pj[1] + perp_y * nudge / 2)
            already_nudged[i] = already_nudged[j] = True

    return adjusted


def _label_position_fraction(path: List[Tuple[float, float]]) -> float:
    """
    Returns an mxGraph edge-label "x" value (relative position along the
    edge, -1.0 at the source end through 0.0 at the middle to 1.0 at the
    target end) that lands at the MIDPOINT OF THE LONGEST STRAIGHT SEGMENT
    of `path`, rather than drawio's own default -- the midpoint by raw arc
    length of the whole polyline.

    Confirmed directly (see cloudarch_layout_engine's own test suite) that
    the two disagree by a wide margin on exactly the edges this router
    bends hardest: a 3-segment cross-row/cross-zone path's short first leg
    and long middle leg can put the arc-length midpoint barely past the
    first corner -- right where the route jogs through the gap BETWEEN two
    zones, which is exactly where a zone's own border line sits. The
    longest segment is, by construction, the one furthest from either
    corner, so its own midpoint is the one spot on the path guaranteed not
    to sit on top of a bend or a box edge.
    """
    seg_lengths = [math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
    total = sum(seg_lengths)
    if total <= 0:
        return 0.0

    longest_idx = max(range(len(seg_lengths)), key=lambda i: seg_lengths[i])
    arc_before_longest = sum(seg_lengths[:longest_idx])
    midpoint_arc_position = arc_before_longest + seg_lengths[longest_idx] / 2

    fraction_0_to_1 = midpoint_arc_position / total
    return 2 * fraction_0_to_1 - 1


def _point_at_fraction(path: List[Tuple[float, float]], fraction: float) -> Tuple[float, float]:
    """
    The inverse of _label_position_fraction: the absolute (x, y) point
    along `path` that a given mxGraph label fraction (-1.0 source .. 1.0
    target) actually lands on. Used to recover real pixel positions for
    every edge's label so collisions BETWEEN edges can be detected -- see
    _resolve_label_collisions.
    """
    seg_lengths = [math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
    total = sum(seg_lengths)
    if total <= 0:
        return path[0]

    target_arc = (fraction + 1) / 2 * total
    covered = 0.0
    for i, seg_len in enumerate(seg_lengths):
        if covered + seg_len >= target_arc or i == len(seg_lengths) - 1:
            t = (target_arc - covered) / seg_len if seg_len > 0 else 0.0
            x0, y0 = path[i]
            x1, y1 = path[i + 1]
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        covered += seg_len
    return path[-1]


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
        "math": "0", "shadow": "0", "background": "#FFFFFF",
        # Explicit white page background -- without it, the canvas renders
        # using whatever theme the viewer/exporter happens to be in (e.g. a
        # dark-mode drawio client), which turns the deliberately white,
        # light-bordered boxes into stark cards floating on a black void.
        # A professional architecture diagram should look the same
        # regardless of the viewer's own theme.
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
                f"swimlaneFillColor=#F8F9FA;"
                # swimlaneFillColor is mxgraph's own style key for a swimlane's BODY/
                # lane area, distinct from fillColor (which some renderers apply only
                # to the header bar for a swimlane-shaped cell) -- set both to the
                # same value so the body fill can't silently fall through to
                # whatever's behind the canvas regardless of which one a given
                # viewer actually honors.
                f"strokeColor={color};strokeWidth=2;html=1;fontStyle=1;fontSize=12;"
                f"fontColor=#202124;align=center;verticalAlign=middle;container=1;collapsible=0;"
                # fontColor was previously left unset on this swimlane header title,
                # which has been observed to render pale/near-illegible against the
                # light header fill -- pin it explicitly rather than rely on
                # whatever default a given viewer falls back to.
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

        if has_icon:
            # No visible box around an icon-bearing component -- just the icon with its
            # title/caption underneath, floating on the zone's own background. Matches
            # professional AWS/Azure/GCP reference diagrams, which reserve a bordered box
            # for GROUPING containers (zones) and render individual resource icons
            # borderless. Geometry (box.w/box.h, spacing_top) is unchanged -- only the
            # visible fill/stroke disappear, so overlap-prevention and edge routing (both
            # computed from this same reserved box) are completely unaffected.
            box_style = (
                f"whiteSpace=wrap;html=1;fillColor=none;strokeColor=none;"
                f"verticalAlign=top;align=center;fontSize=11;fontColor=#202124;"
                f"spacingTop={spacing_top};"
            )
        else:
            # No icon -- keep the bordered box. Without an icon, a borderless floating
            # text label wouldn't read as a distinct component at all; the box is what
            # visually anchors it.
            box_style = (
                f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={color};"
                f"strokeWidth=1.5;verticalAlign=top;align=center;fontSize=11;fontColor=#202124;"
                f"spacingTop={spacing_top};"
            )

        comp_cell = ET.SubElement(root, "mxCell", {
            "id": component["id"], "value": value, "vertex": "1", "parent": component["zone_id"],
            "style": box_style,
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

    # Assign each edge a slot number (0, 1, 2, ...) local to the channel it
    # shares with other edges, so edges converging on the same gap/band/pair
    # get visibly different offsets regardless of their absolute position in
    # the edges list -- a global counter (the previous approach) could put
    # two edges sharing a channel arbitrarily far apart in index and give
    # them the same offset by coincidence.
    channel_slot_counts: Dict[Tuple[str, Any], int] = {}
    channel_slots: List[int] = []
    for edge in edges:
        src = all_boxes.get(edge["source"])
        tgt = all_boxes.get(edge["target"])
        if src is None or tgt is None:
            channel_slots.append(0)
            continue
        key = _channel_key(src, tgt, all_boxes)
        slot = channel_slot_counts.get(key, 0)
        channel_slot_counts[key] = slot + 1
        channel_slots.append(slot)

    # Pin exact connection points instead of letting drawio float them, and
    # spread multiple edges sharing a box+side across that side -- see
    # _assign_connection_slots's own docstring for why.
    edge_plans = _assign_connection_slots(edges, all_boxes, row_bottoms, channel_slots)

    # Compute every edge's absolute label point UP FRONT, across all edges,
    # so collisions BETWEEN unrelated edges (not just within one edge's own
    # bent path) can be detected and nudged apart -- see
    # _resolve_label_collisions's own docstring for why this has to be a
    # separate pass rather than resolved edge-by-edge.
    label_fractions: List[Optional[float]] = [None] * len(edges)
    raw_label_points: List[Optional[Tuple[float, float]]] = [None] * len(edges)
    for i, edge in enumerate(edges):
        plan = edge_plans[i]
        src = all_boxes.get(edge["source"])
        tgt = all_boxes.get(edge["target"])
        if plan is None or src is None or tgt is None:
            continue
        exit_x, exit_y = plan["exit_frac"]
        entry_x, entry_y = plan["entry_frac"]
        exit_pt = (src.x + exit_x * src.w, src.y + exit_y * src.h)
        entry_pt = (tgt.x + entry_x * tgt.w, tgt.y + entry_y * tgt.h)
        path = [exit_pt, *plan["waypoints"], entry_pt]
        fraction = _label_position_fraction(path)
        label_fractions[i] = fraction
        raw_label_points[i] = _point_at_fraction(path, fraction)

    resolved_label_points = _resolve_label_collisions(raw_label_points)

    for i, edge in enumerate(edges):
        plan = edge_plans[i]
        src = all_boxes.get(edge["source"])
        tgt = all_boxes.get(edge["target"])
        if plan is None or src is None or tgt is None:
            continue  # dangling reference -- skip rather than emit a broken edge

        waypoints = plan["waypoints"]
        label = edge.get("label", "")
        if edge.get("number") is not None and label:
            label = f"{edge['number']}. {label}"
        color = edge.get("color", "#5f6368")
        dashed = "dashed=1;" if edge.get("dashed") else ""

        exit_x, exit_y = plan["exit_frac"]
        entry_x, entry_y = plan["entry_frac"]
        label_fraction = label_fractions[i]

        edge_cell = ET.SubElement(root, "mxCell", {
            "id": f"edge_{i}_{edge['source']}_{edge['target']}",
            "value": f"<b>{label}</b>" if label else "",
            "edge": "1", "parent": "1", "source": edge["source"], "target": edge["target"],
            "style": (
                # Deliberately NOT edgeStyle=orthogonalEdgeStyle -- that is drawio's
                # own AUTOMATIC router, which computes (and can override) its own
                # path rather than reliably treating our waypoints/connection
                # points as literal, especially crossing a swimlane/container
                # boundary. Our own _route_edge waypoints are already constructed
                # to form clean right-angle paths (consecutive points deliberately
                # share an X or Y coordinate) -- a plain polyline through our exact
                # points (no edgeStyle at all) draws the same right-angle shape
                # without handing any interpretation authority to an auto-router
                # that has been observed to disconnect from the actual target box.
                f"rounded=1;html=1;startArrow=none;endArrow=classic;"
                f"strokeColor={color};strokeWidth=2;"
                f"{dashed}fontColor=#202124;fontSize=10;labelBackgroundColor=#ffffff;"
                f"exitX={exit_x};exitY={exit_y};exitDx=0;exitDy=0;"
                f"entryX={entry_x};entryY={entry_y};entryDx=0;entryDy=0;"
            ),
        })
        geom = ET.SubElement(edge_cell, "mxGeometry", {
            "relative": "1", "as": "geometry", "x": f"{label_fraction:.4f}",
        })
        raw_point = raw_label_points[i]
        resolved_point = resolved_label_points[i]
        if raw_point is not None and resolved_point is not None:
            offset_x = resolved_point[0] - raw_point[0]
            offset_y = resolved_point[1] - raw_point[1]
            if abs(offset_x) > 0.5 or abs(offset_y) > 0.5:
                # A pixel-delta nudge FROM the on-path point already set by
                # the "x" fraction above -- the standard mxGraph mechanism
                # for separating a label from its anchor without moving the
                # anchor itself. See _resolve_label_collisions.
                ET.SubElement(geom, "mxPoint", {
                    "x": f"{offset_x:.1f}", "y": f"{offset_y:.1f}", "as": "offset",
                })
        if waypoints:
            points_el = ET.SubElement(geom, "Array", {"as": "points"})
            for wx, wy in waypoints:
                ET.SubElement(points_el, "mxPoint", {"x": str(int(wx)), "y": str(int(wy))})

    return ET.tostring(mxfile, encoding="unicode")
