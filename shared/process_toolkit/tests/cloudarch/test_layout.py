"""Ported from the ADK original's tests/test_cloudarch_layout_agent.py --
cloudarch_layout_engine.py is a byte-identical copy of that module (confirmed
directly: same MD5), but this port had never ported its dedicated test
coverage, leaving the single most algorithmically dense file in this project
(825 lines of deterministic geometry) with zero unit tests here despite
having a 491-line suite on the ADK side. Converted from unittest.TestCase to
plain pytest-style classes/asserts to match this project's own convention
(no other test file here uses unittest).

Also covers three real bugs found and fixed in this pass, all confirmed
directly against real generated diagrams (not just reasoned about):

1. _label_position_fraction: drawio's default edge-label position -- the
   arc-length midpoint of the whole polyline -- lands on top of a route's
   bend point on real multi-waypoint edges, usually on top of a zone
   boundary. A generated diagram showed labels like "Encrypt"/"Telemetry"
   clustering right at a subnet border.
2. _assign_connection_slots (replacing the old fixed-center
   _connection_point): multiple edges sharing one box+side (e.g. an API
   Gateway fanning out to two Fargate clusters) all got the IDENTICAL
   connection point, so their line segments visibly coincided near the
   shared box.
3. _resolve_label_collisions: _label_position_fraction only keeps a label
   off corners on its OWN edge's path -- it has no visibility into where
   every OTHER edge's label lands, so two entirely unrelated edges'
   labels could still coincidentally land within a few pixels of each
   other.

A first pass at fix #1 alone was shown to a real messy generated diagram
and initially (wrongly) reported as sufficient; a second, more complex
real diagram proved #2 and #3 still present, which is why all three are
covered here. Worth porting all three fixes to the ADK original's own
cloudarch_layout_agent.py, since the two files are otherwise kept
identical.

A THIRD real diagram (again shown directly, again after a "fixed" claim)
proved _route_edge itself could still route a line straight THROUGH an
unrelated box, not just crowd/mislabel one -- three more real, confirmed
causes, all fixed via _safe_x_for_vertical_span (see TestSafeRouting):
(4) a same-row edge between zones that are not actually adjacent (another
zone sits between them) cut through that intervening zone; (5) a
cross-row edge from a component with siblings stacked between it and the
direction of travel cut through those siblings; (6) a cross-row edge
skipping an entire intervening row (not just crossing into the next one)
cut through that row's own zone. (7) _channel_key's stagger-channel
grouping for the shared below-row gap didn't match which edges actually
ended up routed through it after the above fixes, so otherwise-correct
edges could still render as overlapping lines with no coordination
between them.
"""

import math
import xml.etree.ElementTree as ET

import pytest

from process_toolkit.cloudarch import layout


def _boxes_overlap(a, b):
    return not (a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y)


def _segment_crosses_box(p1, p2, box, pad=0.01):
    """Whether the axis-aligned segment p1->p2 (this router never produces
    diagonal segments) passes through `box`'s interior."""
    x1, y1 = p1
    x2, y2 = p2
    bx, by, bw, bh = box.x - pad, box.y - pad, box.w + 2 * pad, box.h + 2 * pad
    if x1 == x2:
        if not (bx < x1 < bx + bw):
            return False
        ylo, yhi = sorted((y1, y2))
        return not (yhi <= by or ylo >= by + bh)
    if y1 == y2:
        if not (by < y1 < by + bh):
            return False
        xlo, xhi = sorted((x1, x2))
        return not (xhi <= bx or xlo >= bx + bw)
    return False


class TestComponentHeight:
    def test_height_scales_with_bullet_count(self):
        no_bullets = layout._component_height({"label": "X"})
        three_bullets = layout._component_height({"label": "X", "bullets": ["a", "b", "c"]})
        assert no_bullets < three_bullets
        assert three_bullets - no_bullets == 3 * layout.LINE_HEIGHT

    def test_icon_adds_top_clearance(self):
        without_icon = layout._component_height({"label": "X", "bullets": ["a"]})
        with_icon = layout._component_height({"label": "X", "bullets": ["a"], "shape": "mxgraph.gcp2.cloud_run"})
        assert with_icon - without_icon == layout.SPACING_TOP_WITH_ICON - layout.SPACING_TOP_NO_ICON

    def test_matches_documented_formula(self):
        # A title plus 4 bullets (5 lines total) with spacingTop=74 needs height >= 174.
        component = {"label": "X", "bullets": ["a", "b", "c", "d"], "shape": "mxgraph.gcp2.cloud_run"}
        assert layout._component_height(component) == 174


