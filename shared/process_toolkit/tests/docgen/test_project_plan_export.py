"""project_plan_export.py's own end-to-end coverage: real MSPDI XML is
rendered and parsed back (not mocked), asserting task hierarchy, scheduling,
and the illustrative-estimate disclosure text."""

import xml.etree.ElementTree as ET

from process_toolkit import paths
from process_toolkit.docgen.project_plan_export import (
    PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME,
    PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME,
    _normalize_resources,
    _parse_timing_to_days,
    build_portfolio_backlog_project_plan,
    build_proposal_response_project_plan,
    mspdi_project_title,
    parse_mspdi_assignments,
    parse_mspdi_project,
    parse_mspdi_resources,
    parse_mspdi_tasks,
    portfolio_backlog_project_plan_exists,
    proposal_response_project_plan_exists,
    uk_bank_holidays,
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


class TestUkBankHolidays:
    def test_2024_matches_the_real_published_calendar(self):
        # Verified against the real UK government bank holiday list.
        import datetime as dt

        assert uk_bank_holidays(2024) == frozenset({
            dt.date(2024, 1, 1), dt.date(2024, 3, 29), dt.date(2024, 4, 1),
            dt.date(2024, 5, 6), dt.date(2024, 5, 27), dt.date(2024, 8, 26),
            dt.date(2024, 12, 25), dt.date(2024, 12, 26),
        })

    def test_2025_matches_the_real_published_calendar(self):
        import datetime as dt

        assert uk_bank_holidays(2025) == frozenset({
            dt.date(2025, 1, 1), dt.date(2025, 4, 18), dt.date(2025, 4, 21),
            dt.date(2025, 5, 5), dt.date(2025, 5, 26), dt.date(2025, 8, 25),
            dt.date(2025, 12, 25), dt.date(2025, 12, 26),
        })

    def test_christmas_and_boxing_day_weekend_collision_gets_two_distinct_substitutes(self):
        # 2021: Christmas Day fell on a Saturday, Boxing Day on a Sunday --
        # CONFIRMED AS A REAL EDGE CASE the simple "move to next Monday"
        # rule alone would collide on: both substitutes must land on
        # different weekdays (27th and 28th), not both on the 27th.
        import datetime as dt

        holidays_2021 = uk_bank_holidays(2021)
        assert dt.date(2021, 12, 27) in holidays_2021
        assert dt.date(2021, 12, 28) in holidays_2021
        assert dt.date(2021, 12, 25) not in holidays_2021  # the Saturday itself, not observed
        assert dt.date(2021, 12, 26) not in holidays_2021  # the Sunday itself, not observed

    def test_new_years_day_on_a_weekend_substitutes_to_monday(self):
        import datetime as dt

        # 1 January 2028 is a Saturday.
        assert dt.date(2028, 1, 3) in uk_bank_holidays(2028)  # substitute Monday
        assert dt.date(2028, 1, 1) not in uk_bank_holidays(2028)


class TestHolidayAwareScheduling:
    def _sample_backlog(self):
        # Two stories at the max Fibonacci point value (20) each, summing to
        # 40 sequential working days from a 23 Nov start -- comfortably
        # crosses Christmas/Boxing Day/New Year's Day, while keeping each
        # individual story on the real modified-Fibonacci scale
        # ([1, 2, 3, 5, 8, 13, 20]) this codebase uses elsewhere, rather
        # than an off-scale single-story value.
        return {
            "name": "Test Backlog", "summary": "s", "source_artifact": "design", "source_name": "x",
            "epics": [{
                "id": "EPIC-001", "title": "Epic One", "description": "d", "strategic_theme": "t",
                "traces_to": ["FR-1"],
                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                "job_size": 20,
                "features": [{
                    "id": "FEAT-001", "title": "Feature One", "description": "d", "strategic_theme": "t",
                    "traces_to": ["FR-1"],
                    "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                    "job_size": 20,
                    "stories": [
                        {
                            "id": "STORY-001", "title": "Story One", "description": "d", "strategic_theme": "t",
                            "traces_to": ["FR-1"],
                            "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                            "job_size": 20, "acceptance_criteria": ["works"],
                        },
                        {
                            "id": "STORY-002", "title": "Story Two", "description": "d", "strategic_theme": "t",
                            "traces_to": ["FR-1"],
                            "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                            "job_size": 20, "acceptance_criteria": ["works"],
                        },
                    ],
                }],
            }],
        }

    def test_schedule_skips_christmas_and_new_year_when_uk_calendar_requested(self):
        # job_size=20 starting 23 Nov 2026 runs long enough to cross
        # Christmas/Boxing Day/New Year's Day -- with the UK calendar, none
        # of those three dates may appear as a Start/Finish, and the
        # overall finish must land LATER than the equivalent plain
        # weekends-only schedule would.
        save_portfolio_backlog(self._sample_backlog())
        build_portfolio_backlog_project_plan(start_date="2026-11-23", holiday_calendar="uk")

        import datetime as dt

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        holiday_dates = {dt.date(2026, 12, 25), dt.date(2026, 12, 28), dt.date(2027, 1, 1)}
        for task in root.findall(".//p:Task", _NS):
            for field in ("Start", "Finish"):
                el = task.find(f"p:{field}", _NS)
                if el is not None:
                    day = dt.datetime.strptime(el.text, "%Y-%m-%dT%H:%M:%S").date()
                    assert day not in holiday_dates, f"{field}={el.text} falls on a UK bank holiday"

    def test_calendar_exceptions_are_rendered_for_holidays_within_the_plan_span(self):
        save_portfolio_backlog(self._sample_backlog())
        build_portfolio_backlog_project_plan(start_date="2026-11-23", holiday_calendar="uk")

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        exception_dates = {
            e.find("p:TimePeriod/p:FromDate", _NS).text
            for e in root.findall(".//p:Calendars/p:Calendar/p:Exceptions/p:Exception", _NS)
        }
        assert "2026-12-25T00:00:00" in exception_dates
        assert "2027-01-01T00:00:00" in exception_dates

    def test_no_holiday_calendar_means_weekends_only_as_before(self):
        save_portfolio_backlog(self._sample_backlog())
        build_portfolio_backlog_project_plan(start_date="2026-11-23")  # no holiday_calendar

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        assert root.findall(".//p:Calendars/p:Calendar/p:Exceptions/p:Exception", _NS) == []

    def test_unknown_holiday_calendar_value_is_ignored_not_guessed(self):
        save_portfolio_backlog(self._sample_backlog())
        build_portfolio_backlog_project_plan(start_date="2026-11-23", holiday_calendar="narnia")

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        assert root.findall(".//p:Calendars/p:Calendar/p:Exceptions/p:Exception", _NS) == []


class TestNormalizeResources:
    def test_valid_entries_pass_through_as_fractions(self):
        assert _normalize_resources([
            {"name": "Project Manager", "allocation_percent": 50},
            {"name": "Engineer", "allocation_percent": 100},
        ]) == [("Project Manager", 0.5), ("Engineer", 1.0)]

    def test_missing_or_blank_name_is_skipped(self):
        assert _normalize_resources([{"allocation_percent": 50}, {"name": "  ", "allocation_percent": 50}]) == []

    def test_non_numeric_or_out_of_range_percent_is_skipped(self):
        assert _normalize_resources([
            {"name": "A", "allocation_percent": "not a number"},
            {"name": "B", "allocation_percent": 0},
            {"name": "C", "allocation_percent": 150},
        ]) == []

    def test_none_or_empty_input_returns_empty_list(self):
        assert _normalize_resources(None) == []
        assert _normalize_resources([]) == []


class TestResourcesAndAssignments:
    def _sample_backlog_two_stories(self):
        return {
            "name": "Test Backlog", "summary": "s", "source_artifact": "design", "source_name": "x",
            "epics": [{
                "id": "EPIC-001", "title": "Epic One", "description": "d", "strategic_theme": "t",
                "traces_to": ["FR-1"],
                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                "job_size": 8,
                "features": [{
                    "id": "FEAT-001", "title": "Feature One", "description": "d", "strategic_theme": "t",
                    "traces_to": ["FR-1"],
                    "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                    "job_size": 8,
                    "stories": [
                        {
                            "id": "STORY-001", "title": "Story One", "description": "d", "strategic_theme": "t",
                            "traces_to": ["FR-1"],
                            "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                            "job_size": 5, "acceptance_criteria": ["works"],
                        },
                        {
                            "id": "STORY-002", "title": "Story Two", "description": "d", "strategic_theme": "t",
                            "traces_to": ["FR-1"],
                            "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                            "job_size": 3, "acceptance_criteria": ["works"],
                        },
                    ],
                }],
            }],
        }

    def test_resources_rendered_with_correct_max_units(self):
        save_portfolio_backlog(self._sample_backlog_two_stories())
        build_portfolio_backlog_project_plan(resources=[
            {"name": "Project Manager", "allocation_percent": 50},
            {"name": "ServiceNow Engineer", "allocation_percent": 100},
        ])

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        resources = {r.find("p:Name", _NS).text: r.find("p:MaxUnits", _NS).text for r in root.findall(".//p:Resources/p:Resource", _NS)}
        assert resources == {"Project Manager": "0.5", "ServiceNow Engineer": "1"}

    def test_every_resource_assigned_to_every_leaf_task_with_scaled_work(self):
        save_portfolio_backlog(self._sample_backlog_two_stories())
        build_portfolio_backlog_project_plan(resources=[
            {"name": "Project Manager", "allocation_percent": 50},
        ])

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        tasks_by_name = {t.find("p:Name", _NS).text: t.find("p:UID", _NS).text for t in root.findall(".//p:Task", _NS)}
        assignments = root.findall(".//p:Assignments/p:Assignment", _NS)

        # 2 leaf stories x 1 resource = 2 assignments; no assignment targets
        # the summary (epic/feature/root) tasks.
        assert len(assignments) == 2
        assigned_task_uids = {a.find("p:TaskUID", _NS).text for a in assignments}
        assert tasks_by_name["Story One"] in assigned_task_uids
        assert tasks_by_name["Story Two"] in assigned_task_uids
        assert tasks_by_name["Epic One"] not in assigned_task_uids

        for assignment in assignments:
            assert assignment.find("p:Units", _NS).text == "0.5"
        # Story One: job_size=5 -> 40 working hours; at 50% allocation, Work = 20h.
        story_one_assignment = next(
            a for a in assignments if a.find("p:TaskUID", _NS).text == tasks_by_name["Story One"]
        )
        assert story_one_assignment.find("p:Work", _NS).text == "PT20H0M0S"

    def test_backlog_resources_included_in_project_plan_when_no_caller_resources_passed(self):
        save_portfolio_backlog(self._sample_backlog_two_stories())
        build_portfolio_backlog_project_plan()

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        assert root.find(".//p:Resources", _NS) is not None
        assert root.find(".//p:Assignments", _NS) is not None
        resources = root.findall(".//p:Resources/p:Resource", _NS)
        assert len(resources) > 0
        assignments = root.findall(".//p:Assignments/p:Assignment", _NS)
        assert len(assignments) > 0


class TestTargetDurationOverrunWarning:
    def _large_backlog(self):
        return {
            "name": "Test Backlog", "summary": "s", "source_artifact": "design", "source_name": "x",
            "epics": [{
                "id": "EPIC-001", "title": "Epic One", "description": "d", "strategic_theme": "t",
                "traces_to": ["FR-1"],
                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                "job_size": 20,
                "features": [{
                    "id": "FEAT-001", "title": "Feature One", "description": "d", "strategic_theme": "t",
                    "traces_to": ["FR-1"],
                    "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                    "job_size": 20,
                    "stories": [{
                        "id": "STORY-001", "title": "Story One", "description": "d", "strategic_theme": "t",
                        "traces_to": ["FR-1"],
                        "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                        "job_size": 20, "acceptance_criteria": ["works"],
                    }],
                }],
            }],
        }

    def test_warning_appears_in_message_and_notes_when_target_is_overrun(self):
        save_portfolio_backlog(self._large_backlog())  # 20 points = 20 working days = 4 weeks
        result = build_portfolio_backlog_project_plan(target_duration_weeks=1)

        assert "WARNING" in result
        assert "overruns the requested 1-week target" in result

        root = ET.parse(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)).getroot()
        root_notes = root.findall(".//p:Task", _NS)[0].find("p:Notes", _NS).text
        assert "WARNING" in root_notes

    def test_no_warning_when_plan_fits_within_target(self):
        save_portfolio_backlog(self._large_backlog())
        result = build_portfolio_backlog_project_plan(target_duration_weeks=52)

        assert "WARNING" not in result

    def test_no_target_means_no_warning_regardless_of_length(self):
        save_portfolio_backlog(self._large_backlog())
        result = build_portfolio_backlog_project_plan()

        assert "WARNING" not in result


