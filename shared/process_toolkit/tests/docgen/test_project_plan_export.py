"""project_plan_export.py's own end-to-end coverage: real MSPDI XML is
rendered and parsed back (not mocked), asserting task hierarchy, scheduling,
and the illustrative-estimate disclosure text."""

import xml.etree.ElementTree as ET

from process_toolkit import paths
from process_toolkit.docgen.project_plan_export import (
    PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME,
    PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME,
    _parse_timing_to_days,
    build_portfolio_backlog_project_plan,
    build_proposal_response_project_plan,
    portfolio_backlog_project_plan_exists,
    proposal_response_project_plan_exists,
)
from process_toolkit.portfolio_backlog.portfolio_backlog import save_portfolio_backlog
from process_toolkit.proposal_response.proposal_response import save_proposal_response

_NS = {"p": "http://schemas.microsoft.com/project"}


def _sample_backlog():
    return {
        "name": "Test Backlog",
        "summary": "s", "source_artifact": "design", "source_name": "x",
        "epics": [
            {
                "id": "EPIC-001", "title": "Epic One", "description": "d", "strategic_theme": "t",
                "traces_to": ["FR-1"],
                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-001", "title": "Feature One", "description": "d",
                        "strategic_theme": "t", "traces_to": ["FR-1"],
                        "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-001", "title": "Story One", "description": "d",
                                "strategic_theme": "t", "traces_to": ["FR-1"],
                                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                                "job_size": 3, "acceptance_criteria": ["works"],
                            },
                            {
                                "id": "STORY-002", "title": "Story Two", "description": "d",
                                "strategic_theme": "t", "traces_to": ["FR-1"],
                                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                                "job_size": 5, "acceptance_criteria": ["works"],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _parse(path):
    return ET.parse(path).getroot()


def _tasks_by_name(root):
    return {t.find("p:Name", _NS).text: t for t in root.findall(".//p:Task", _NS)}


class TestPortfolioBacklogProjectPlan:
    def test_errors_when_nothing_saved(self):
        assert build_portfolio_backlog_project_plan() == (
            "ERROR: No saved portfolio backlog found. Create one first."
        )
        assert not portfolio_backlog_project_plan_exists()

    def test_builds_a_real_mspdi_file_with_epic_feature_story_hierarchy(self):
        save_portfolio_backlog(_sample_backlog())
        result = build_portfolio_backlog_project_plan()

        assert "successfully exported" in result
        assert portfolio_backlog_project_plan_exists()

        root = _parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)
        assert set(tasks) == {"Test Backlog", "Epic One", "Feature One", "Story One", "Story Two"}

        outline_levels = {name: t.find("p:OutlineLevel", _NS).text for name, t in tasks.items()}
        assert outline_levels["Test Backlog"] == "1"
        assert outline_levels["Epic One"] == "2"
        assert outline_levels["Feature One"] == "3"
        assert outline_levels["Story One"] == "4"

        summary_flags = {name: t.find("p:Summary", _NS).text for name, t in tasks.items()}
        assert summary_flags["Test Backlog"] == "1"
        assert summary_flags["Epic One"] == "1"
        assert summary_flags["Feature One"] == "1"
        assert summary_flags["Story One"] == "0"

    def test_story_duration_derives_from_job_size_at_one_day_per_point(self):
        save_portfolio_backlog(_sample_backlog())
        build_portfolio_backlog_project_plan()
        root = _parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)

        # job_size=3 -> 3 working days -> 24 working hours.
        assert tasks["Story One"].find("p:Duration", _NS).text == "PT24H0M0S"
        # job_size=5 -> 5 working days -> 40 working hours.
        assert tasks["Story Two"].find("p:Duration", _NS).text == "PT40H0M0S"

    def test_stories_are_sequenced_finish_to_start_not_in_parallel(self):
        save_portfolio_backlog(_sample_backlog())
        build_portfolio_backlog_project_plan()
        root = _parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)

        story_one_uid = tasks["Story One"].find("p:UID", _NS).text
        story_two_pred = tasks["Story Two"].find("p:PredecessorLink/p:PredecessorUID", _NS)
        assert story_two_pred is not None
        assert story_two_pred.text == story_one_uid

        story_one_finish = tasks["Story One"].find("p:Finish", _NS).text
        story_two_start = tasks["Story Two"].find("p:Start", _NS).text
        assert story_two_start > story_one_finish

    def test_root_task_carries_the_illustrative_disclosure(self):
        save_portfolio_backlog(_sample_backlog())
        build_portfolio_backlog_project_plan()
        root = _parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)

        notes = tasks["Test Backlog"].find("p:Notes", _NS).text
        assert "Illustrative delivery schedule" in notes
        assert "not a committed schedule" in notes

    def test_dates_fall_on_working_days_never_weekends(self):
        save_portfolio_backlog(_sample_backlog())
        build_portfolio_backlog_project_plan()
        root = _parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME))
        import datetime

        for task in root.findall(".//p:Task", _NS):
            for field in ("Start", "Finish"):
                el = task.find(f"p:{field}", _NS)
                if el is not None:
                    day = datetime.datetime.strptime(el.text, "%Y-%m-%dT%H:%M:%S").date()
                    assert day.weekday() < 5, f"{field}={el.text} falls on a weekend"


