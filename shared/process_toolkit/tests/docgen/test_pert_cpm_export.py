"""build_pert_cpm_drawio_xml's own coverage: a real backward CPM pass over
plain synthetic activity dicts (not mocked), asserting the mxGraph XML
shape, the float/critical computation, and the legend text's two variants."""

import datetime as dt
import xml.etree.ElementTree as ET

from process_toolkit.docgen.pert_cpm_export import _compute_cpm, build_pert_cpm_drawio_xml


def _activity(uid, name, start, finish, duration_days, gap=0):
    return {
        "uid": uid, "name": name, "start": start, "finish": finish,
        "duration_days": duration_days, "gap_working_days_before": gap,
    }


class TestComputeCpmLinearChain:
    """Today's real scheduler (docgen.project_plan_export._schedule_subtree)
    always produces a back-to-back chain with zero gaps -- this is the
    common case the backward pass must get right."""

    def test_every_activity_is_critical_with_zero_float(self):
        activities = [
            _activity(1, "A", dt.date(2026, 1, 1), dt.date(2026, 1, 2), 2),
            _activity(2, "B", dt.date(2026, 1, 5), dt.date(2026, 1, 6), 2, gap=0),
            _activity(3, "C", dt.date(2026, 1, 7), dt.date(2026, 1, 9), 3, gap=0),
        ]
        scored = _compute_cpm(activities)
        for a in scored:
            assert a["critical"] is True
            assert a["float_days"] == 0
        # The terminal activity's own late_finish anchors at its early
        # finish -- nothing follows it to create slack against.
        assert scored[-1]["late_finish"] == scored[-1]["finish"]
        # Back-to-back propagation: an earlier activity's late_finish
        # equals its own early finish too, since the gap before its
        # successor is zero.
        assert scored[0]["late_finish"] == scored[0]["finish"]
        assert scored[0]["late_start"] == scored[0]["start"]

    def test_empty_activity_list_returns_empty(self):
        assert _compute_cpm([]) == []

    def test_single_activity_is_critical_by_definition(self):
        scored = _compute_cpm([_activity(1, "Solo", dt.date(2026, 1, 1), dt.date(2026, 1, 1), 1)])
        assert scored[0]["critical"] is True
        assert scored[0]["float_days"] == 0


class TestComputeCpmWithRealSlack:
    """A synthetic case with a deliberate gap -- production code never
    currently produces this (today's scheduler packs everything
    back-to-back), but this proves the backward pass is a genuine
    computation, not a hardcoded "everything is critical" shortcut."""

    def test_an_activity_before_a_gap_has_real_float_and_is_not_critical(self):
        activities = [
            _activity(1, "A", dt.date(2026, 1, 1), dt.date(2026, 1, 2), 2),
            # B starts 3 working days after A finishes -- real slack.
            _activity(2, "B", dt.date(2026, 1, 8), dt.date(2026, 1, 9), 2, gap=3),
        ]
        scored = _compute_cpm(activities)
        assert scored[0]["critical"] is False
        assert scored[0]["float_days"] == 3
        assert scored[0]["late_finish"] == scored[0]["finish"] + dt.timedelta(days=3)
        assert scored[0]["late_start"] == scored[0]["start"] + dt.timedelta(days=3)
        # The terminal activity is always critical by definition, gap or not.
        assert scored[1]["critical"] is True
        assert scored[1]["float_days"] == 0

    def test_a_longer_chain_propagates_slack_backward_through_a_back_to_back_run(self):
        # A -> B (back-to-back) -> C (3-day gap before C) -> D (back-to-back
        # terminal). A's own float must inherit the SAME 3-day slack as B's,
        # since neither A nor B can be delayed past the point that would
        # start pushing C later than its own scheduled start.
        activities = [
            _activity(1, "A", dt.date(2026, 1, 1), dt.date(2026, 1, 2), 2, gap=0),
            _activity(2, "B", dt.date(2026, 1, 3), dt.date(2026, 1, 5), 3, gap=0),
            _activity(3, "C", dt.date(2026, 1, 9), dt.date(2026, 1, 9), 1, gap=3),
            _activity(4, "D", dt.date(2026, 1, 10), dt.date(2026, 1, 10), 1, gap=0),
        ]
        scored = _compute_cpm(activities)
        assert [a["float_days"] for a in scored] == [3, 3, 0, 0]
        assert [a["critical"] for a in scored] == [False, False, True, True]