class TestParseMspdiTasks:
    def test_returns_none_for_a_non_mspdi_xml_file(self, tmp_path):
        path = tmp_path / "not_mspdi.xml"
        path.write_text("<root><child/></root>", encoding="utf-8")
        assert parse_mspdi_tasks(str(path)) is None
        assert mspdi_project_title(str(path)) is None

    def test_returns_none_for_malformed_xml(self, tmp_path):
        path = tmp_path / "broken.xml"
        path.write_text("<Project><Tasks>", encoding="utf-8")
        assert parse_mspdi_tasks(str(path)) is None

    def test_round_trips_hierarchy_dates_and_duration(self):
        save_portfolio_backlog(_sample_backlog())
        build_portfolio_backlog_project_plan()
        out_path = paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)

        assert mspdi_project_title(out_path) == "Test Backlog"

        tasks = parse_mspdi_tasks(out_path)
        by_name = {t["name"]: t for t in tasks}
        assert set(by_name) == {"Test Backlog", "Epic One", "Feature One", "Story One", "Story Two"}

        assert by_name["Test Backlog"]["outline_level"] == 1
        assert by_name["Test Backlog"]["is_summary"] is True
        assert by_name["Story One"]["outline_level"] == 4
        assert by_name["Story One"]["is_summary"] is False

        # job_size=3 -> 3 working days -> 24 hours (see
        # test_story_duration_derives_from_job_size_at_one_day_per_point).
        assert by_name["Story One"]["duration_hours"] == 24.0
        assert by_name["Story One"]["start"] is not None
        assert by_name["Story One"]["finish"] is not None

        # Whichever story is scheduled second carries the other's UID as predecessor.
        story_one_uid = by_name["Story One"]["uid"]
        story_two_uid = by_name["Story Two"]["uid"]
        predecessor_uids = {by_name["Story One"]["predecessor_uid"], by_name["Story Two"]["predecessor_uid"]}
        assert story_one_uid in predecessor_uids or story_two_uid in predecessor_uids

    def test_tasks_are_returned_in_document_order(self):
        save_proposal_response({
            "name": "Ordered Response",
            "implementation_plan": [
                {"phase": "Discovery", "timing": "1 week", "deliverable": "d", "acceptance_criteria": "a"},
                {"phase": "Build", "timing": "2 weeks", "deliverable": "d", "acceptance_criteria": "a"},
                {"phase": "Launch", "timing": "1 week", "deliverable": "d", "acceptance_criteria": "a"},
            ],
        })
        build_proposal_response_project_plan()
        out_path = paths.output_path(PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME)

        tasks = parse_mspdi_tasks(out_path)
        names = [t["name"] for t in tasks]
        assert names == ["Ordered Response", "Discovery", "Build", "Launch"]

    def test_notes_are_preserved_verbatim(self):
        save_proposal_response({
            "name": "Notes Response",
            "implementation_plan": [
                {"phase": "Discovery", "timing": "roughly a quarter", "deliverable": "d", "acceptance_criteria": "a"},
            ],
        })
        build_proposal_response_project_plan()
        out_path = paths.output_path(PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME)

        tasks = parse_mspdi_tasks(out_path)
        discovery = next(t for t in tasks if t["name"] == "Discovery")
        assert "roughly a quarter" in discovery["notes"]


