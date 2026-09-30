import unittest
import xml.etree.ElementTree as ET

# Pure Python, no ADK/google dependencies -- no stub installer needed.
from process_agents.cloudarch import cloudarch_layout_agent as layout


def _boxes_overlap(a, b):
    return not (a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y)


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
        # plus 4 bullets (5 lines total) with spacingTop=58 needs height >= 158.
        component = {"label": "X", "bullets": ["a", "b", "c", "d"], "shape": "mxgraph.gcp2.cloud_run"}
        self.assertEqual(layout._component_height(component), 158)


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
        waypoints = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 0, row_bottoms
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
        waypoints = layout._route_edge(
            {"source": "top", "target": "far"}, comp_boxes["top"], comp_boxes["far"], 0, row_bottoms
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
        waypoints = layout._route_edge(
            {"source": "bottom", "target": "far"}, comp_boxes["bottom"], comp_boxes["far"], 0, row_bottoms
        )
        self.assertEqual(waypoints, [])

    def test_same_row_edge_routes_through_the_zone_gap(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        waypoints = layout._route_edge(
            {"source": "top", "target": "other"}, comp_boxes["top"], comp_boxes["other"], 0, row_bottoms
        )
        self.assertEqual(len(waypoints), 1)
        wx, _wy = waypoints[0]
        # Must sit strictly between the two zone columns, in the reserved gap.
        self.assertGreater(wx, zone_boxes["z1"].right)
        self.assertLess(wx, zone_boxes["z2"].x)

    def test_cross_row_edge_uses_tallest_zone_in_the_row_not_the_component(self):
        # Regression test: this previously used the SOURCE COMPONENT's own
        # bottom (near the top of its column) instead of the bottom of the
        # tallest zone in that row, routing straight through sibling
        # components below it. "top" is near the TOP of z1, far above
        # z1's actual bottom edge.
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        waypoints = layout._route_edge(
            {"source": "top", "target": "gov_item"}, comp_boxes["top"], comp_boxes["gov_item"], 0, row_bottoms
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
        first = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 0, row_bottoms
        )
        second = layout._route_edge(
            {"source": "top", "target": "bottom"}, comp_boxes["top"], comp_boxes["bottom"], 1, row_bottoms
        )
        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertNotEqual(second[0], first)

    def test_channel_key_groups_edges_that_would_otherwise_collide(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        # Same pair, both directions -> same channel.
        self.assertEqual(
            layout._channel_key(comp_boxes["top"], comp_boxes["bottom"]),
            layout._channel_key(comp_boxes["bottom"], comp_boxes["top"]),
        )
        # Same zone-pair gap, different component pairs -> same channel.
        self.assertEqual(
            layout._channel_key(comp_boxes["top"], comp_boxes["other"]),
            layout._channel_key(comp_boxes["bottom"], comp_boxes["other"]),
        )
        # A same-zone pair must not collide with an inter-zone channel key.
        self.assertNotEqual(
            layout._channel_key(comp_boxes["top"], comp_boxes["bottom"]),
            layout._channel_key(comp_boxes["top"], comp_boxes["other"]),
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
        edge_a = layout._route_edge(
            {"source": "top", "target": "other"}, comp_boxes["top"], comp_boxes["other"], 0, row_bottoms
        )
        edge_b = layout._route_edge(
            {"source": "bottom", "target": "other"}, comp_boxes["bottom"], comp_boxes["other"], 1, row_bottoms
        )
        self.assertNotEqual(edge_a[0][1], edge_b[0][1])

    def test_cross_row_waypoints_never_land_inside_an_unrelated_component(self):
        zones, components = self._sample()
        zone_boxes, comp_boxes, _, _ = layout._layout_zones_and_components(zones, components)
        row_bottoms = self._row_bottoms(zone_boxes)
        waypoints = layout._route_edge(
            {"source": "top", "target": "gov_item"}, comp_boxes["top"], comp_boxes["gov_item"], 0, row_bottoms
        )
        for wx, wy in waypoints:
            for cid, box in comp_boxes.items():
                if cid in ("top", "gov_item"):
                    continue
                self.assertFalse(
                    box.x < wx < box.right and box.y < wy < box.bottom,
                    f"waypoint ({wx},{wy}) lands inside unrelated component {cid}",
                )


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