class TestLayoutOverlap:
    """Regression coverage for the whole reason this module exists: no two
    boxes may ever overlap, regardless of how many components a zone holds
    or how the zones are arranged into rows."""

    def _sample(self):
        zones = [
            {"id": "z1", "label": "Zone One", "row": 0},
            {"id": "z2", "label": "Zone Two", "row": 0},
            {"id": "z3", "label": "Zone Three", "row": 0, "width": 300},
            {"id": "z_gov", "label": "Governance", "row": 1, "stack": "horizontal"},
        ]
        components = [
            {"id": "c1", "zone_id": "z1", "label": "A", "bullets": ["x", "y"], "shape": "mxgraph.gcp2.user"},
            {"id": "c2", "zone_id": "z1", "label": "B", "bullets": ["x", "y", "z", "w", "v"]},  # deliberately dense
            {"id": "c3", "zone_id": "z1", "label": "C"},  # no bullets, no icon -- shortest box
            {"id": "c4", "zone_id": "z2", "label": "D", "bullets": ["x"], "shape": "mxgraph.gcp2.cloud_vpn"},
            {"id": "c5", "zone_id": "z3", "label": "E", "bullets": ["x", "y", "z"]},
            {"id": "c6", "zone_id": "z_gov", "label": "F", "bullets": ["x"]},
            {"id": "c7", "zone_id": "z_gov", "label": "G", "bullets": ["x", "y"]},
        ]
        return zones, components

    def test_no_component_overlaps_within_a_zone(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        by_zone = {}
        for box in comp_boxes.values():
            by_zone.setdefault(box.zone_id, []).append(box)
        for zone_id, boxes in by_zone.items():
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    assert not _boxes_overlap(boxes[i], boxes[j]), (
                        f"{boxes[i].id} overlaps {boxes[j].id} in zone {zone_id}"
                    )

    def test_horizontal_stack_siblings_with_different_caption_lengths_get_matched_heights(self):
        # Regression test: confirmed against a real generated diagram. In a
        # "stack": "horizontal" zone, siblings with different bullet/caption
        # counts (c6 has 1, c7 has 2) previously kept their own, individually
        # shorter/taller heights while staying top-aligned at the same inner
        # y -- their vertical CENTERS then differed by a few pixels, forcing
        # every connecting edge between them into a small reconciliation jog
        # instead of a clean straight line, reading as "wonky"/pixels out of
        # alignment in an otherwise unbroken left-to-right row. Every
        # sibling in a horizontal-stack zone must get the SAME height (the
        # zone's own, tallest-sibling-driven content height).
        zones, components = self._sample()
        _, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        c6, c7 = comp_boxes["c6"], comp_boxes["c7"]
        assert c6.h == c7.h, f"horizontal-stack siblings have mismatched heights: {c6.h} vs {c7.h}"
        assert c6.cy == c7.cy, f"mismatched heights left their centers misaligned: {c6.cy} vs {c7.cy}"

    def test_no_zone_overlaps_another_zone(self):
        zones, components = self._sample()
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        boxes = list(zone_boxes.values())
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                assert not _boxes_overlap(boxes[i], boxes[j])

    def test_taller_zone_in_same_row_does_not_shrink_others(self):
        # z1 has a dense 5-bullet component (c2); z2/z3 are much shorter.
        # Every zone in row 0 must still start at the same y and span the
        # full row width without clipping its own content.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row0 = [zone_boxes[z] for z in ("z1", "z2", "z3")]
        assert len({b.y for b in row0}) == 1  # all start at the same y

    def test_horizontal_zone_in_a_later_row_stretches_to_match_earlier_row_width(self):
        # Regression test: a "stack": "horizontal" zone's width was
        # previously computed purely from its own children, contradicting
        # its own "full-width band" doc comment -- a governance strip with
        # few/narrow children (z_gov here has 2 default-width children,
        # narrower than row 0's 3-column total) stayed narrower than the
        # row above it instead of stretching to match.
        zones, components = self._sample()
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        row0_right_edge = max(zone_boxes[z].right for z in ("z1", "z2", "z3"))
        assert zone_boxes["z_gov"].right == pytest.approx(row0_right_edge, abs=1)

    def test_multi_zone_rows_stretch_to_the_same_width_without_compounding(self):
        # Regression test for a real generated diagram: stretching a
        # horizontal-stack zone to "the canvas width established so far" was
        # applied independently to EVERY zone in a row, with no awareness of
        # its row-mates -- so a row of two such zones each claimed the full
        # available width, making that row roughly DOUBLE the previous row's
        # width. That doubled width then became the next row's own stretch
        # target, doubling again. Four rows (2, 2, 1, 2 horizontal-stack
        # zones, mirroring the real diagram's shape) must all land on the
        # exact same total width -- not grow row over row.
        def comps(zone_id, n):
            return [
                {"id": f"{zone_id}_c{i}", "zone_id": zone_id, "label": "X", "shape": "mxgraph.aws4.lambda"}
                for i in range(n)
            ]

        zones = [
            {"id": "z0a", "row": 0, "stack": "horizontal"},
            {"id": "z0b", "row": 0, "stack": "horizontal"},
            {"id": "z1a", "row": 1, "stack": "horizontal"},
            {"id": "z1b", "row": 1, "stack": "horizontal"},
            {"id": "z2a", "row": 2, "stack": "horizontal"},
            {"id": "z3a", "row": 3, "stack": "horizontal"},
            {"id": "z3b", "row": 3, "stack": "horizontal"},
        ]
        components = (
            comps("z0a", 2) + comps("z0b", 4) + comps("z1a", 4) + comps("z1b", 2)
            + comps("z2a", 5) + comps("z3a", 4) + comps("z3b", 4)
        )
        zone_boxes, comp_boxes, canvas_w, _ = layout._layout_zones_and_components(zones, components)

        row_right_edges = {
            row: max(zone_boxes[z].right for z in ids)
            for row, ids in {
                0: ("z0a", "z0b"), 1: ("z1a", "z1b"), 2: ("z2a",), 3: ("z3a", "z3b"),
            }.items()
        }
        target = row_right_edges[0]
        for row, right_edge in row_right_edges.items():
            assert right_edge == pytest.approx(target, abs=1), f"row {row} did not match the target width"

        # A stretched zone's children must spread out to fill it, not stay
        # clustered at the left edge with dead space before the zone's own
        # right border.
        z1b_box = zone_boxes["z1b"]
        last_child = comp_boxes["z1b_c1"]
        assert z1b_box.right - last_child.right == pytest.approx(layout.COMPONENT_H_MARGIN, abs=1)


class TestVerticalZonesDoNotStretch:
    """Regression coverage for the fix to a real generated diagram: a row
    of plain vertical-stack zones (e.g. Management/Log/Security/Network
    accounts, each holding just 1-3 single-icon components) sharing a
    canvas with a much wider row (e.g. Customer accounts, each containing
    a horizontally-spread VPC of 6 resources) had every zone in the
    narrow row individually stretched to match the wide row's width --
    each ballooning from its natural 340px to ~1850px, since the vertical
    branch gives every child the SAME full zone width regardless of
    content, producing a single centered icon swimming in huge dead
    whitespace. Only "stack": "horizontal" zones (whose children genuinely
    spread out to use extra width) should stretch; the existing
    TestLayoutOverlap tests above already cover that they still do."""

    def _mismatched_rows(self):
        zones = [
            {"id": "small_a", "row": 0},
            {"id": "small_b", "row": 0},
            {"id": "wide_a", "row": 1, "stack": "horizontal"},
            {"id": "wide_b", "row": 1, "stack": "horizontal"},
        ]
        components = [
            {"id": "sa_c1", "zone_id": "small_a", "label": "X"},
            {"id": "sb_c1", "zone_id": "small_b", "label": "X"},
        ] + [
            {"id": f"wa_c{i}", "zone_id": "wide_a", "label": "X", "shape": "mxgraph.aws4.lambda"}
            for i in range(5)
        ] + [
            {"id": f"wb_c{i}", "zone_id": "wide_b", "label": "X", "shape": "mxgraph.aws4.lambda"}
            for i in range(5)
        ]
        return zones, components

    def test_plain_vertical_zone_keeps_its_natural_width_despite_a_much_wider_row(self):
        zones, components = self._mismatched_rows()
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        assert zone_boxes["small_a"].w == pytest.approx(layout.DEFAULT_ZONE_WIDTH)
        assert zone_boxes["small_b"].w == pytest.approx(layout.DEFAULT_ZONE_WIDTH)
        # The wide row's own horizontal-stack zones are, as ever, much
        # wider -- confirming this is a real width mismatch, not a fixture
        # that happens to produce equal widths anyway.
        assert zone_boxes["wide_a"].w > zone_boxes["small_a"].w * 3

    def test_row_of_only_vertical_zones_is_centered_not_individually_inflated(self):
        zones, components = self._mismatched_rows()
        zone_boxes, _, canvas_w, _ = layout._layout_zones_and_components(zones, components)
        small_a, small_b = zone_boxes["small_a"], zone_boxes["small_b"]
        row_total = small_b.right - small_a.x
        # The row as a whole is centered WITHIN the content region (between
        # PAGE_MARGIN and canvas_w) -- not individually stretched to fill
        # it. left_margin/right_margin are each measured from their own
        # edge of that content region, per _layout_zones_and_components'
        # own "centered within target_width" comment.
        left_margin = small_a.x - layout.PAGE_MARGIN
        right_margin = canvas_w - small_b.right
        assert left_margin == pytest.approx(right_margin, abs=2)
        assert left_margin > 0  # genuinely centered, not flush left
        # Not individually inflated: the row's total footprint is far
        # narrower than the wide row's own combined width.
        wide_total = zone_boxes["wide_b"].right - zone_boxes["wide_a"].x
        assert row_total < wide_total / 3

    def test_vertical_zone_with_an_explicit_width_is_still_unaffected(self):
        # Explicit "width" was already excluded from stretch eligibility
        # before this fix -- confirm that's still true (not a regression
        # introduced by also excluding plain vertical zones).
        zones, components = self._mismatched_rows()
        zones[0]["width"] = 500
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        assert zone_boxes["small_a"].w == pytest.approx(500)

    def test_horizontal_zones_still_stretch_as_before(self):
        # Non-regression check: this fix narrows eligibility, it must not
        # change what happens to an eligible ("stack": "horizontal") zone
        # -- already covered in depth by TestLayoutOverlap above, repeated
        # here directly alongside the vertical-exclusion fixture for
        # clarity that both behaviors coexist correctly in the same row.
        zones, components = self._mismatched_rows()
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        assert zone_boxes["wide_a"].w == pytest.approx(zone_boxes["wide_b"].w)

    def test_mixed_row_only_stretches_the_horizontal_sibling(self):
        zones = [
            {"id": "v1", "row": 0},
            {"id": "h1", "row": 0, "stack": "horizontal"},
            {"id": "wide_a", "row": 1, "stack": "horizontal"},
            {"id": "wide_b", "row": 1, "stack": "horizontal"},
        ]
        components = [
            {"id": "v1_c1", "zone_id": "v1", "label": "X"},
            {"id": "h1_c1", "zone_id": "h1", "label": "X"},
        ] + [
            {"id": f"wa_c{i}", "zone_id": "wide_a", "label": "X", "shape": "mxgraph.aws4.lambda"}
            for i in range(5)
        ] + [
            {"id": f"wb_c{i}", "zone_id": "wide_b", "label": "X", "shape": "mxgraph.aws4.lambda"}
            for i in range(5)
        ]
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        assert zone_boxes["v1"].w == pytest.approx(layout.DEFAULT_ZONE_WIDTH)
        assert zone_boxes["h1"].w > zone_boxes["v1"].w


class TestEdgeRouting:
    def _sample(self):
        zones = [
            {"id": "z1", "label": "Z1", "row": 0},
            {"id": "z2", "label": "Z2", "row": 0},
            {"id": "z_gov", "label": "Gov", "row": 1, "stack": "horizontal"},
        ]
        components = [
            {"id": "top", "zone_id": "z1", "label": "Top", "bullets": ["x"]},
            {"id": "bottom", "zone_id": "z1", "label": "Bottom", "bullets": ["x"]},
            # "far" is a 3rd component in z1, stacked below "bottom" -- so
            # "top" and "far" are NOT adjacent (bottom sits between them),
            # while "top"/"bottom" and "bottom"/"far" remain adjacent pairs.
            {"id": "far", "zone_id": "z1", "label": "Far", "bullets": ["x"]},
            {"id": "other", "zone_id": "z2", "label": "Other", "bullets": ["x"]},
            {"id": "gov_item", "zone_id": "z_gov", "label": "GovItem", "bullets": ["x"]},
        ]
        return zones, components

    def _row_bottoms(self, zone_boxes):
        row_bottoms = {}
        for box in zone_boxes.values():
            row_bottoms[box.row] = max(row_bottoms.get(box.row, 0.0), box.bottom)
        return row_bottoms

    def test_same_zone_edge_has_no_explicit_waypoint(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints, _, _ = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 0, row_bottoms, all_boxes
        )
        assert waypoints == []

    def test_edge_labels_sit_above_the_line_not_centered_on_it(self):
        # Requested against a real generated diagram: edge labels rendered
        # centered ON their arrow (the mxGraph default, which paints the
        # label's white background squarely over the line). verticalAlign=
        # bottom anchors each label's bottom edge to its point on the line,
        # lifting the text just above the arrow instead.
        zones, components = self._sample()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[{"source": "top", "target": "bottom", "label": "Flows"}],
        )
        root = ET.fromstring(xml_str)
        edge_cell = next(c for c in root.findall(".//mxCell") if c.get("edge") == "1")
        assert "verticalAlign=bottom;" in edge_cell.get("style", "")

    def test_non_adjacent_same_zone_edge_routes_through_the_side_margin_not_through_bottom(self):
        # Regression test for the "lines cutting through boxes" bug: "top"
        # and "far" are both in z1 but "bottom" sits between them in the
        # stack. A bare straight line from top to far would cut straight
        # through bottom's box. The route must instead go through the
        # zone's own side margin -- to the LEFT of every component in z1,
        # never through bottom's interior.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints, _, _ = layout._route_edge(
            {"source": "top", "target": "far"}, comp_boxes["top"], comp_boxes["far"], 0, row_bottoms, all_boxes
        )
        assert len(waypoints) == 2
        margin_x = waypoints[0][0]
        assert waypoints[1][0] == margin_x
        # Must sit strictly to the left of every component in the zone
        # (inside the zone's own border, outside every component's box).
        for comp_id in ("top", "bottom", "far"):
            assert margin_x < comp_boxes[comp_id].x
        assert margin_x > zone_boxes["z1"].x
        # And the vertical run must not pass through bottom's box (it
        # can't, since margin_x < bottom.x, but assert it explicitly).
        bottom = comp_boxes["bottom"]
        assert not (bottom.x < margin_x < bottom.right)

    def test_adjacent_same_zone_edges_unaffected_by_non_adjacent_fix(self):
        # bottom<->far are immediate neighbors (order 1, 2) despite "far"
        # being the 3rd component added for the non-adjacency tests above.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints, _, _ = layout._route_edge(
            {"source": "bottom", "target": "far"}, comp_boxes["bottom"], comp_boxes["far"], 0, row_bottoms, all_boxes
        )
        assert waypoints == []

    def test_same_row_edge_routes_through_the_zone_gap(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints, _, _ = layout._route_edge(
            {"source": "top", "target": "other"}, comp_boxes["top"], comp_boxes["other"], 0, row_bottoms, all_boxes
        )
        assert len(waypoints) == 1
        wx, _wy = waypoints[0]
        # Must sit strictly between the two zone columns, in the reserved gap.
        assert wx > zone_boxes["z1"].right
        assert wx < zone_boxes["z2"].x

    def test_same_row_edge_between_vertically_offset_components_is_axis_aligned(self):
        # Regression test: a real generated diagram (confirmed against the
        # actual XML) showed a "same row, different zone" edge rendering as
        # two DIAGONAL segments and looking disconnected from its target box.
        # "bottom" (2nd item in z1) and "other" (1st, only item in z2) sit at
        # different vertical positions -- the previous single-waypoint-at-
        # the-midpoint approach produced a path where neither segment was
        # purely horizontal or vertical. Every consecutive pair of points in
        # the full path (src's own center, each waypoint, tgt's own center)
        # must share either their x or their y for the rendered path to be a
        # clean right-angle route.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        src, tgt = comp_boxes["bottom"], comp_boxes["other"]
        assert src.cy != tgt.cy  # precondition: genuinely offset
        waypoints, _, _ = layout._route_edge({"source": "bottom", "target": "other"}, src, tgt, 0, row_bottoms, all_boxes)
        assert len(waypoints) == 2
        full_path = [(src.cx, src.cy)] + waypoints + [(tgt.cx, tgt.cy)]
        for (x1, y1), (x2, y2) in zip(full_path, full_path[1:]):
            assert x1 == x2 or y1 == y2, f"diagonal segment: ({x1},{y1}) -> ({x2},{y2})"

    def test_cross_row_edge_uses_tallest_zone_in_the_row_not_the_component(self):
        # Regression test: this previously used the SOURCE COMPONENT's own
        # bottom (near the top of its column) instead of the bottom of the
        # tallest zone in that row, routing straight through sibling
        # components below it. "top" is near the TOP of z1, far above
        # z1's actual bottom edge.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints, _, _ = layout._route_edge(
            {"source": "top", "target": "gov_item"}, comp_boxes["top"], comp_boxes["gov_item"], 0, row_bottoms, all_boxes
        )
        # "top" is not the last component in its own zone (bottom/far sit
        # below it), so _safe_x_for_vertical_span also moves exit_x away
        # from top.cx to dodge them -- the same fix TestSafeRouting covers
        # directly -- adding an extra axis-aligned jog waypoint rather than
        # the bare 2-point path. channel_y is whichever y repeats (the
        # horizontal leg through the reserved inter-row gap).
        ys = [wy for _wx, wy in waypoints]
        channel_y = max(ys)
        # The channel must be below EVERY row-0 zone's bottom edge (not just
        # the source component's own position), and above the row-1 zone.
        for zid in ("z1", "z2"):
            assert channel_y > zone_boxes[zid].bottom
        assert channel_y < zone_boxes["z_gov"].y

    def test_second_edge_between_identical_pair_gets_offset_not_identical_line(self):
        # Regression test: a request/response pair of edges between the SAME
        # two components previously both returned [] (no waypoint at all),
        # so they drew on the exact same straight line with labels rendering
        # on top of each other. The 2nd (and later) edge between an identical
        # pair must now get a nonzero perpendicular offset.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        first, _, _ = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 0, row_bottoms, all_boxes
        )
        second, _, _ = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 1, row_bottoms, all_boxes
        )
        assert first == []
        assert len(second) == 1
        assert second[0] != first

    def test_channel_key_groups_edges_that_would_otherwise_collide(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        all_boxes = {**comp_boxes, **zone_boxes}
        # Same pair, both directions -> same channel.
        assert (
            layout._channel_key(comp_boxes["top"], comp_boxes["bottom"], all_boxes)
            == layout._channel_key(comp_boxes["bottom"], comp_boxes["top"], all_boxes)
        )
        # Same zone-pair gap, different component pairs -> same channel.
        assert (
            layout._channel_key(comp_boxes["top"], comp_boxes["other"], all_boxes)
            == layout._channel_key(comp_boxes["bottom"], comp_boxes["other"], all_boxes)
        )
        # A same-zone pair must not collide with an inter-zone channel key.
        assert (
            layout._channel_key(comp_boxes["top"], comp_boxes["bottom"], all_boxes)
            != layout._channel_key(comp_boxes["top"], comp_boxes["other"], all_boxes)
        )

    def test_stagger_offset_alternates_and_grows_outward(self):
        assert layout._stagger_offset(0, 10) == 0.0
        assert layout._stagger_offset(1, 10) == 10.0
        assert layout._stagger_offset(2, 10) == -10.0
        assert layout._stagger_offset(3, 10) == 20.0
        assert layout._stagger_offset(4, 10) == -20.0

    def test_stagger_offset_respects_clamp(self):
        assert layout._stagger_offset(9, 10, clamp=15) == 15.0
        assert layout._stagger_offset(10, 10, clamp=15) == -15.0

    def test_two_edges_sharing_the_zone_gap_get_different_waypoints(self):
        # Two edges with different component pairs but similar enough
        # vertical position that, pre-fix, a global (not channel-local)
        # stagger could coincidentally assign them the same offset.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        edge_a, _, _ = layout._route_edge(
            {"source": "top", "target": "other"}, comp_boxes["top"], comp_boxes["other"], 0, row_bottoms, all_boxes
        )
        edge_b, _, _ = layout._route_edge(
            {"source": "bottom", "target": "other"}, comp_boxes["bottom"], comp_boxes["other"], 1, row_bottoms, all_boxes
        )
        assert edge_a[0][1] != edge_b[0][1]

    def test_cross_row_waypoints_never_land_inside_an_unrelated_component(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints, _, _ = layout._route_edge(
            {"source": "top", "target": "gov_item"}, comp_boxes["top"], comp_boxes["gov_item"], 0, row_bottoms, all_boxes
        )
        for wx, wy in waypoints:
            for cid, box in comp_boxes.items():
                if cid in ("top", "gov_item"):
                    continue
                assert not (box.x < wx < box.right and box.y < wy < box.bottom), (
                    f"waypoint ({wx},{wy}) lands inside unrelated component {cid}"
                )


class TestSafeRouting:
    """Regression coverage for _safe_x_for_vertical_span and the
    _route_edge branches it fixed -- see this file's own module docstring,
    bugs 4-7. A same-row edge between non-adjacent zones, a cross-row edge
    skipping an entire intervening row, and a cross-row edge from a
    component with siblings stacked between it and the direction of
    travel all previously cut straight through an unrelated box; two
    edges that end up sharing the same physical channel via different
    _route_edge branches previously had no stagger coordination between
    them. All confirmed directly against a real generated diagram."""

    def _sample(self):
        zones = [
            {"id": "left", "label": "Left", "row": 0},
            {"id": "middle", "label": "Middle", "row": 0},
            {"id": "right", "label": "Right", "row": 0},
            {"id": "wide", "label": "Wide", "row": 1},
            {"id": "bottom", "label": "Bottom", "row": 2, "stack": "horizontal"},
        ]
        components = [
            {"id": "l1", "zone_id": "left", "label": "L1"},
            {"id": "m1", "zone_id": "middle", "label": "M1"},
            {"id": "r1", "zone_id": "right", "label": "R1"},
            # "wide" is the sole zone in its row, same as the real diagram's
            # zone that triggered this bug -- its components stretch to
            # nearly the FULL row width, so a straight vertical line
            # through this row at almost ANY x lands inside one of them.
            {"id": "w1", "zone_id": "wide", "label": "W1"},
            {"id": "w2", "zone_id": "wide", "label": "W2"},
            {"id": "w3", "zone_id": "wide", "label": "W3"},
            {"id": "b1", "zone_id": "bottom", "label": "B1"},
        ]
        return zones, components

    def _route(self, source, target):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = {zb.row: zb.bottom for zb in zone_boxes.values()}
        all_boxes = {**comp_boxes, **zone_boxes}
        src, tgt = comp_boxes[source], comp_boxes[target]
        waypoints, _, _ = layout._route_edge({"source": source, "target": target}, src, tgt, 0, row_bottoms, all_boxes)
        full_path = [(src.cx, src.cy), *waypoints, (tgt.cx, tgt.cy)]
        return full_path, comp_boxes

    def test_safe_x_returns_preferred_x_when_already_clear(self):
        assert layout._safe_x_for_vertical_span(100.0, 0.0, 50.0, ("a", "b"), {}) == 100.0

    def test_safe_x_searches_away_from_a_blocking_component(self):
        boxes = {"blocker": layout._Box("blocker", 90.0, 0.0, 20.0, 50.0, zone_id="z")}
        safe_x = layout._safe_x_for_vertical_span(100.0, 0.0, 50.0, ("a", "b"), boxes)
        assert not (90.0 <= safe_x <= 110.0)

    def test_safe_x_ignores_excluded_ids_and_zone_containers(self):
        boxes = {
            "src": layout._Box("src", 90.0, 0.0, 20.0, 50.0, zone_id="z"),
            "zone": layout._Box("zone", 90.0, 0.0, 20.0, 50.0, zone_id=None),
        }
        assert layout._safe_x_for_vertical_span(100.0, 0.0, 50.0, ("src", "tgt"), boxes) == 100.0

    def test_same_row_non_adjacent_zones_do_not_cut_through_the_zone_between_them(self):
        full_path, comp_boxes = self._route("l1", "r1")
        middle = comp_boxes["m1"]
        for p1, p2 in zip(full_path, full_path[1:]):
            assert not _segment_crosses_box(p1, p2, middle)

    def test_cross_row_edge_skipping_an_entire_row_does_not_cut_through_it(self):
        full_path, comp_boxes = self._route("l1", "b1")
        for wide_id in ("w1", "w2", "w3"):
            box = comp_boxes[wide_id]
            for p1, p2 in zip(full_path, full_path[1:]):
                assert not _segment_crosses_box(p1, p2, box)

    def test_cross_row_edge_from_a_component_with_siblings_below_it_does_not_cut_through_them(self):
        # w1 is the FIRST (topmost) of three stacked components in "wide"
        # -- routing it down to row 2 must not cut through w2/w3 below it.
        full_path, comp_boxes = self._route("w1", "b1")
        for sibling_id in ("w2", "w3"):
            box = comp_boxes[sibling_id]
            for p1, p2 in zip(full_path, full_path[1:]):
                assert not _segment_crosses_box(p1, p2, box)

    def test_channel_key_unifies_same_row_detour_and_cross_row_edges_sharing_the_same_gap(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        all_boxes = {**comp_boxes, **zone_boxes}
        # l1->r1 (same-row, non-adjacent -> routed via row 0's below-row
        # channel) and l1->w1 (cross-row, adjacent rows -> ALSO routed via
        # row 0's below-row channel) must land in the SAME stagger channel,
        # so they get coordinated (not coincidentally identical) offsets.
        assert (
            layout._channel_key(comp_boxes["l1"], comp_boxes["r1"], all_boxes)
            == layout._channel_key(comp_boxes["l1"], comp_boxes["w1"], all_boxes)
        )

    def test_two_edges_sharing_a_channel_with_overlapping_spans_get_a_visible_stagger(self):
        # Regression test: confirmed against a real generated diagram that
        # sharing the same _channel_key was not enough on its own -- two
        # edges (a same-row detour and a cross-row edge, landing in the
        # same below-row channel per the test above) whose horizontal
        # spans substantially overlap rendered as one indistinguishable
        # line with two competing labels, because the per-slot stagger
        # step was too small to notice over a long shared run. l1->r1 and
        # l1->w1 both start at l1, so their channel legs overlap for their
        # entire length -- exactly the shape that broke.
        zones, components = self._sample()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[
                {"source": "l1", "target": "r1", "label": "First"},
                {"source": "l1", "target": "w1", "label": "Second"},
            ],
        )
        root = ET.fromstring(xml_str)
        edges_by_label = {}
        for cell in root.findall(".//mxCell"):
            if cell.get("edge") != "1":
                continue
            label = cell.get("value", "").replace("<b>", "").replace("</b>", "")
            arr = cell.find("mxGeometry/Array")
            ys = [float(p.get("y")) for p in arr.findall("mxPoint")] if arr is not None else []
            edges_by_label[label] = ys

        def _channel_y(ys):
            # The channel leg is the y that repeats (both ends of the
            # horizontal run through the channel share it) -- distinct
            # from any single jog point reconciling a slot-spread
            # connection point back to the route's own exit/entry x,
            # which appears only once.
            seen = set()
            for y in ys:
                if y in seen:
                    return y
                seen.add(y)
            raise AssertionError(f"no repeated y (no channel leg) in {ys}")

        channel_y_first = _channel_y(edges_by_label["First"])
        channel_y_second = _channel_y(edges_by_label["Second"])
        # A couple of pixels would technically be "different" but is
        # imperceptible at diagram scale -- require a real, visible gap.
        assert abs(channel_y_first - channel_y_second) >= 15, (
            f"channel legs only {abs(channel_y_first - channel_y_second)}px apart -- "
            "indistinguishable as separate lines"
        )

    def test_three_edges_sharing_a_channel_spread_across_the_full_safe_range(self):
        # Regression test: confirmed against a real generated diagram that
        # THREE distinct below-row-channel edges (not just two, the shape
        # the previous test covers) only ended up one fixed step (18px)
        # apart each -- visually indistinguishable parallel lines a viewer
        # picks up mid-span with no obvious endpoint, reading as "arrows
        # connected to nothing" -- when the channel had roughly twice that
        # much pre-verified-safe room (ROW_GAP_STAGGER_CLAMP) to spread
        # them further apart. l1->r1 (same-row detour), l1->w1, and
        # m1->w2 (both cross-row) all land in the same below-row-0 channel
        # per _channel_key.
        zones, components = self._sample()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[
                {"source": "l1", "target": "r1", "label": "First"},
                {"source": "l1", "target": "w1", "label": "Second"},
                {"source": "m1", "target": "w2", "label": "Third"},
            ],
        )
        root = ET.fromstring(xml_str)
        edges_by_label = {}
        for cell in root.findall(".//mxCell"):
            if cell.get("edge") != "1":
                continue
            label = cell.get("value", "").replace("<b>", "").replace("</b>", "")
            arr = cell.find("mxGeometry/Array")
            ys = [float(p.get("y")) for p in arr.findall("mxPoint")] if arr is not None else []
            edges_by_label[label] = ys

        def _channel_y(ys):
            seen = set()
            for y in ys:
                if y in seen:
                    return y
                seen.add(y)
            raise AssertionError(f"no repeated y (no channel leg) in {ys}")

        channel_ys = sorted(_channel_y(edges_by_label[label]) for label in ("First", "Second", "Third"))
        assert len(set(channel_ys)) == 3, f"two channels collapsed onto the same y: {channel_ys}"
        gaps = [channel_ys[1] - channel_ys[0], channel_ys[2] - channel_ys[1]]
        # With the old fixed 18px step, three edges ended up only 18px
        # apart each -- assert something close to double that (confirming
        # the dynamic step is actually using the available clamp range),
        # not just "more than the old step by a hair".
        assert min(gaps) >= 30, f"channel legs only {gaps}px apart -- still cramped like the old fixed step"

    def test_cross_row_edge_into_a_non_first_vertically_stacked_target_lands_in_the_gap_not_the_boundary(self):
        # Regression test: confirmed against a real generated diagram. A
        # cross-row edge into "target" (the SECOND of two vertically-
        # stacked, same-width siblings, so "blocker" shares target's own
        # center-x) must search away from center to avoid blocker -- but
        # the entry point itself (computed independently, unaware of that
        # search) still defaults to target's true center, which IS
        # blocked. The old single-point jog fallback reconciled that gap
        # with a horizontal segment run at the TARGET's own boundary y --
        # i.e. right along the edge of the box the arrow is about to
        # enter, indistinguishable from a line hugging/pointing at the box
        # rather than cleanly terminating on it. The correction must
        # instead land in the reserved gap between blocker and target, a
        # few px above target's own top edge, not AT it.
        zones = [
            {"id": "z_src", "label": "Src", "row": 0},
            {"id": "z_tgt", "label": "Tgt", "row": 1},
        ]
        components = [
            {"id": "src", "zone_id": "z_src", "label": "Src"},
            {"id": "blocker", "zone_id": "z_tgt", "label": "Blocker"},
            {"id": "target", "zone_id": "z_tgt", "label": "Target"},
        ]
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[{"source": "src", "target": "target", "label": "E"}],
        )
        root = ET.fromstring(xml_str)
        _, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        blocker, target = comp_boxes["blocker"], comp_boxes["target"]
        edge_cell = next(c for c in root.findall(".//mxCell") if c.get("edge") == "1")
        style = dict(p.split("=", 1) for p in edge_cell.get("style", "").split(";") if "=" in p)
        entry_pt = (target.x + float(style["entryX"]) * target.w, target.y + float(style["entryY"]) * target.h)
        geom = edge_cell.find("./mxGeometry")
        waypoints = [
            (float(p.get("x")), float(p.get("y")))
            for p in geom.findall("./Array[@as='points']/mxPoint")
        ]
        full_path = waypoints + [entry_pt]
        # No segment of the final approach may run along target's own top
        # boundary (y == target.y) for a horizontal stretch -- the
        # correction must land inside the gap above it instead.
        for (x1, y1), (x2, y2) in zip(full_path, full_path[1:]):
            hugs_target_edge = y1 == target.y and y2 == target.y and x1 != x2
            assert not hugs_target_edge, (
                f"correction segment runs along target's own edge: ({x1},{y1}) -> ({x2},{y2})"
            )
        for p1, p2 in zip(full_path, full_path[1:]):
            assert not _segment_crosses_box(p1, p2, blocker), (
                f"edge cuts through the blocking sibling: {p1} -> {p2}"
            )

    def test_adjacent_zone_edge_into_a_non_first_component_does_not_cut_through_its_sibling(self):
        # Regression test: confirmed against a real generated diagram. An
        # edge from a source zone into the SECOND component of the adjacent
        # target zone (with a sibling occupying the first slot, between the
        # zone boundary and the real target) must NOT draw a straight
        # horizontal connector at the shared mid-height -- that cuts clean
        # through the sibling, the arrowhead appearing to emerge from inside
        # that unrelated box. Two single-component "edge" zones feeding the
        # SECOND box of a 2-box adjacent zone reproduce exactly that shape.
        zones = [
            {"id": "src_zone", "label": "Source", "row": 0, "stack": "horizontal"},
            {"id": "tgt_zone", "label": "Target", "row": 0, "stack": "horizontal"},
        ]
        components = [
            {"id": "s1", "zone_id": "src_zone", "label": "S1"},
            {"id": "t_first", "zone_id": "tgt_zone", "label": "T First"},
            {"id": "t_second", "zone_id": "tgt_zone", "label": "T Second"},
        ]
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[{"source": "s1", "target": "t_second", "label": "Reach"}],
        )
        root = ET.fromstring(xml_str)
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        sibling = comp_boxes["t_first"]
        edge_cell = next(c for c in root.findall(".//mxCell") if c.get("edge") == "1")
        style = dict(p.split("=", 1) for p in edge_cell.get("style", "").split(";") if "=" in p)
        src, tgt = comp_boxes["s1"], comp_boxes["t_second"]
        exit_pt = (src.x + float(style["exitX"]) * src.w, src.y + float(style["exitY"]) * src.h)
        entry_pt = (tgt.x + float(style["entryX"]) * tgt.w, tgt.y + float(style["entryY"]) * tgt.h)
        geom = edge_cell.find("./mxGeometry")
        waypoints = [
            (float(p.get("x")), float(p.get("y")))
            for p in geom.findall("./Array[@as='points']/mxPoint")
        ]
        full_path = [exit_pt, *waypoints, entry_pt]
        for p1, p2 in zip(full_path, full_path[1:]):
            assert not _segment_crosses_box(p1, p2, sibling), (
                f"edge cuts through its target's sibling: {p1} -> {p2} crosses t_first"
            )

    def test_blocked_exit_stays_axis_aligned_and_keeps_its_conceptual_side(self):
        # Regression test for a real generated diagram: when
        # _safe_x_for_vertical_span has to search far from a box's own
        # center to dodge a sibling, a naively-inferred connection side
        # could flip from "bottom" to "left"/"right" once the found x was
        # farther from the box's center than the channel was from its own
        # y -- rendering as a diagonal line jumping from the box's
        # left-center straight to a point far below and to the side of
        # it, instead of a clean right-angle drop from its bottom edge.
        # exit_side must stay "bottom" (this edge conceptually flows
        # downward into a later row) regardless of how far the search
        # moved, and every segment of the FINAL, slot-reconciled path
        # (via build_structured_drawio_xml -- see
        # _reconcile_connection_points) must be axis-aligned.
        zones, components = self._sample()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[{"source": "w1", "target": "b1", "label": "Down"}],
        )
        root = ET.fromstring(xml_str)
        edge_cell = next(c for c in root.findall(".//mxCell") if c.get("edge") == "1")
        style = edge_cell.get("style", "")
        parts = dict(p.split("=", 1) for p in style.split(";") if "=" in p)
        assert parts["exitY"] == "1.0"  # "bottom" side, not skewed to left/right

        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        src, tgt = comp_boxes["w1"], comp_boxes["b1"]
        # Waypoints are serialized as integers (see build_structured_drawio_
        # xml's own str(int(..)) on each mxPoint) while exitX/entryX keep
        # full float precision, so a connection point's own pixel position
        # can differ from an adjacent waypoint's by under 1px -- compare at
        # the same (int) precision actually rendered, not raw floats.
        exit_pt = (
            int(src.x + float(parts["exitX"]) * src.w), int(src.y + float(parts["exitY"]) * src.h)
        )
        entry_pt = (
            int(tgt.x + float(parts["entryX"]) * tgt.w), int(tgt.y + float(parts["entryY"]) * tgt.h)
        )
        geom = edge_cell.find("./mxGeometry")
        waypoints = [(int(p.get("x")), int(p.get("y"))) for p in geom.findall("./Array[@as='points']/mxPoint")]
        full_path = [exit_pt, *waypoints, entry_pt]
        for (x1, y1), (x2, y2) in zip(full_path, full_path[1:]):
            assert x1 == x2 or y1 == y2, f"diagonal segment: ({x1},{y1}) -> ({x2},{y2})"

    def test_multiple_edges_sharing_a_box_side_stay_axis_aligned_after_slot_spreading(self):
        # Regression test for a real generated diagram: _assign_connection_
        # slots spreads multiple edges sharing one box+side to DIFFERENT
        # points along that side (fix #2, earlier in this file's history)
        # -- but _route_edge computes its own waypoints assuming the box's
        # CENTER as the connection point. Without reconciling the two,
        # every edge touching a multi-edge hub box (e.g. two edges both
        # leaving "wide"'s bottom side) rendered as a diagonal line cutting
        # in from an angle instead of a clean right-angle drop.
        zones, components = self._sample()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[
                {"source": "w1", "target": "b1", "label": "Down 1"},
                {"source": "w1", "target": "w2", "label": "Down 2"},
            ],
        )
        root = ET.fromstring(xml_str)
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        for edge_cell in root.findall(".//mxCell"):
            if edge_cell.get("edge") != "1":
                continue
            style = edge_cell.get("style", "")
            parts = dict(p.split("=", 1) for p in style.split(";") if "=" in p)
            src = comp_boxes[edge_cell.get("source")]
            tgt = comp_boxes[edge_cell.get("target")]
            # int(), matching the truncation build_structured_drawio_xml's
            # own waypoint serialization uses -- see the other test in
            # this class for why raw float comparison is too strict here.
            exit_pt = (int(src.x + float(parts["exitX"]) * src.w), int(src.y + float(parts["exitY"]) * src.h))
            entry_pt = (int(tgt.x + float(parts["entryX"]) * tgt.w), int(tgt.y + float(parts["entryY"]) * tgt.h))
            geom = edge_cell.find("./mxGeometry")
            waypoints = [
                (int(p.get("x")), int(p.get("y"))) for p in geom.findall("./Array[@as='points']/mxPoint")
            ]
            full_path = [exit_pt, *waypoints, entry_pt]
            for (x1, y1), (x2, y2) in zip(full_path, full_path[1:]):
                assert x1 == x2 or y1 == y2, (
                    f"{edge_cell.get('id')}: diagonal segment ({x1},{y1}) -> ({x2},{y2})"
                )

    def test_zone_skip_edge_sharing_its_box_side_with_another_edge_does_not_backtrack(self):
        # Regression test: confirmed against a real generated diagram (an
        # OpenSearch architecture's "Data Nodes -> S3 Storage" backup
        # edge). The zone_skip branch of _route_edge (a same-zone,
        # non-adjacent-sibling edge) computes its own waypoints assuming
        # it exits its source box from the box's own CENTER. When that
        # same box+side is ALSO used by another edge, slot-spreading
        # moves this edge's REAL exit point away from center -- and the
        # old reconciliation logic inserted a jog that ran BACKWARD along
        # the box's own edge (toward the center) before turning toward
        # the real destination, visually indistinguishable from a stray,
        # disconnected line sitting on top of the source box. "a" here
        # plays the role of "Data Nodes": both the target of an incoming
        # edge from above and the source of a same-zone skip edge, both
        # sharing its "top" side.
        zones = [
            {"id": "upstream", "label": "Upstream", "row": 0},
            {"id": "z", "label": "Z", "row": 1, "stack": "horizontal"},
        ]
        components = [
            {"id": "u1", "zone_id": "upstream", "label": "U1"},
            {"id": "a", "zone_id": "z", "label": "A"},
            {"id": "b", "zone_id": "z", "label": "B"},
            {"id": "c", "zone_id": "z", "label": "C"},
        ]
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[
                {"source": "u1", "target": "a", "label": "In"},
                {"source": "a", "target": "c", "label": "Skip"},
            ],
        )
        root = ET.fromstring(xml_str)
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        edge_cell = next(
            c for c in root.findall(".//mxCell")
            if c.get("edge") == "1" and "Skip" in (c.get("value") or "")
        )
        style = edge_cell.get("style", "")
        parts = dict(p.split("=", 1) for p in style.split(";") if "=" in p)
        assert parts["exitX"] != "0.5", "test fixture did not actually force slot-spreading off-center"
        src = comp_boxes["a"]
        exit_pt = (int(src.x + float(parts["exitX"]) * src.w), int(src.y + float(parts["exitY"]) * src.h))
        geom = edge_cell.find("./mxGeometry")
        waypoints = [
            (int(p.get("x")), int(p.get("y"))) for p in geom.findall("./Array[@as='points']/mxPoint")
        ]
        # "a" exits toward "c" (further right) -- the very first segment
        # must not move LEFT, back across the box's own top edge, before
        # heading toward the real destination.
        assert waypoints[0][0] >= exit_pt[0], (
            f"edge backtracks left from its own exit point: {exit_pt} -> {waypoints[0]}"
        )


