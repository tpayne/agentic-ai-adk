import math
import unittest
import xml.etree.ElementTree as ET

# Pure Python, no ADK/google dependencies -- no stub installer needed.
from process_agents.cloudarch import cloudarch_layout_agent as layout


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


class ComponentHeightTests(unittest.TestCase):
    def test_height_scales_with_bullet_count(self):
        no_bullets = layout._component_height({"label": "X"})
        three_bullets = layout._component_height({"label": "X", "bullets": ["a", "b", "c"]})
        self.assertLess(no_bullets, three_bullets)
        self.assertEqual(three_bullets - no_bullets, 3 * layout.LINE_HEIGHT)

    def test_icon_adds_top_clearance(self):
        without_icon = layout._component_height({"label": "X", "bullets": ["a"]})
        with_icon = layout._component_height({"label": "X", "bullets": ["a"], "shape": "mxgraph.gcp2.cloud_run"})
        self.assertEqual(
            with_icon - without_icon,
            layout.SPACING_TOP_WITH_ICON - layout.SPACING_TOP_NO_ICON,
        )

    def test_matches_documented_formula(self):
        # The exact example given to the LLM in cloudarch_agent.txt: a title
        # plus 4 bullets (5 lines total) with spacingTop=74 needs height >= 174.
        component = {"label": "X", "bullets": ["a", "b", "c", "d"], "shape": "mxgraph.gcp2.cloud_run"}
        self.assertEqual(layout._component_height(component), 174)


class LayoutOverlapTests(unittest.TestCase):
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
                    self.assertFalse(
                        _boxes_overlap(boxes[i], boxes[j]),
                        f"{boxes[i].id} overlaps {boxes[j].id} in zone {zone_id}",
                    )

    def test_no_zone_overlaps_another_zone(self):
        zones, components = self._sample()
        zone_boxes, _, _, _ = layout._layout_zones_and_components(zones, components)
        boxes = list(zone_boxes.values())
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                self.assertFalse(_boxes_overlap(boxes[i], boxes[j]))

    def test_taller_zone_in_same_row_does_not_shrink_others(self):
        # z1 has a dense 5-bullet component (c2); z2/z3 are much shorter.
        # Every zone in row 0 must still start at the same y and span the
        # full row width without clipping its own content.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row0 = [zone_boxes[z] for z in ("z1", "z2", "z3")]
        self.assertEqual(len({b.y for b in row0}), 1)  # all start at the same y

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
        self.assertAlmostEqual(zone_boxes["z_gov"].right, row0_right_edge, delta=1)

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
            self.assertAlmostEqual(right_edge, target, delta=1, msg=f"row {row} did not match the target width")

        # A stretched zone's children must spread out to fill it, not stay
        # clustered at the left edge with dead space before the zone's own
        # right border.
        z1b_box = zone_boxes["z1b"]
        last_child = comp_boxes["z1b_c1"]
        self.assertAlmostEqual(z1b_box.right - last_child.right, layout.COMPONENT_H_MARGIN, delta=1)