class TestProposalResponseProjectPlan:
    def _sample_response(self):
        return {
            "name": "Harborlight Response",
            "implementation_plan": [
                {"phase": "Discovery", "timing": "Weeks 1-4", "deliverable": "Discovery report", "acceptance_criteria": "Signed off"},
                {"phase": "Build", "timing": "roughly a quarter", "deliverable": "Built system", "acceptance_criteria": "UAT passed"},
                {"phase": "Launch", "timing": "10 days", "deliverable": "Go-live", "acceptance_criteria": "Live in prod"},
            ],
        }

    def test_errors_when_nothing_saved(self):
        assert build_proposal_response_project_plan() == (
            "ERROR: No saved proposal response found. Create one first."
        )
        assert not proposal_response_project_plan_exists()

    def test_builds_one_task_per_phase_in_order(self):
        save_proposal_response(self._sample_response())
        result = build_proposal_response_project_plan()

        assert "successfully exported" in result
        root = _parse(paths.output_path(PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)
        assert set(tasks) == {"Harborlight Response", "Discovery", "Build", "Launch"}

    def test_unparseable_timing_falls_back_but_preserves_original_text_verbatim(self):
        # CONFIRMED AS A REAL REQUIREMENT, not just a nice-to-have: an
        # unparseable timing string must still be visible verbatim in the
        # task's own Notes, even though its duration falls back to the
        # nominal default -- nothing silently dropped or misrepresented.
        save_proposal_response(self._sample_response())
        build_proposal_response_project_plan()
        root = _parse(paths.output_path(PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)

        build_notes = tasks["Build"].find("p:Notes", _NS).text
        assert "roughly a quarter" in build_notes
        # 10 working days (the nominal fallback) = 80 working hours.
        assert tasks["Build"].find("p:Duration", _NS).text == "PT80H0M0S"

    def test_week_range_timing_parses_to_matching_duration(self):
        save_proposal_response(self._sample_response())
        build_proposal_response_project_plan()
        root = _parse(paths.output_path(PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)

        # "Weeks 1-4" -> 4 weeks * 5 working days = 20 days = 160 hours.
        assert tasks["Discovery"].find("p:Duration", _NS).text == "PT160H0M0S"

    def test_deliverable_and_acceptance_criteria_preserved_in_notes(self):
        save_proposal_response(self._sample_response())
        build_proposal_response_project_plan()
        root = _parse(paths.output_path(PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME))
        tasks = _tasks_by_name(root)

        launch_notes = tasks["Launch"].find("p:Notes", _NS).text
        assert "Go-live" in launch_notes
        assert "Live in prod" in launch_notes


class TestParseTimingToDays:
    def test_week_range(self):
        assert _parse_timing_to_days("Weeks 1-4") == 20

    def test_single_week(self):
        assert _parse_timing_to_days("Week 2") == 5

    def test_n_weeks(self):
        assert _parse_timing_to_days("3 weeks") == 15

    def test_n_months(self):
        assert _parse_timing_to_days("2 months") == 40

    def test_n_days(self):
        assert _parse_timing_to_days("10 days") == 10

    def test_unparseable_falls_back_to_default(self):
        assert _parse_timing_to_days("sometime next quarter") == 10

    def test_empty_or_non_string_falls_back_to_default(self):
        assert _parse_timing_to_days("") == 10
        assert _parse_timing_to_days(None) == 10