class TestLabelPosition:
    """New coverage for _label_position_fraction -- see its own docstring
    and this file's module docstring for the real bug it fixes: drawio's
    default edge-label position (the arc-length midpoint of the whole
    polyline) lands on a bend point -- usually a zone boundary, for this
    router's own waypoints -- on an uneven multi-segment path."""

    def test_straight_two_point_path_is_the_exact_middle(self):
        path = [(0.0, 0.0), (100.0, 0.0)]
        assert layout._label_position_fraction(path) == pytest.approx(0.0)

    def test_single_bend_with_unequal_legs_favors_the_longer_leg(self):
        # A short leg (10) then a long leg (100): the arc-length midpoint
        # (55 units in) falls on the long leg, same as the longest-segment
        # midpoint here -- so this case alone wouldn't distinguish the two
        # approaches. The point is the NEXT test, where it does.
        path = [(0.0, 0.0), (10.0, 0.0), (10.0, 100.0)]
        fraction = layout._label_position_fraction(path)
        # Longest segment is index 1 (length 100, out of 110 total),
        # spanning arc positions [10, 110]; its midpoint is at arc position
        # 60, i.e. fraction (60/110)*2-1.
        expected = (60 / 110) * 2 - 1
        assert fraction == pytest.approx(expected)

    def test_three_segment_path_prefers_longest_segment_over_arc_midpoint(self):
        # This is the real shape _route_edge produces for a cross-row/
        # cross-zone edge: short-long-short. The arc-length midpoint (at
        # 50% of total length) can land well inside the FIRST or THIRD leg
        # if the middle leg is long enough relative to the others --
        # confirmed directly against a real generated diagram's geometry.
        # Segments: 80 (up), 200 (across), 80 (down) -- total 360, arc-mid
        # at 180, which is 100 units into the middle segment (80..280).
        path = [(0.0, 80.0), (0.0, 0.0), (200.0, 0.0), (200.0, 80.0)]
        fraction = layout._label_position_fraction(path)
        # Longest segment is index 1 (length 200, out of 360 total),
        # spanning arc positions [80, 280]; its midpoint is at arc position
        # 180 -- same as the arc-length midpoint in THIS particular case
        # (by construction, to keep the assertion simple), but computed via
        # the longest-segment rule, not "50% of total length" -- the next
        # test is the one where the two rules actually diverge.
        expected = (180 / 360) * 2 - 1
        assert fraction == pytest.approx(expected)

    def test_uneven_three_segment_path_diverges_from_arc_length_midpoint(self):
        # Segments: 20 (short), 50 (medium), 100 (long) -- total 170.
        # Arc-length midpoint sits at 85, which falls 65 units into the
        # LONG segment (arc range [70, 170]) -- so even the naive
        # arc-length approach happens to land on the long segment here.
        # Make it diverge for real: 90 (long-ish), 50 (medium), 20 (short).
        # Total 160, arc-mid at 80 -- falls exactly at the boundary between
        # segment 0 (range [0,90]) and segment 1 -- i.e. arc-length mid is
        # near the FIRST segment's own end/corner, not its middle, while
        # the longest-segment rule correctly centers on segment 0 (mid=45).
        path = [(0.0, 0.0), (90.0, 0.0), (90.0, 50.0), (90.0, 70.0)]
        fraction = layout._label_position_fraction(path)
        arc_length_mid_fraction = 0.0  # what the OLD (pre-fix) behavior effectively used
        longest_seg_mid_fraction = (45 / 160) * 2 - 1
        assert fraction == pytest.approx(longest_seg_mid_fraction)
        assert fraction != pytest.approx(arc_length_mid_fraction, abs=0.05)

    def test_build_structured_drawio_xml_sets_a_label_position_on_every_edge(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[
                {"id": "z1", "label": "Z1", "row": 0},
                {"id": "z2", "label": "Z2", "row": 1, "stack": "horizontal"},
            ],
            components=[
                {"id": "a", "zone_id": "z1", "label": "A", "bullets": ["x"]},
                {"id": "b", "zone_id": "z2", "label": "B", "bullets": ["x"]},
            ],
            edges=[{"source": "a", "target": "b", "label": "Cross-row"}],
        )
        root = ET.fromstring(xml_str)
        edge_cells = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]
        assert len(edge_cells) == 1
        geom = edge_cells[0].find("./mxGeometry")
        assert geom.get("x") is not None
        assert -1.0 <= float(geom.get("x")) <= 1.0