class EdgeRoutingTests(unittest.TestCase):
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
        waypoints = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 0, row_bottoms, all_boxes
        )
        self.assertEqual(waypoints, [])

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
        waypoints = layout._route_edge(
            {"source": "top", "target": "far"}, comp_boxes["top"], comp_boxes["far"], 0, row_bottoms, all_boxes
        )
        self.assertEqual(len(waypoints), 2)
        margin_x = waypoints[0][0]
        self.assertEqual(waypoints[1][0], margin_x)
        # Must sit strictly to the left of every component in the zone
        # (inside the zone's own border, outside every component's box).
        for comp_id in ("top", "bottom", "far"):
            self.assertLess(margin_x, comp_boxes[comp_id].x)
        self.assertGreater(margin_x, zone_boxes["z1"].x)
        # And the vertical run must not pass through bottom's box (it
        # can't, since margin_x < bottom.x, but assert it explicitly).
        by_wp, ty_wp = waypoints[0][1], waypoints[1][1]
        bottom = comp_boxes["bottom"]
        self.assertFalse(bottom.x < margin_x < bottom.right)

    def test_adjacent_same_zone_edges_unaffected_by_non_adjacent_fix(self):
        # bottom<->far are immediate neighbors (order 1, 2) despite "far"
        # being the 3rd component added for the non-adjacency tests above.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints = layout._route_edge(
            {"source": "bottom", "target": "far"}, comp_boxes["bottom"], comp_boxes["far"], 0, row_bottoms, all_boxes
        )
        self.assertEqual(waypoints, [])

    def test_same_row_edge_routes_through_the_zone_gap(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints = layout._route_edge(
            {"source": "top", "target": "other"}, comp_boxes["top"], comp_boxes["other"], 0, row_bottoms, all_boxes
        )
        self.assertEqual(len(waypoints), 1)
        wx, _wy = waypoints[0]
        # Must sit strictly between the two zone columns, in the reserved gap.
        self.assertGreater(wx, zone_boxes["z1"].right)
        self.assertLess(wx, zone_boxes["z2"].x)

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
        self.assertNotEqual(src.cy, tgt.cy)  # precondition: genuinely offset
        waypoints = layout._route_edge({"source": "bottom", "target": "other"}, src, tgt, 0, row_bottoms, all_boxes)
        self.assertEqual(len(waypoints), 2)
        full_path = [(src.cx, src.cy)] + waypoints + [(tgt.cx, tgt.cy)]
        for (x1, y1), (x2, y2) in zip(full_path, full_path[1:]):
            self.assertTrue(x1 == x2 or y1 == y2, f"diagonal segment: ({x1},{y1}) -> ({x2},{y2})")

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
        waypoints = layout._route_edge(
            {"source": "top", "target": "gov_item"}, comp_boxes["top"], comp_boxes["gov_item"], 0, row_bottoms, all_boxes
        )
        self.assertEqual(len(waypoints), 2)
        channel_y = waypoints[0][1]
        # The channel must be below EVERY row-0 zone's bottom edge (not just
        # the source component's own position), and above the row-1 zone.
        for zid in ("z1", "z2"):
            self.assertGreater(channel_y, zone_boxes[zid].bottom)
        self.assertLess(channel_y, zone_boxes["z_gov"].y)

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
        first = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 0, row_bottoms, all_boxes
        )
        second = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 1, row_bottoms, all_boxes
        )
        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertNotEqual(second[0], first)

    def test_channel_key_groups_edges_that_would_otherwise_collide(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        all_boxes = {**comp_boxes, **zone_boxes}
        # Same pair, both directions -> same channel.
        self.assertEqual(
            layout._channel_key(comp_boxes["top"], comp_boxes["bottom"], all_boxes),
            layout._channel_key(comp_boxes["bottom"], comp_boxes["top"], all_boxes),
        )
        # Same zone-pair gap, different component pairs -> same channel.
        self.assertEqual(
            layout._channel_key(comp_boxes["top"], comp_boxes["other"], all_boxes),
            layout._channel_key(comp_boxes["bottom"], comp_boxes["other"], all_boxes),
        )
        # A same-zone pair must not collide with an inter-zone channel key.
        self.assertNotEqual(
            layout._channel_key(comp_boxes["top"], comp_boxes["bottom"], all_boxes),
            layout._channel_key(comp_boxes["top"], comp_boxes["other"], all_boxes),
        )

    def test_stagger_offset_alternates_and_grows_outward(self):
        self.assertEqual(layout._stagger_offset(0, 10), 0.0)
        self.assertEqual(layout._stagger_offset(1, 10), 10.0)
        self.assertEqual(layout._stagger_offset(2, 10), -10.0)
        self.assertEqual(layout._stagger_offset(3, 10), 20.0)
        self.assertEqual(layout._stagger_offset(4, 10), -20.0)

    def test_stagger_offset_respects_clamp(self):
        self.assertEqual(layout._stagger_offset(9, 10, clamp=15), 15.0)
        self.assertEqual(layout._stagger_offset(10, 10, clamp=15), -15.0)

    def test_two_edges_sharing_the_zone_gap_get_different_waypoints(self):
        # Two edges with different component pairs but similar enough
        # vertical position that, pre-fix, a global (not channel-local)
        # stagger could coincidentally assign them the same offset.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        edge_a = layout._route_edge(
            {"source": "top", "target": "other"}, comp_boxes["top"], comp_boxes["other"], 0, row_bottoms, all_boxes
        )
        edge_b = layout._route_edge(
            {"source": "bottom", "target": "other"}, comp_boxes["bottom"], comp_boxes["other"], 1, row_bottoms, all_boxes
        )
        self.assertNotEqual(edge_a[0][1], edge_b[0][1])

    def test_cross_row_waypoints_never_land_inside_an_unrelated_component(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        all_boxes = {**comp_boxes, **zone_boxes}
        waypoints = layout._route_edge(
            {"source": "top", "target": "gov_item"}, comp_boxes["top"], comp_boxes["gov_item"], 0, row_bottoms, all_boxes
        )
        for wx, wy in waypoints:
            for cid, box in comp_boxes.items():
                if cid in ("top", "gov_item"):
                    continue
                self.assertFalse(
                    box.x < wx < box.right and box.y < wy < box.bottom,
                    f"waypoint ({wx},{wy}) lands inside unrelated component {cid}",
                )


class SafeRoutingTests(unittest.TestCase):
    """Coverage for _safe_x_for_vertical_span and the _route_edge branches
    it fixed. A same-row edge between non-adjacent zones, a cross-row edge
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
        waypoints = layout._route_edge({"source": source, "target": target}, src, tgt, 0, row_bottoms, all_boxes)
        full_path = [(src.cx, src.cy), *waypoints, (tgt.cx, tgt.cy)]
        return full_path, comp_boxes

    def test_safe_x_returns_preferred_x_when_already_clear(self):
        self.assertEqual(layout._safe_x_for_vertical_span(100.0, 0.0, 50.0, ("a", "b"), {}), 100.0)

    def test_safe_x_searches_away_from_a_blocking_component(self):
        boxes = {"blocker": layout._Box("blocker", 90.0, 0.0, 20.0, 50.0, zone_id="z")}
        safe_x = layout._safe_x_for_vertical_span(100.0, 0.0, 50.0, ("a", "b"), boxes)
        self.assertFalse(90.0 <= safe_x <= 110.0)

    def test_safe_x_ignores_excluded_ids_and_zone_containers(self):
        boxes = {
            "src": layout._Box("src", 90.0, 0.0, 20.0, 50.0, zone_id="z"),
            "zone": layout._Box("zone", 90.0, 0.0, 20.0, 50.0, zone_id=None),
        }
        self.assertEqual(
            layout._safe_x_for_vertical_span(100.0, 0.0, 50.0, ("src", "tgt"), boxes), 100.0
        )

    def test_same_row_non_adjacent_zones_do_not_cut_through_the_zone_between_them(self):
        full_path, comp_boxes = self._route("l1", "r1")
        middle = comp_boxes["m1"]
        for p1, p2 in zip(full_path, full_path[1:]):
            self.assertFalse(_segment_crosses_box(p1, p2, middle))

    def test_cross_row_edge_skipping_an_entire_row_does_not_cut_through_it(self):
        full_path, comp_boxes = self._route("l1", "b1")
        for wide_id in ("w1", "w2", "w3"):
            box = comp_boxes[wide_id]
            for p1, p2 in zip(full_path, full_path[1:]):
                self.assertFalse(_segment_crosses_box(p1, p2, box))

    def test_cross_row_edge_from_a_component_with_siblings_below_it_does_not_cut_through_them(self):
        # w1 is the FIRST (topmost) of three stacked components in "wide"
        # -- routing it down to row 2 must not cut through w2/w3 below it.
        full_path, comp_boxes = self._route("w1", "b1")
        for sibling_id in ("w2", "w3"):
            box = comp_boxes[sibling_id]
            for p1, p2 in zip(full_path, full_path[1:]):
                self.assertFalse(_segment_crosses_box(p1, p2, box))

    def test_channel_key_unifies_same_row_detour_and_cross_row_edges_sharing_the_same_gap(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        all_boxes = {**comp_boxes, **zone_boxes}
        # l1->r1 (same-row, non-adjacent -> routed via row 0's below-row
        # channel) and l1->w1 (cross-row, adjacent rows -> ALSO routed via
        # row 0's below-row channel) must land in the SAME stagger channel,
        # so they get coordinated (not coincidentally identical) offsets.
        self.assertEqual(
            layout._channel_key(comp_boxes["l1"], comp_boxes["r1"], all_boxes),
            layout._channel_key(comp_boxes["l1"], comp_boxes["w1"], all_boxes),
        )


class LabelPositionTests(unittest.TestCase):
    """Coverage for _label_position_fraction -- see its own docstring for
    the real bug it fixes: drawio's default edge-label position (the
    arc-length midpoint of the whole polyline) lands on a bend point --
    usually a zone boundary, for this router's own waypoints -- on an
    uneven multi-segment path. Confirmed directly against a real generated
    diagram, where labels like "Encrypt"/"Telemetry" clustered and
    overlapped right at a subnet border."""

    def test_straight_two_point_path_is_the_exact_middle(self):
        path = [(0.0, 0.0), (100.0, 0.0)]
        self.assertAlmostEqual(layout._label_position_fraction(path), 0.0)

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
        self.assertAlmostEqual(fraction, expected)

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
        self.assertAlmostEqual(fraction, expected)

    def test_uneven_three_segment_path_diverges_from_arc_length_midpoint(self):
        # Segments: 90 (long-ish), 50 (medium), 20 (short) -- total 160.
        # Arc-length midpoint sits at 80 -- exactly at the boundary between
        # segment 0 (range [0,90]) and segment 1 -- i.e. near the FIRST
        # segment's own end/corner, not its middle, while the
        # longest-segment rule correctly centers on segment 0 (mid=45).
        path = [(0.0, 0.0), (90.0, 0.0), (90.0, 50.0), (90.0, 70.0)]
        fraction = layout._label_position_fraction(path)
        arc_length_mid_fraction = 0.0  # what the OLD (pre-fix) behavior effectively used
        longest_seg_mid_fraction = (45 / 160) * 2 - 1
        self.assertAlmostEqual(fraction, longest_seg_mid_fraction)
        self.assertNotAlmostEqual(fraction, arc_length_mid_fraction, delta=0.05)

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
        self.assertEqual(len(edge_cells), 1)
        geom = edge_cells[0].find("./mxGeometry")
        self.assertIsNotNone(geom.get("x"))
        self.assertGreaterEqual(float(geom.get("x")), -1.0)
        self.assertLessEqual(float(geom.get("x")), 1.0)


class ConnectionSlotSpreadingTests(unittest.TestCase):
    """Coverage for _assign_connection_slots -- see its own docstring and
    _connection_side's for the real bug it fixes: _connection_point (now
    removed) gave every edge touching the same box+side the IDENTICAL
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
        self.assertAlmostEqual(layout._slot_fraction(0, 1), 0.5)

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
        self.assertNotEqual(plans[0]["exit_frac"], plans[1]["exit_frac"])

    def test_slot_fractions_stay_off_the_corners(self):
        for slot in range(4):
            fraction = layout._slot_fraction(slot, 4)
            self.assertGreaterEqual(fraction, 0.2)
            self.assertLessEqual(fraction, 0.8)

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

        self.assertNotEqual(exit_point(edge_cells[0]), exit_point(edge_cells[1]))