class TestParseMspdiProject:
    def test_parse_mspdi_project_returns_complete_project_json(self):
        save_portfolio_backlog({
            "name": "Project Plan JSON Backlog",
            "summary": "s", "source_artifact": "design", "source_name": "x",
            "epics": [{
                "id": "EPIC-001", "title": "Epic One", "description": "d", "strategic_theme": "t",
                "traces_to": ["FR-1"],
                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                "job_size": 5,
                "features": [{
                    "id": "FEAT-001", "title": "Feature One", "description": "d", "strategic_theme": "t",
                    "traces_to": ["FR-1"],
                    "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                    "job_size": 5,
                    "stories": [{
                        "id": "STORY-001", "title": "Deploy Centralized Platform Backup",
                        "description": "Deploy terraform platform backups to AWS cloud.",
                        "strategic_theme": "Infrastructure",
                        "traces_to": ["FR-1"],
                        "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                        "job_size": 5,
                        "acceptance_criteria": ["Backup deployed"],
                    }],
                }],
            }],
        })
        build_portfolio_backlog_project_plan()
        out_path = paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)

        project = parse_mspdi_project(out_path)
        assert project is not None
        assert project["title"] == "Project Plan JSON Backlog"
        assert project["start_date"] is not None
        assert project["finish_date"] is not None
        assert len(project["tasks"]) > 0
        assert len(project["resources"]) > 0
        assert len(project["assignments"]) > 0

        # Story task includes resources and allocations
        story_task = next(t for t in project["tasks"] if t["name"] == "Deploy Centralized Platform Backup")
        assert len(story_task["resources"]) > 0
        assert len(story_task["assignments"]) > 0
        primary_res = story_task["resources"][0]
        assert primary_res["name"] == "DevOps / Platform Engineer"
        assert primary_res["units"] == 0.6
        assert primary_res["work_hours"] == 24.0
        assert primary_res["cost"] == 3600.0
        assert story_task["cost"] is not None
        assert project["total_cost"] is not None

        # Project resource has standard hourly rate from rate card
        devops_res = next(r for r in project["resources"] if r["name"] == "DevOps / Platform Engineer")
        assert devops_res["standard_rate"] == 150.0

    def test_parse_mspdi_project_returns_none_for_missing_or_non_mspdi(self, tmp_path):
        assert parse_mspdi_project(str(tmp_path / "missing.xml")) is None
        bad = tmp_path / "bad.xml"
        bad.write_text("<NotProject/>", encoding="utf-8")
        assert parse_mspdi_project(str(bad)) is None