class TestConnectionSlotSpreading:
    """New coverage for _assign_connection_slots -- see its own docstring
    and _connection_side's for the real bug it fixes: _connection_point
    (now removed) gave every edge touching the same box+side the IDENTICAL
    fixed-center connection point, so two or more edges fanning out of one
    box (e.g. an API Gateway calling two Fargate clusters) rendered with
    their line segments visibly coinciding near that shared box -- confirmed
    directly against a real generated diagram ("api_gw" had two edges both
    exiting at the exact same pixel point)."""

    def _sample(self):
        zones = [{"id": "z1", "label": "Z1", "row": 0}, {"id": "z2", "label": "Z2", "row": 0}]
        components = [
            {"id": "hub", "zone_id": "z1", "label": "Hub"},
            {"id": "spoke_a", "zone_id": "z2", "label": "A"},
            {"id": "spoke_b", "zone_id": "z2", "label": "B"},
        ]
        return zones, components

    def test_single_edge_on_a_side_still_gets_dead_center(self):
        # slot_count <= 1 must match the old fixed-0.5 behavior exactly --
        # no regression for the overwhelmingly common case of one edge per
        # box+side.
        assert layout._slot_fraction(0, 1) == pytest.approx(0.5)

    def test_two_edges_sharing_a_box_and_side_get_different_connection_points(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = {zb.row: zb.bottom for zb in zone_boxes.values()}
        all_boxes = {**comp_boxes, **zone_boxes}
        edges = [
            {"source": "hub", "target": "spoke_a"},
            {"source": "hub", "target": "spoke_b"},
        ]
        plans = layout._assign_connection_slots(edges, all_boxes, row_bottoms, [0, 0])
        assert plans[0]["exit_frac"] != plans[1]["exit_frac"]

    def test_slot_fractions_stay_off_the_corners(self):
        for slot in range(4):
            fraction = layout._slot_fraction(slot, 4)
            assert 0.2 <= fraction <= 0.8

    def test_build_structured_drawio_xml_gives_fanout_edges_distinct_exit_points(self):
        # End-to-end regression test: a real generated diagram showed one
        # box's two outgoing edges rendering from the identical exit point.
        zones, components = self._sample()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[
                {"source": "hub", "target": "spoke_a", "label": "To A"},
                {"source": "hub", "target": "spoke_b", "label": "To B"},
            ],
        )
        root = ET.fromstring(xml_str)
        edge_cells = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]

        def exit_point(cell):
            style = cell.get("style", "")
            parts = dict(p.split("=", 1) for p in style.split(";") if "=" in p)
            return (parts["exitX"], parts["exitY"])

        assert exit_point(edge_cells[0]) != exit_point(edge_cells[1])