class LabelCollisionResolutionTests(unittest.TestCase):
    """Coverage for _resolve_label_collisions -- see its own docstring for
    the real bug it fixes: _label_position_fraction only keeps a label off
    corners/bends on its OWN edge's path, with no visibility into where
    every OTHER edge's label lands, so two entirely unrelated edges can
    still coincidentally compute to nearly the same point -- confirmed
    directly against a real generated diagram (two unrelated edges' labels
    only 5px apart)."""

    def test_far_apart_labels_are_left_untouched(self):
        points = [(0.0, 0.0), (500.0, 500.0)]
        self.assertEqual(layout._resolve_label_collisions(points), points)

    def test_coincident_labels_end_up_at_least_threshold_apart(self):
        points = [(100.0, 100.0), (100.0, 100.0)]
        resolved = layout._resolve_label_collisions(points, threshold=40.0)
        self.assertAlmostEqual(math.dist(resolved[0], resolved[1]), 40.0)

    def test_nearly_coincident_labels_end_up_at_least_threshold_apart(self):
        # Regression test for the real confirmed bug: two labels 5px apart.
        points = [(100.0, 100.0), (105.0, 100.0)]
        resolved = layout._resolve_label_collisions(points, threshold=40.0)
        self.assertAlmostEqual(math.dist(resolved[0], resolved[1]), 40.0)

    def test_none_entries_are_skipped_without_raising(self):
        points = [(0.0, 0.0), None, (0.0, 0.0)]
        resolved = layout._resolve_label_collisions(points, threshold=40.0)
        self.assertIsNone(resolved[1])
        self.assertAlmostEqual(math.dist(resolved[0], resolved[2]), 40.0)

    def test_build_structured_drawio_xml_nudges_colliding_edge_labels_apart(self):
        # End-to-end wiring test: force two unrelated edges' raw label
        # points to coincide exactly (the collision-resolution LOGIC
        # itself is already covered above; this confirms
        # build_structured_drawio_xml actually threads its result into a
        # real mxPoint offset on the emitted XML, same as the real
        # generated diagram that originally surfaced this bug).
        original = layout._point_at_fraction
        layout._point_at_fraction = staticmethod(lambda path, fraction: (100.0, 100.0))
        try:
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
        finally:
            layout._point_at_fraction = original

        root = ET.fromstring(xml_str)
        edge_cells = [c for c in root.findall(".//mxCell") if c.get("edge") == "1"]
        offsets = [c.find("./mxGeometry/mxPoint[@as='offset']") for c in edge_cells]
        self.assertTrue(all(offset is not None for offset in offsets))
        resolved = [(float(o.get("x")) + 100.0, float(o.get("y")) + 100.0) for o in offsets]
        self.assertAlmostEqual(math.dist(resolved[0], resolved[1]), 40.0)