class TestBuildPertCpmDrawioXml:
    def test_linear_chain_produces_boxes_and_edges(self):
        activities = [
            _activity(1, "Story One", dt.date(2026, 1, 1), dt.date(2026, 1, 2), 2),
            _activity(2, "Story Two", dt.date(2026, 1, 5), dt.date(2026, 1, 6), 2),
            _activity(3, "Story Three", dt.date(2026, 1, 7), dt.date(2026, 1, 9), 3),
        ]
        xml_text = build_pert_cpm_drawio_xml(activities, "Test Plan")
        root = ET.fromstring(xml_text)
        cells = root.findall(".//mxCell")

        vertex_cells = [c for c in cells if c.get("vertex") == "1"]
        edge_cells = [c for c in cells if c.get("edge") == "1"]
        # 3 activity boxes + 1 header/legend banner.
        assert len(vertex_cells) == 4
        assert len(edge_cells) == 2

        activity_ids = {f"activity_{a['uid']}" for a in activities}
        assert activity_ids.issubset({c.get("id") for c in vertex_cells})

        for edge in edge_cells:
            assert edge.get("source") in activity_ids
            assert edge.get("target") in activity_ids

    def test_all_critical_shows_the_no_parallel_streams_legend(self):
        activities = [_activity(1, "Only Task", dt.date(2026, 1, 1), dt.date(2026, 1, 1), 1)]
        xml_text = build_pert_cpm_drawio_xml(activities, "Solo Plan")
        assert "no parallel work" in xml_text
        assert "Activities outlined in red are on" not in xml_text

    def test_mixed_criticality_shows_the_generic_legend(self):
        activities = [
            _activity(1, "A", dt.date(2026, 1, 1), dt.date(2026, 1, 2), 2),
            _activity(2, "B", dt.date(2026, 1, 8), dt.date(2026, 1, 9), 2, gap=3),
        ]
        xml_text = build_pert_cpm_drawio_xml(activities, "Mixed Plan")
        assert "Activities outlined in red are on" in xml_text
        assert "no parallel work" not in xml_text
        assert "HAS SLACK" in xml_text
        assert "CRITICAL" in xml_text

    def test_empty_activity_list_produces_a_valid_no_crash_diagram(self):
        xml_text = build_pert_cpm_drawio_xml([], "Empty Plan")
        root = ET.fromstring(xml_text)
        vertex_cells = [c for c in root.findall(".//mxCell") if c.get("vertex") == "1"]
        assert len(vertex_cells) == 1  # just the header/legend banner
        assert "No activities to schedule" in xml_text

    def test_name_with_special_characters_still_parses_as_valid_xml(self):
        # `value` is written as a plain Python string containing real "<b>"/
        # "<br/>" markup, same as cloudarch/layout.py's own title_value/
        # zone-label construction -- ET.tostring's own attribute
        # serialization is what escapes it (exactly once) when the file is
        # written, same as it escapes the task's own name. No manual
        # escaping belongs in this module (confirmed directly: adding one
        # here previously double-escaped everything, e.g. "&amp;" became
        # "&amp;amp;", corrupting the markup).
        activities = [_activity(1, "A & <B>", dt.date(2026, 1, 1), dt.date(2026, 1, 1), 1)]
        xml_text = build_pert_cpm_drawio_xml(activities, "Plan")
        root = ET.fromstring(xml_text)  # raises if this isn't well-formed
        activity_cell = root.find(".//mxCell[@id='activity_1']")
        assert "A & <B>" in activity_cell.get("value")
        assert "<b>" in activity_cell.get("value")