class TestLabelCollisionResolution:
    """New coverage for _resolve_label_collisions -- see its own docstring
    for the real bug it fixes: _label_position_fraction only keeps a label
    off corners/bends on its OWN edge's path, with no visibility into where
    every OTHER edge's label lands, so two entirely unrelated edges can
    still coincidentally compute to nearly the same point -- confirmed
    directly against a real generated diagram (two unrelated edges' labels
    only 5px apart)."""

    def test_far_apart_labels_are_left_untouched(self):
        points = [(0.0, 0.0), (500.0, 500.0)]
        assert layout._resolve_label_collisions(points) == points

    def test_coincident_labels_end_up_at_least_threshold_apart(self):
        points = [(100.0, 100.0), (100.0, 100.0)]
        resolved = layout._resolve_label_collisions(points, threshold=40.0)
        assert math.dist(resolved[0], resolved[1]) == pytest.approx(40.0)

    def test_nearly_coincident_labels_end_up_at_least_threshold_apart(self):
        # Regression test for the real confirmed bug: two labels 5px apart.
        points = [(100.0, 100.0), (105.0, 100.0)]
        resolved = layout._resolve_label_collisions(points, threshold=40.0)
        assert math.dist(resolved[0], resolved[1]) == pytest.approx(40.0)

    def test_none_entries_are_skipped_without_raising(self):
        points = [(0.0, 0.0), None, (0.0, 0.0)]
        resolved = layout._resolve_label_collisions(points, threshold=40.0)
        assert resolved[1] is None
        assert math.dist(resolved[0], resolved[2]) == pytest.approx(40.0)

    def test_build_structured_drawio_xml_nudges_colliding_edge_labels_apart(self, monkeypatch):
        # End-to-end wiring test: force two unrelated edges' raw label
        # points to coincide exactly (the collision-resolution LOGIC
        # itself is already covered above; this confirms
        # build_structured_drawio_xml actually threads its result into a
        # real mxPoint offset on the emitted XML, same as the real
        # generated diagram that originally surfaced this bug).
        monkeypatch.setattr(layout, "_point_at_fraction", lambda path, fraction: (100.0, 100.0))

        zones = [{"id": "z1", "label": "Z1", "row": 0}]
        components = [
            {"id": "a", "zone_id": "z1", "label": "A"},
            {"id": "b", "zone_id": "z1", "label": "B"},
            {"id": "c", "zone_id": "z1", "label": "C"},
            {"id": "d", "zone_id": "z1", "label": "D"},
        ]
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components,
            edges=[
                {"source": "a", "target": "b", "label": "Edge 1"},
                {"source": "c", "target": "d", "label": "Edge 2"},
            ],
        )
        root = ET.fromstring(xml_str)
        edge_cells = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]
        offsets = [c.find("./mxGeometry/mxPoint[@as='offset']") for c in edge_cells]
        # Both coincident labels must have gotten an explicit offset nudge
        # away from their shared on-path point, and end up far enough apart.
        assert all(offset is not None for offset in offsets)
        resolved = [(float(o.get("x")) + 100.0, float(o.get("y")) + 100.0) for o in offsets]
        assert math.dist(resolved[0], resolved[1]) == pytest.approx(40.0)