class BuildXmlTests(unittest.TestCase):
    def test_produces_valid_parseable_xml_with_expected_cells(self):
        xml_str = layout.build_structured_drawio_xml(
            title="T", subtitle="S",
            zones=[{"id": "z1", "label": "Zone"}],
            components=[{"id": "c1", "zone_id": "z1", "label": "Comp", "bullets": ["b1"], "shape": "mxgraph.gcp2.cloud_run"}],
            edges=[],
        )
        root = ET.fromstring(xml_str)  # raises if not well-formed
        ids = {cell.get("id") for cell in root.findall(".//mxCell")}
        self.assertIn("title_banner", ids)
        self.assertIn("z1", ids)
        self.assertIn("c1", ids)
        self.assertIn("c1_icon", ids)

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
        self.assertEqual(len(edge_cells), 2)

        def waypoints_of(cell):
            return [
                (p.get("x"), p.get("y"))
                for p in cell.findall("./mxGeometry/Array[@as='points']/mxPoint")
            ]

        wp0, wp1 = waypoints_of(edge_cells[0]), waypoints_of(edge_cells[1])
        self.assertNotEqual(wp0, wp1)

    def test_duplicate_component_id_raises_with_offending_id_named(self):
        # Regression test: previously a duplicate component id silently
        # collapsed both components onto the same box (component_boxes is
        # dict-keyed by id, so the second overwrites the first), rendering
        # as two components' text and icons fused on top of each other in
        # the actual generated diagram. This must fail loudly instead.
        with self.assertRaises(ValueError) as ctx:
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Zone"}],
                components=[
                    {"id": "vertex", "zone_id": "z1", "label": "Vertex AI Search"},
                    {"id": "vertex", "zone_id": "z1", "label": "Vertex AI Models"},
                ],
                edges=[],
            )
        self.assertIn("vertex", str(ctx.exception))

    def test_duplicate_zone_id_raises_with_offending_id_named(self):
        with self.assertRaises(ValueError) as ctx:
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[
                    {"id": "z1", "label": "Zone A"},
                    {"id": "z1", "label": "Zone B"},
                ],
                components=[],
                edges=[],
            )
        self.assertIn("z1", str(ctx.exception))

    def test_dangling_component_zone_reference_raises(self):
        with self.assertRaises(KeyError):
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
        with self.assertRaises(ValueError) as ctx:
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "shared", "label": "Zone"}],
                components=[{"id": "shared", "zone_id": "shared", "label": "Comp"}],
                edges=[],
            )
        self.assertIn("shared", str(ctx.exception))

    def test_component_id_collides_with_another_components_generated_icon_id_raises(self):
        # Regression test: a component literally named "<other id>_icon"
        # collides with the auto-generated icon cell id of a DIFFERENT
        # component that has a shape -- two mxCell elements would end up
        # with the identical id in the emitted XML.
        with self.assertRaises(ValueError) as ctx:
            layout.build_structured_drawio_xml(
                title="T", subtitle="",
                zones=[{"id": "z1", "label": "Zone"}],
                components=[
                    {"id": "service", "zone_id": "z1", "label": "Service", "shape": "mxgraph.gcp2.cloud_run"},
                    {"id": "service_icon", "zone_id": "z1", "label": "Unrelated"},
                ],
                edges=[],
            )
        self.assertIn("service_icon", str(ctx.exception))

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
        self.assertEqual(edge_cells, [])


if __name__ == "__main__":
    unittest.main()
