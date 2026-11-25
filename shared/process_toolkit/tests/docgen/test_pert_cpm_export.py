"""generate_pert_cpm_diagram's own coverage: a real backward CPM pass over
plain synthetic activity dicts (not mocked), asserting the float/critical
computation, plus a real PNG rendered to disk (same existence/size-only
assertion convention test_proposal_roadmap_diagram.py already uses for its
own sibling matplotlib diagram -- pixel-level inspection isn't this
codebase's style for generated images)."""

import datetime as dt
import os

import pytest

from process_toolkit import paths
from process_toolkit.docgen.pert_cpm_export import _compute_cpm, generate_pert_cpm_diagram


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


class TestComputeCpmDagBranchRespectsHolidays:
    """CONFIRMED AS A REAL BUG: the DAG backward pass's own working-day
    arithmetic (_working_day_diff/_subtract_working_days) ignored holidays
    entirely, unlike every other working-day function in this codebase and
    unlike the linear branch above (whose float comes from the caller's
    already holiday-aware gap_working_days_before). No existing test
    exercised the DAG branch (has_dag=True, i.e. any activity carrying a
    non-empty predecessor_uids) at all before this one."""

    def test_a_holiday_inside_the_backward_walk_changes_float_and_criticality(self):
        monday = dt.date(2026, 11, 23)  # confirmed Monday elsewhere this session
        wednesday = monday + dt.timedelta(days=2)
        thursday = monday + dt.timedelta(days=3)
        friday = monday + dt.timedelta(days=4)

        activities = [
            {"uid": 1, "name": "Y", "start": monday, "finish": wednesday, "duration_days": 2},
            {"uid": 2, "name": "Z", "start": thursday, "finish": friday, "duration_days": 1,
             "predecessor_uids": [1]},
        ]

        # Without holidays: Z's own late_start needs no slack (duration 1
        # subtracts 0 days), so Y's late_finish is exactly 1 working day
        # before Friday -- Thursday -- a full day of float relative to Y's
        # own Wednesday finish.
        scored = _compute_cpm(activities)
        y = next(a for a in scored if a["uid"] == 1)
        assert y["late_finish"] == thursday
        assert y["float_days"] == 1
        assert y["critical"] is False

        # With Thursday marked as a holiday, "1 working day before Friday"
        # skips it and lands on Wednesday instead -- exactly Y's own
        # forward finish, so float collapses to 0 and Y becomes critical.
        scored_holiday = _compute_cpm(activities, holidays=frozenset({thursday}))
        y2 = next(a for a in scored_holiday if a["uid"] == 1)
        assert y2["late_finish"] == wednesday
        assert y2["float_days"] == 0
        assert y2["critical"] is True

    def test_generate_pert_cpm_diagram_threads_holidays_into_the_dag_branch(self):
        # Same scenario as above, through the real public entry point --
        # proves holidays actually reaches _compute_cpm rather than being
        # silently dropped at the generate_pert_cpm_diagram boundary.
        monday = dt.date(2026, 11, 23)
        wednesday = monday + dt.timedelta(days=2)
        thursday = monday + dt.timedelta(days=3)
        friday = monday + dt.timedelta(days=4)
        activities = [
            {"uid": 1, "name": "Y", "start": monday, "finish": wednesday, "duration_days": 2},
            {"uid": 2, "name": "Z", "start": thursday, "finish": friday, "duration_days": 1,
             "predecessor_uids": [1]},
        ]
        out_path = generate_pert_cpm_diagram(
            activities, "Holiday DAG Plan", "holiday_dag.png", holidays=frozenset({thursday}),
        )
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0


class TestGeneratePertCpmDiagram:
    def test_raises_when_no_activities(self):
        with pytest.raises(ValueError):
            generate_pert_cpm_diagram([], "Empty Plan", "empty.png")

    def test_generates_a_real_png_at_the_expected_path(self):
        activities = [
            _activity(1, "Story One", dt.date(2026, 1, 1), dt.date(2026, 1, 2), 2),
            _activity(2, "Story Two", dt.date(2026, 1, 5), dt.date(2026, 1, 6), 2),
            _activity(3, "Story Three", dt.date(2026, 1, 7), dt.date(2026, 1, 9), 3),
        ]
        out_path = generate_pert_cpm_diagram(activities, "Test Plan", "test_pert_cpm.png")
        assert out_path == paths.output_path("test_pert_cpm.png")
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0

    def test_handles_a_single_activity(self):
        activities = [_activity(1, "Only Task", dt.date(2026, 1, 1), dt.date(2026, 1, 1), 1)]
        out_path = generate_pert_cpm_diagram(activities, "Solo Plan", "solo.png")
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0

    def test_handles_mixed_criticality_without_crashing(self):
        activities = [
            _activity(1, "A", dt.date(2026, 1, 1), dt.date(2026, 1, 2), 2),
            _activity(2, "B", dt.date(2026, 1, 8), dt.date(2026, 1, 9), 2, gap=3),
        ]
        out_path = generate_pert_cpm_diagram(activities, "Mixed Plan", "mixed.png")
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0

    def test_generates_multi_row_png_for_large_activity_set(self):
        activities = [
            _activity(i, f"Task {i}", dt.date(2026, 1, 1) + dt.timedelta(days=i), dt.date(2026, 1, 2) + dt.timedelta(days=i), 1)
            for i in range(1, 16)
        ]
        out_path = generate_pert_cpm_diagram(activities, "Multi-Row Plan", "multi_row.png")
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0