class TestBuildXml:
    def test_produces_valid_parseable_xml_with_expected_cells(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="S",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[{"id": "c1", "zone_id": "z1", "label": "Comp", "bullets": ["b1"], "shape": "mxgraph.gcp2.cloud_run"}],
            edges=[],
        )
        root = ET.fromstring(xml_str)  # raises if not well-formed
        ids = {cell.get("id") for cell in root.findall(".//mxCell")}
        assert "title_banner" in ids
        assert "z1" in ids
        assert "c1" in ids
        assert "c1_icon" in ids

    def test_explicit_empty_icon_color_falls_back_to_the_component_color_not_a_blank_fill(self):
        # Regression test: confirmed against a real generated diagram, a
        # component spec with an explicit "icon_color": "" produced a
        # literal "fillColor=;" style fragment -- dict.get(key, default)
        # only falls back when the KEY is absent, not when its value is
        # present but empty -- which drawio renders as a solid black icon
        # instead of the component's own color.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[{
                "id": "c1", "zone_id": "z1", "label": "Comp", "shape": "mxgraph.aws4.opensearch_service",
                "color": "#527FFF", "icon_color": "",
            }],
            edges=[],
        )
        root = ET.fromstring(xml_str)
        icon_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "c1_icon")
        assert "fillColor=#527FFF;" in icon_cell.get("style", "")
        assert "fillColor=;" not in icon_cell.get("style", "")

    def test_explicit_json_null_color_falls_back_instead_of_literal_none(self):
        # Regression test: confirmed against a real generated diagram -- the
        # LLM emitted explicit "color": null (and "icon_color" omitted) for
        # components, which component.get("color", DEFAULT) does NOT catch
        # (that positional default only applies when the KEY is absent, not
        # when it's present with value None) -- the result was the literal
        # text "None" baked into fillColor=None;strokeColor=None;, invalid
        # drawio styling that rendered icons and box borders as invisible.
        # Same bug class as the empty-string case above, but for JSON null.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone", "color": None}],
            components=[
                {
                    "id": "c1", "zone_id": "z1", "label": "Icon Comp",
                    "shape": "mxgraph.aws4.organizations", "color": None, "icon_color": None,
                },
                {"id": "c2", "zone_id": "z1", "label": "Box Comp", "color": None},
            ],
            edges=[{"source": "c1", "target": "c2", "label": "E", "color": None}],
        )
        assert "None" not in xml_str

        root = ET.fromstring(xml_str)
        zone_style = next(c for c in root.findall(".//mxCell") if c.get("id") == "z1").get("style", "")
        assert "strokeColor=None" not in zone_style

        icon_style = next(c for c in root.findall(".//mxCell") if c.get("id") == "c1_icon").get("style", "")
        assert "fillColor=None" not in icon_style
        assert f"fillColor={layout.DEFAULT_COMPONENT_COLOR};" in icon_style

        box_style = next(c for c in root.findall(".//mxCell") if c.get("id") == "c2").get("style", "")
        assert "strokeColor=None" not in box_style
        assert f"strokeColor={layout.DEFAULT_COMPONENT_COLOR};" in box_style

        edge_style = next(c for c in root.findall(".//mxCell") if c.get("edge") == "1").get("style", "")
        assert "strokeColor=None" not in edge_style

    def test_uncolored_component_inherits_its_own_zones_color(self):
        # Regression test: confirmed against a real generated diagram -- the
        # LLM set distinct, correct colors on every ZONE (per the "ZONES
        # NEED A DISTINCT COLOR TOO" instruction) but left every single
        # component's own color/icon_color unset. Previously that meant
        # EVERY icon in the whole diagram rendered in the identical flat
        # DEFAULT_COMPONENT_COLOR gray regardless of which (differently
        # colored) zone it sat in -- a diagram read as entirely monochrome
        # instead of at least differentiating by zone/grouping. An
        # uncolored component must now inherit its OWN zone's color.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[
                {"id": "z_mgmt", "label": "Management", "row": 0, "color": "#E7157B"},
                {"id": "z_sec", "label": "Security", "row": 0, "color": "#DD344C"},
            ],
            components=[
                {"id": "orgs", "zone_id": "z_mgmt", "label": "Organizations", "shape": "mxgraph.aws4.organizations"},
                {"id": "kms", "zone_id": "z_sec", "label": "KMS", "shape": "mxgraph.aws4.key_management_service"},
            ],
            edges=[],
        )
        root = ET.fromstring(xml_str)
        orgs_style = next(c for c in root.findall(".//mxCell") if c.get("id") == "orgs_icon").get("style", "")
        kms_style = next(c for c in root.findall(".//mxCell") if c.get("id") == "kms_icon").get("style", "")
        assert "fillColor=#E7157B;" in orgs_style
        assert "fillColor=#DD344C;" in kms_style
        # Different zones' uncolored components must differ from each
        # other, not all collapse onto the same flat default.
        assert "fillColor=#E7157B;" not in kms_style

    def test_component_explicit_color_still_wins_over_its_zones_color(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone", "color": "#E7157B"}],
            components=[{
                "id": "c1", "zone_id": "z1", "label": "X",
                "shape": "mxgraph.aws4.lambda", "color": "#ED7100",
            }],
            edges=[],
        )
        root = ET.fromstring(xml_str)
        style = next(c for c in root.findall(".//mxCell") if c.get("id") == "c1_icon").get("style", "")
        assert "fillColor=#ED7100;" in style
        assert "fillColor=#E7157B;" not in style

    def test_uncolored_component_in_an_uncolored_zone_still_falls_back_to_the_flat_default(self):
        # The zone-color-inheritance fallback must not regress the
        # ultimate safety net when NEITHER the component NOR its zone has
        # any color at all.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[{"id": "c1", "zone_id": "z1", "label": "X", "shape": "mxgraph.aws4.lambda"}],
            edges=[],
        )
        root = ET.fromstring(xml_str)
        style = next(c for c in root.findall(".//mxCell") if c.get("id") == "c1_icon").get("style", "")
        assert f"fillColor={layout.DEFAULT_COMPONENT_COLOR};" in style

    def test_uncolored_component_in_an_uncolored_vpc_zone_inherits_an_icon_safe_accent_not_the_pale_container_fill(self):
        # GCP's own VPC container accent (#E3F2FD) is a pale pastel FILL
        # meant for a large background rectangle -- inheriting it as an
        # icon's own fillColor would reproduce the "icons too faint to
        # see" problem this pipeline already fixed once, just for GCP.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "vpc1", "label": "VPC", "type": "vpc"}],
            components=[{"id": "c1", "zone_id": "vpc1", "label": "X", "shape": "mxgraph.gcp2.cloud_run"}],
            edges=[], provider="gcp",
        )
        root = ET.fromstring(xml_str)
        style = next(c for c in root.findall(".//mxCell") if c.get("id") == "c1_icon").get("style", "")
        assert "fillColor=#E3F2FD;" not in style
        assert "fillColor=#4285F4;" in style

    def test_explicit_json_null_row_does_not_crash(self):
        # Regression test: int(z.get("row", 0)) crashes with TypeError if
        # "row" is explicitly null (present-but-None is not caught by a
        # positional .get default) -- one optional field the LLM didn't
        # bother setting shouldn't take down the whole build.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone", "row": None}],
            components=[{"id": "c1", "zone_id": "z1", "label": "Comp"}],
            edges=[],
        )
        root = ET.fromstring(xml_str)
        assert next(c for c in root.findall(".//mxCell") if c.get("id") == "z1") is not None

    def test_explicit_json_null_stack_falls_back_to_vertical(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone", "stack": None}],
            components=[
                {"id": "c1", "zone_id": "z1", "label": "A"},
                {"id": "c2", "zone_id": "z1", "label": "B"},
            ],
            edges=[],
        )
        _, comp_boxes, _, _ = layout._layout_zones_and_components(
            [{"id": "z1", "label": "Zone", "stack": None}],
            [
                {"id": "c1", "zone_id": "z1", "label": "A"},
                {"id": "c2", "zone_id": "z1", "label": "B"},
            ],
        )
        # Vertical stacking: second component sits strictly below the first.
        assert comp_boxes["c2"].y > comp_boxes["c1"].y

    def test_bidirectional_edges_between_same_pair_get_visibly_different_labels(self):
        # End-to-end regression test for the label-collision fix: a request
        # edge and a response edge between the identical two components must
        # not render as two edges with identical waypoints (which previously
        # produced overlapping labels, e.g. two numbered steps merging into
        # unreadable text in the rendered diagram).
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[
                {"id": "a", "zone_id": "z1", "label": "A", "bullets": ["x"]},
                {"id": "b", "zone_id": "z1", "label": "B", "bullets": ["x"]},
            ],
            edges=[
                {"source": "a", "target": "b", "number": 1, "label": "Request"},
                {"source": "b", "target": "a", "number": 2, "label": "Response"},
            ],
        )
        root = ET.fromstring(xml_str)
        edge_cells = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]
        assert len(edge_cells) == 2

        def waypoints_of(cell):
            return [
                (p.get("x"), p.get("y"))
                for p in cell.findall("./mxGeometry/Array[@as='points']/mxPoint")
            ]

        wp0, wp1 = waypoints_of(edge_cells[0]), waypoints_of(edge_cells[1])
        assert wp0 != wp1

    def test_duplicate_component_id_raises_with_offending_id_named(self):
        # Regression test: previously a duplicate component id silently
        # collapsed both components onto the same box (component_boxes is
        # dict-keyed by id, so the second overwrites the first), rendering
        # as two components' text and icons fused on top of each other in
        # the actual generated diagram. This must fail loudly instead.
        with pytest.raises(ValueError, match="vertex"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Zone"}],
                components=[
                    {"id": "vertex", "zone_id": "z1", "label": "Vertex AI Search"},
                    {"id": "vertex", "zone_id": "z1", "label": "Vertex AI Models"},
                ],
                edges=[],
            )

    def test_duplicate_zone_id_raises_with_offending_id_named(self):
        with pytest.raises(ValueError, match="z1"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[
                    {"id": "z1", "label": "Zone A"},
                    {"id": "z1", "label": "Zone B"},
                ],
                components=[],
                edges=[],
            )

    def test_dangling_component_zone_reference_raises_a_clear_value_error(self):
        # Regression test: a component whose zone_id doesn't match any
        # real zone previously crashed with a bare, uninformative
        # `KeyError: 'c1'` from deep inside the final render pass (the
        # component silently never got laid out because nothing ever
        # visits comps_by_zone's own keys independently -- it's only
        # ever read via comps_by_zone.get(<a real zone's own id>)) --
        # confirmed directly against a real generated request. That
        # KeyError names the orphaned COMPONENT's id, not the bogus
        # zone_id that actually caused it, giving an LLM caller nothing
        # to act on despite save_drawio_structured_tool.py's own
        # error-handling message always having claimed this exact case
        # ("every component's zone_id references a real zone id") was
        # checked. Must raise a clear, actionable ValueError instead,
        # naming both the component and the bad zone_id, before any
        # layout work starts.
        with pytest.raises(ValueError, match="c1.*NO_SUCH_ZONE"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Zone"}],
                components=[{"id": "c1", "zone_id": "NO_SUCH_ZONE", "label": "Orphan"}],
                edges=[],
            )

    def test_zone_id_equal_to_component_id_raises(self):
        # Regression test: same-kind duplicate checks (component vs
        # component, zone vs zone) previously missed a zone id reused as a
        # component id. build_structured_drawio_xml's
        # all_boxes = {**component_boxes, **zone_boxes} would silently let
        # the zone's box overwrite the component's in that merge, routing
        # any edge referencing "shared" against the wrong box.
        with pytest.raises(ValueError, match="shared"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "shared", "label": "Zone"}],
                components=[{"id": "shared", "zone_id": "shared", "label": "Comp"}],
                edges=[],
            )

    def test_component_id_collides_with_another_components_generated_icon_id_raises(self):
        # Regression test: a component literally named "<other id>_icon"
        # collides with the auto-generated icon cell id of a DIFFERENT
        # component that has a shape -- two mxCell elements would end up
        # with the identical id in the emitted XML.
        with pytest.raises(ValueError, match="service_icon"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Zone"}],
                components=[
                    {"id": "service", "zone_id": "z1", "label": "Service", "shape": "mxgraph.gcp2.cloud_run"},
                    {"id": "service_icon", "zone_id": "z1", "label": "Unrelated"},
                ],
                edges=[],
            )

    def test_multiple_dangling_component_zone_references_are_all_named(self):
        with pytest.raises(ValueError, match="c1.*BAD_A.*c2.*BAD_B"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Zone"}],
                components=[
                    {"id": "c1", "zone_id": "BAD_A", "label": "Orphan A"},
                    {"id": "c2", "zone_id": "BAD_B", "label": "Orphan B"},
                ],
                edges=[],
            )

    def test_component_attached_to_a_nested_child_zone_is_not_flagged_as_dangling(self):
        # A component's zone_id correctly pointing at a NESTED (level-2)
        # zone -- e.g. a VPC inside an Account -- must not be mistaken
        # for a dangling reference just because it isn't a top-level zone.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[
                {"id": "account", "label": "Account"},
                {"id": "vpc", "label": "VPC", "parent_zone_id": "account"},
            ],
            components=[{"id": "c1", "zone_id": "vpc", "label": "Comp"}],
            edges=[],
        )
        root = ET.fromstring(xml_str)
        assert any(c.get("id") == "c1" for c in root.findall(".//mxCell"))

    def test_dangling_edge_reference_is_skipped_not_fatal(self):
        # An edge to a nonexistent component id is dropped rather than
        # crashing the whole build -- one bad edge shouldn't lose the diagram.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[{"id": "c1", "zone_id": "z1", "label": "Comp"}],
            edges=[{"source": "c1", "target": "GHOST"}],
        )
        root = ET.fromstring(xml_str)
        edge_cells = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]
        assert edge_cells == []


class TestIconShapeStyle:
    """Coverage for _style_for_icon_shape -- the fix for icons that render
    faint/blank because a bare `shape=mxgraph.aws4.<name>;fillColor=...;` is
    not a registered stencil for most individual AWS4 service icons (only
    confirmed via a real draw.io-generated AWS reference export -- see the
    function's own docstring). Mirrors samples/GCP/ProcessEngineering's
    already-verified _style_for_shape_ref."""

    def test_most_aws4_icons_are_wrapped_in_the_resource_icon_carrier(self):
        style = layout._style_for_icon_shape("mxgraph.aws4.lambda", "#ED7100")
        assert "shape=mxgraph.aws4.resourceIcon;" in style
        assert "resIcon=mxgraph.aws4.lambda;" in style
        assert "fillColor=#ED7100;" in style
        # The bare, non-rendering form must never be emitted for this case.
        assert "shape=mxgraph.aws4.lambda;" not in style

    def test_aws4_dedicated_shapes_stay_bare(self):
        style = layout._style_for_icon_shape("mxgraph.aws4.nat_gateway", "#8C4FFF")
        assert "shape=mxgraph.aws4.nat_gateway;" in style
        assert "resIcon=" not in style
        assert "fillColor=#8C4FFF;" in style

    def test_aws4_group_shapes_stay_bare(self):
        style = layout._style_for_icon_shape("mxgraph.aws4.group_vpc2", "#8C4FFF")
        assert "shape=mxgraph.aws4.group_vpc2;" in style
        assert "resIcon=" not in style

    def test_azure_svg_path_uses_image_not_shape(self):
        style = layout._style_for_icon_shape("img/lib/azure2/compute/Virtual_Machine.svg", "#0078D4")
        assert style.startswith("image;")
        assert "image=img/lib/azure2/compute/Virtual_Machine.svg;" in style
        assert "shape=" not in style

    def test_data_uri_uses_image_not_shape(self):
        style = layout._style_for_icon_shape("data:image/svg+xml;base64,AAAA", "#4285F4")
        assert style.startswith("image;")

    def test_gcp2_shape_stays_bare(self):
        style = layout._style_for_icon_shape("mxgraph.gcp2.cloud_run", "#4285F4")
        assert style == "shape=mxgraph.gcp2.cloud_run;fillColor=#4285F4;strokeColor=none;html=1;"

    def test_build_structured_drawio_xml_renders_aws4_icons_via_the_resource_icon_carrier(self):
        # End-to-end: confirms the real pipeline actually uses the fixed
        # helper, not just that the helper itself is correct in isolation.
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[{
                "id": "c1", "zone_id": "z1", "label": "Fn",
                "shape": "mxgraph.aws4.lambda", "icon_color": "#ED7100",
            }],
            edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        icon_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "c1_icon")
        assert "resIcon=mxgraph.aws4.lambda;" in icon_cell.get("style", "")


class TestVpcZoneContainer:
    """Coverage for the "type": "vpc" zone style -- a VPC/VNet boundary
    renders using each provider's REAL container convention instead of the
    generic flat swimlane, per the request that cloud architecture diagrams
    use VPC containers whenever possible, with visible (not faint) icons
    inside them."""

    def _zone_cell(self, root, zone_id):
        return next(c for c in root.findall(".//mxCell") if c.get("id") == zone_id)

    def test_aws_vpc_zone_uses_the_native_group_vpc_shape(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "vpc1", "label": "App VPC", "type": "vpc"}],
            components=[{"id": "c1", "zone_id": "vpc1", "label": "Comp"}],
            edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        style = self._zone_cell(root, "vpc1").get("style", "")
        assert "shape=mxgraph.aws4.group;" in style
        assert "grIcon=mxgraph.aws4.group_vpc2;" in style
        assert "strokeColor=#8C4FFF;" in style
        assert "swimlane" not in style

    def test_gcp_vpc_zone_uses_the_pastel_container_rectangle(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "vpc1", "label": "App VPC", "type": "vpc"}],
            components=[{"id": "c1", "zone_id": "vpc1", "label": "Comp"}],
            edges=[], provider="gcp",
        )
        root = ET.fromstring(xml_str)
        style = self._zone_cell(root, "vpc1").get("style", "")
        assert "shape=rect;" in style
        assert "fillColor=#E3F2FD;" in style
        assert "strokeColor=none;" in style
        assert "swimlane" not in style

    def test_azure_vpc_zone_gets_a_dashed_border_and_a_vnet_corner_badge(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "vpc1", "label": "App VNet", "type": "vpc", "width": 340}],
            components=[{"id": "c1", "zone_id": "vpc1", "label": "Comp"}],
            edges=[], provider="azure",
        )
        root = ET.fromstring(xml_str)
        style = self._zone_cell(root, "vpc1").get("style", "")
        assert "dashed=1;" in style
        assert "strokeColor=#0078D4;" in style
        badge = next(c for c in root.findall(".//mxCell") if c.get("id") == "vpc1_badge")
        assert badge.get("parent") == "vpc1"
        assert "img/lib/azure2/networking/Virtual_Networks.svg" in badge.get("style", "")

    def test_vpc_zone_color_override_is_honored(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "vpc1", "label": "App VPC", "type": "vpc", "color": "#123456"}],
            components=[{"id": "c1", "zone_id": "vpc1", "label": "Comp"}],
            edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        style = self._zone_cell(root, "vpc1").get("style", "")
        assert "strokeColor=#123456;" in style

    def test_vpc_zone_components_are_still_positioned_without_overlap(self):
        # The VPC container swaps out swimlane for a different cell style,
        # but must not change the reserved header space the layout engine
        # already computed -- components must still sit inside the zone,
        # not overlapping its own label area.
        zones = [{"id": "vpc1", "label": "App VPC", "type": "vpc"}]
        components = [
            {"id": "c1", "zone_id": "vpc1", "label": "A", "shape": "mxgraph.gcp2.cloud_run"},
            {"id": "c2", "zone_id": "vpc1", "label": "B", "shape": "mxgraph.gcp2.cloud_sql"},
        ]
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        zbox = zone_boxes["vpc1"]
        for box in comp_boxes.values():
            assert box.x >= zbox.x
            assert box.right <= zbox.right
            assert box.y >= zbox.y + layout.ZONE_HEADER_H_PLAIN

    def test_plain_zone_without_type_is_unaffected(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[{"id": "c1", "zone_id": "z1", "label": "Comp"}],
            edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        style = self._zone_cell(root, "z1").get("style", "")
        assert "swimlane" in style
        assert "shape=mxgraph.aws4.group" not in style


class TestNestedZones:
    """Coverage for "parent_zone_id" -- a zone nested inside another (e.g. a
    VPC inside an AWS Account), the real-world shape that was missing: a
    landing-zone/multi-account diagram has no single zone that IS a VPC, it
    has Account zones that each CONTAIN one. Regression target: every
    existing (non-nested) test above must keep passing unchanged, since
    this only adds a new code path gated on parent_zone_id being present."""

    def _account_and_vpc(self, vpc_type="vpc", vpc_extra=None):
        zones = [
            {"id": "acct", "label": "Workload Account", "row": 0},
            {"id": "vpc", "label": "App VPC", "parent_zone_id": "acct", "type": vpc_type, **(vpc_extra or {})},
        ]
        components = [
            {"id": "rds", "zone_id": "vpc", "label": "RDS", "shape": "mxgraph.aws4.rds"},
            {"id": "ddb", "zone_id": "vpc", "label": "DynamoDB", "shape": "mxgraph.aws4.dynamodb_2"},
        ]
        return zones, components

    def test_nested_zone_box_sits_strictly_inside_its_parent(self):
        zones, components = self._account_and_vpc()
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        acct, vpc = zone_boxes["acct"], zone_boxes["vpc"]
        assert vpc.x > acct.x
        assert vpc.y > acct.y
        assert vpc.right < acct.right
        assert vpc.bottom < acct.bottom

    def test_components_of_the_nested_zone_sit_inside_the_nested_zone_not_the_account(self):
        zones, components = self._account_and_vpc()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        vpc = zone_boxes["vpc"]
        for cid in ("rds", "ddb"):
            box = comp_boxes[cid]
            assert box.x >= vpc.x
            assert box.right <= vpc.right
            assert box.y >= vpc.y
            assert box.bottom <= vpc.bottom

    def test_account_zone_grows_to_fit_its_nested_vpc(self):
        zones, components = self._account_and_vpc()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        acct, vpc = zone_boxes["acct"], zone_boxes["vpc"]
        # The account must be tall/wide enough to actually contain the VPC
        # plus its own margins, not just clip to the VPC's own box.
        assert acct.w > vpc.w
        assert acct.h > vpc.h

    def test_nested_zone_renders_with_parent_cell_id_and_local_coordinates(self):
        zones, components = self._account_and_vpc()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components, edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        acct, vpc = zone_boxes["acct"], zone_boxes["vpc"]

        acct_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "acct")
        assert acct_cell.get("parent") == "1"

        vpc_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "vpc")
        assert vpc_cell.get("parent") == "acct"
        geom = vpc_cell.find("./mxGeometry")
        assert float(geom.get("x")) == pytest.approx(vpc.x - acct.x)
        assert float(geom.get("y")) == pytest.approx(vpc.y - acct.y)

    def test_nested_vpc_zone_still_gets_the_real_vpc_container_style(self):
        zones, components = self._account_and_vpc()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components, edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        vpc_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "vpc")
        style = vpc_cell.get("style", "")
        assert "shape=mxgraph.aws4.group;" in style
        assert "grIcon=mxgraph.aws4.group_vpc2;" in style
        assert "swimlane" not in style

    def test_account_parent_keeps_the_plain_swimlane_style(self):
        zones, components = self._account_and_vpc()
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components, edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        acct_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "acct")
        style = acct_cell.get("style", "")
        assert "swimlane" in style
        assert "shape=mxgraph.aws4.group" not in style

    def test_account_level_direct_components_stack_below_the_nested_vpc(self):
        zones = [
            {"id": "acct", "label": "Account", "row": 0},
            {"id": "vpc", "label": "VPC", "parent_zone_id": "acct", "type": "vpc"},
        ]
        components = [
            {"id": "net_rsc", "zone_id": "vpc", "label": "NAT GW", "shape": "mxgraph.aws4.nat_gateway"},
            {"id": "iam", "zone_id": "acct", "label": "IAM Role"},
        ]
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        vpc_box, iam_box = zone_boxes["vpc"], comp_boxes["iam"]
        assert iam_box.y > vpc_box.bottom
        acct_box = zone_boxes["acct"]
        assert iam_box.x >= acct_box.x
        assert iam_box.right <= acct_box.right

    def test_two_nested_zones_stack_vertically_without_overlap(self):
        zones = [
            {"id": "acct", "label": "Account", "row": 0},
            {"id": "vpc_a", "label": "VPC A", "parent_zone_id": "acct"},
            {"id": "vpc_b", "label": "VPC B", "parent_zone_id": "acct"},
        ]
        components = [
            {"id": "a1", "zone_id": "vpc_a", "label": "A1"},
            {"id": "b1", "zone_id": "vpc_b", "label": "B1"},
        ]
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        va, vb = zone_boxes["vpc_a"], zone_boxes["vpc_b"]
        assert vb.y >= va.bottom
        acct = zone_boxes["acct"]
        for z in (va, vb):
            assert z.x >= acct.x
            assert z.right <= acct.right

    def test_nested_zone_without_explicit_width_fills_the_parents_inner_width(self):
        zones, components = self._account_and_vpc()
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        acct, vpc = zone_boxes["acct"], zone_boxes["vpc"]
        assert vpc.w == pytest.approx(acct.w - 2 * layout.COMPONENT_H_MARGIN)

    def test_nested_zone_respects_its_own_explicit_width(self):
        zones, components = self._account_and_vpc(vpc_extra={"width": 250})
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        assert zone_boxes["vpc"].w == pytest.approx(250)

    def test_multiple_accounts_each_with_their_own_vpc_do_not_overlap(self):
        zones = [
            {"id": "acct1", "label": "Account 1", "row": 0},
            {"id": "acct2", "label": "Account 2", "row": 0},
            {"id": "vpc1", "label": "VPC 1", "parent_zone_id": "acct1", "type": "vpc"},
            {"id": "vpc2", "label": "VPC 2", "parent_zone_id": "acct2", "type": "vpc"},
        ]
        components = [
            {"id": "c1", "zone_id": "vpc1", "label": "C1", "shape": "mxgraph.aws4.rds"},
            {"id": "c2", "zone_id": "vpc2", "label": "C2", "shape": "mxgraph.aws4.rds"},
        ]
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        acct1, acct2 = zone_boxes["acct1"], zone_boxes["acct2"]
        assert not _boxes_overlap(acct1, acct2)
        vpc1, vpc2 = zone_boxes["vpc1"], zone_boxes["vpc2"]
        assert vpc1.x >= acct1.x and vpc1.right <= acct1.right
        assert vpc2.x >= acct2.x and vpc2.right <= acct2.right

    def test_dangling_parent_zone_id_raises(self):
        with pytest.raises(KeyError):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "vpc", "label": "VPC", "parent_zone_id": "NO_SUCH_ZONE"}],
                components=[],
                edges=[],
            )

    def test_merged_field_parent_zone_id_raises_with_a_specific_diagnosis(self):
        # Regression test, confirmed directly against a real generated
        # request: the model produced parent_zone_id="saas_vpc,row:0,
        # stack:horizontal" -- "row"/"stack" (which belong as the zone's
        # OWN separate top-level keys) collapsed into the reference
        # string alongside the real id. A bare "does not match any zone
        # id" message gives no hint why; this specific pattern must be
        # called out by name so the agent has something concrete to fix.
        with pytest.raises(KeyError, match="MULTIPLE fields got merged"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[
                    {"id": "saas_vpc", "label": "VPC"},
                    {
                        "id": "saas_vpc_compute", "label": "Compute",
                        "parent_zone_id": "saas_vpc,row:0,stack:horizontal",
                    },
                ],
                components=[],
                edges=[],
            )

    def test_merged_field_component_zone_id_raises_with_a_specific_diagnosis(self):
        with pytest.raises(KeyError, match="MULTIPLE fields got merged"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Zone"}],
                components=[{"id": "c1", "zone_id": "z1,row:0,stack:horizontal", "label": "Comp"}],
                edges=[],
            )

    def test_self_referential_parent_zone_id_raises(self):
        with pytest.raises(ValueError, match="own id"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Z1", "parent_zone_id": "z1"}],
                components=[],
                edges=[],
            )

    def test_two_levels_of_nesting_is_supported(self):
        # Raised from "exactly one level" after a real request (AWS
        # Organizations -> per-tenant Account -> VPC -> an inner
        # monitoring-agent boundary) legitimately needed a third zone
        # level and had no way to express it -- confirmed directly: the
        # agent kept retrying ever-deeper nesting attempts, all rejected.
        zones = [
            {"id": "acct", "label": "Account"},
            {"id": "vpc", "label": "VPC", "parent_zone_id": "acct"},
            {"id": "subnet", "label": "Subnet", "parent_zone_id": "vpc"},
        ]
        components = [{"id": "c1", "zone_id": "subnet", "label": "Comp"}]
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        acct, vpc, subnet = zone_boxes["acct"], zone_boxes["vpc"], zone_boxes["subnet"]
        # Each level strictly contains the next.
        assert vpc.x > acct.x and vpc.right < acct.right
        assert vpc.y > acct.y and vpc.bottom < acct.bottom
        assert subnet.x > vpc.x and subnet.right < vpc.right
        assert subnet.y > vpc.y and subnet.bottom < vpc.bottom
        # The depth-2 zone's own component sits inside IT, not just
        # somewhere inside the outer ancestors.
        c1 = comp_boxes["c1"]
        assert c1.x >= subnet.x and c1.right <= subnet.right
        assert c1.y >= subnet.y and c1.bottom <= subnet.bottom

    def test_two_levels_of_nesting_renders_with_correct_parent_chain(self):
        zones = [
            {"id": "acct", "label": "Account"},
            {"id": "vpc", "label": "VPC", "parent_zone_id": "acct", "type": "vpc"},
            {"id": "subnet", "label": "Subnet", "parent_zone_id": "vpc"},
        ]
        components = [{"id": "c1", "zone_id": "subnet", "label": "Comp"}]
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components, edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        acct_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "acct")
        vpc_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "vpc")
        subnet_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "subnet")
        assert acct_cell.get("parent") == "1"
        assert vpc_cell.get("parent") == "acct"
        assert subnet_cell.get("parent") == "vpc"

    def test_nesting_depth_has_no_fixed_limit(self):
        # An earlier version capped this first at 1 level, then at 2 --
        # both caps were hit in turn by the SAME real request (AWS
        # Organizations -> per-tenant Account -> VPC -> an inner
        # monitoring-agent boundary needed a fourth zone level once the
        # cap was already raised to 2), so the cap was removed rather
        # than raised a third time. Depth 3 (4 total zone levels) must
        # now succeed, containment holding all the way down.
        zones = [
            {"id": "acct", "label": "Account"},
            {"id": "vpc", "label": "VPC", "parent_zone_id": "acct"},
            {"id": "subnet", "label": "Subnet", "parent_zone_id": "vpc"},
            {"id": "inner", "label": "Inner", "parent_zone_id": "subnet"},
        ]
        components = [{"id": "c1", "zone_id": "inner", "label": "Comp"}]
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        acct, vpc, subnet, inner = (
            zone_boxes["acct"], zone_boxes["vpc"], zone_boxes["subnet"], zone_boxes["inner"],
        )
        assert vpc.x > acct.x and vpc.right < acct.right
        assert subnet.x > vpc.x and subnet.right < vpc.right
        assert inner.x > subnet.x and inner.right < subnet.right
        c1 = comp_boxes["c1"]
        assert c1.x >= inner.x and c1.right <= inner.right

        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components, edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        inner_cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "inner")
        assert inner_cell.get("parent") == "subnet"

    def test_circular_parent_zone_id_chain_raises(self):
        with pytest.raises(ValueError, match="circular"):
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[
                    {"id": "a", "label": "A", "parent_zone_id": "b"},
                    {"id": "b", "label": "B", "parent_zone_id": "a"},
                ],
                components=[],
                edges=[],
            )

    def test_horizontal_stack_of_accounts_each_with_a_depth_2_descendant(self):
        # OU (horizontal) -> 2 peer Accounts, each itself containing a
        # VPC (depth 1) that contains a Subnet (depth 2) -- exercises the
        # RECURSIVE natural-width calc (_zone_outer_natural_width calling
        # itself for a middle zone that has its own nested children) at
        # the same time as sibling horizontal placement.
        zones = [
            {"id": "ou", "label": "OU", "stack": "horizontal"},
            {"id": "acct0", "label": "Account 0", "parent_zone_id": "ou"},
            {"id": "acct1", "label": "Account 1", "parent_zone_id": "ou"},
            {"id": "vpc0", "label": "VPC 0", "parent_zone_id": "acct0"},
            {"id": "vpc1", "label": "VPC 1", "parent_zone_id": "acct1"},
        ]
        components = [
            {"id": "sub0", "zone_id": "vpc0", "label": "Sub 0"},
            {"id": "sub1", "zone_id": "vpc1", "label": "Sub 1"},
        ]
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        acct0, acct1 = zone_boxes["acct0"], zone_boxes["acct1"]
        vpc0, vpc1 = zone_boxes["vpc0"], zone_boxes["vpc1"]
        assert not _boxes_overlap(acct0, acct1)
        assert vpc0.x >= acct0.x and vpc0.right <= acct0.right
        assert vpc1.x >= acct1.x and vpc1.right <= acct1.right
        sub0, sub1 = comp_boxes["sub0"], comp_boxes["sub1"]
        assert sub0.x >= vpc0.x and sub0.right <= vpc0.right
        assert sub1.x >= vpc1.x and sub1.right <= vpc1.right

    def test_account_grows_to_fit_a_depth_2_descendant(self):
        # The outermost zone must be wide/tall enough to actually contain
        # BOTH nested levels plus margins, not just the immediate child.
        zones = [
            {"id": "acct", "label": "Account"},
            {"id": "vpc", "label": "VPC", "parent_zone_id": "acct"},
            {"id": "subnet", "label": "Subnet", "parent_zone_id": "vpc", "width": 400},
        ]
        components = [{"id": "c1", "zone_id": "subnet", "label": "Comp"}]
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        acct, vpc, subnet = zone_boxes["acct"], zone_boxes["vpc"], zone_boxes["subnet"]
        assert acct.w > vpc.w > 0
        assert vpc.w >= subnet.w

    def test_unrelated_top_level_zone_is_unaffected_by_a_sibling_with_nesting(self):
        # A top-level zone with NO nested children in the same diagram must
        # keep going through the untouched, pre-nesting leaf code path.
        zones = [
            {"id": "acct", "label": "Account", "row": 0},
            {"id": "vpc", "label": "VPC", "parent_zone_id": "acct"},
            {"id": "plain", "label": "Plain Zone", "row": 0},
        ]
        components = [
            {"id": "c1", "zone_id": "vpc", "label": "C1"},
            {"id": "c2", "zone_id": "plain", "label": "C2", "bullets": ["x"]},
        ]
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        plain = zone_boxes["plain"]
        c2 = comp_boxes["c2"]
        assert c2.x >= plain.x
        assert c2.right <= plain.right
        assert not _boxes_overlap(zone_boxes["acct"], plain)


class TestHorizontalNestedZones:
    """Coverage for "stack": "horizontal" on a parent zone with nested
    children -- regression target for a real generated diagram where every
    nested zone always stacked vertically regardless of how many peer
    siblings there were (5 sibling Accounts, each itself containing a VPC),
    producing an extremely tall single-column "tower" (6212px tall, 432px
    wide) that the user explicitly asked to fix by favoring horizontal over
    vertical stacking."""

    def _ou_with_accounts(self, n=3, stack="horizontal"):
        zones = [{"id": "ou", "label": "OU", "row": 0, "stack": stack}]
        components = []
        for i in range(n):
            zones.append({"id": f"acct{i}", "label": f"Account {i}", "parent_zone_id": "ou"})
            components.append({"id": f"c{i}", "zone_id": f"acct{i}", "label": f"Comp {i}"})
        return zones, components

    def test_horizontal_nested_siblings_sit_side_by_side_not_stacked(self):
        zones, components = self._ou_with_accounts(n=3)
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        a0, a1, a2 = zone_boxes["acct0"], zone_boxes["acct1"], zone_boxes["acct2"]
        # Same row (same y), increasing x -- not the vertical-stack shape
        # (same x, increasing y) the default produces.
        assert a0.y == a1.y == a2.y
        assert a1.x > a0.right
        assert a2.x > a1.right

    def test_horizontal_nested_siblings_do_not_overlap(self):
        zones, components = self._ou_with_accounts(n=5)
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        accounts = [zone_boxes[f"acct{i}"] for i in range(5)]
        for i in range(len(accounts)):
            for j in range(i + 1, len(accounts)):
                assert not _boxes_overlap(accounts[i], accounts[j])

    def test_horizontal_nested_siblings_stay_inside_their_parent(self):
        zones, components = self._ou_with_accounts(n=4)
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        ou = zone_boxes["ou"]
        for i in range(4):
            acct = zone_boxes[f"acct{i}"]
            assert acct.x >= ou.x
            assert acct.right <= ou.right
            assert acct.bottom <= ou.bottom

    def test_horizontal_stacking_produces_a_wider_shorter_parent_than_vertical(self):
        # The whole point of the feature: for the same content, horizontal
        # must be wider and (consequently) shorter than vertical stacking
        # -- not just geometrically valid, but actually fixing the "tower"
        # complaint.
        h_zones, h_components = self._ou_with_accounts(n=5, stack="horizontal")
        v_zones, v_components = self._ou_with_accounts(n=5, stack="vertical")
        h_boxes, _, _, _ = layout._layout_zones_and_components(h_zones, h_components)
        v_boxes, _, _, _ = layout._layout_zones_and_components(v_zones, v_components)
        assert h_boxes["ou"].w > v_boxes["ou"].w
        assert h_boxes["ou"].h < v_boxes["ou"].h

    def test_single_horizontal_nested_child_is_centered(self):
        zones, components = self._ou_with_accounts(n=1)
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        ou, acct = zone_boxes["ou"], zone_boxes["acct0"]
        assert acct.cx == pytest.approx(ou.cx, abs=1)

    def test_horizontal_nested_children_stretch_to_fill_an_explicitly_wide_parent(self):
        zones, components = self._ou_with_accounts(n=2)
        zones[0]["width"] = 1200
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        a0, a1 = zone_boxes["acct0"], zone_boxes["acct1"]
        ou = zone_boxes["ou"]
        # No big dead-space gap left unused past the last child.
        assert ou.right - a1.right == pytest.approx(layout.COMPONENT_H_MARGIN, abs=1)
        assert a1.x > a0.right

    def test_direct_components_of_a_horizontal_parent_stack_below_the_nested_row(self):
        zones = [
            {"id": "ou", "label": "OU", "row": 0, "stack": "horizontal"},
            {"id": "acct0", "label": "Account 0", "parent_zone_id": "ou"},
            {"id": "acct1", "label": "Account 1", "parent_zone_id": "ou"},
        ]
        components = [
            {"id": "c0", "zone_id": "acct0", "label": "C0"},
            {"id": "c1", "zone_id": "acct1", "label": "C1"},
            {"id": "direct", "zone_id": "ou", "label": "Direct"},
        ]
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        a0, a1 = zone_boxes["acct0"], zone_boxes["acct1"]
        direct = comp_boxes["direct"]
        assert direct.y > max(a0.bottom, a1.bottom)
        ou = zone_boxes["ou"]
        assert direct.x >= ou.x
        assert direct.right <= ou.right

    def test_horizontal_nested_zone_renders_with_correct_parent_and_local_coords(self):
        zones, components = self._ou_with_accounts(n=2)
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="", zones=zones, components=components, edges=[], provider="aws",
        )
        root = ET.fromstring(xml_str)
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        ou, a1 = zone_boxes["ou"], zone_boxes["acct1"]

        cell = next(c for c in root.findall(".//mxCell") if c.get("id") == "acct1")
        assert cell.get("parent") == "ou"
        geom = cell.find("./mxGeometry")
        assert float(geom.get("x")) == pytest.approx(a1.x - ou.x)
        assert float(geom.get("y")) == pytest.approx(a1.y - ou.y)

    def test_default_stack_still_stacks_nested_children_vertically(self):
        # Regression guard: omitting "stack" entirely must keep the
        # original (pre-horizontal-support) vertical tower behavior --
        # this feature is opt-in, not a change in default.
        zones, components = self._ou_with_accounts(n=3, stack=None)
        del zones[0]["stack"]
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        a0, a1, a2 = zone_boxes["acct0"], zone_boxes["acct1"], zone_boxes["acct2"]
        assert a0.x == a1.x == a2.x
        assert a1.y > a0.bottom
        assert a2.y > a1.bottom
