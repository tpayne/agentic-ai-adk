"""Coverage for portfolio_backlog/portfolio_backlog.py's switchable
save_portfolio_backlog wrapper -- specifically the staleness note appended
when a project plan was already exported from this backlog (see that
function's own comment for why the check lives here, in process_interface,
rather than in process_toolkit, where importing docgen.project_plan_export
would be a circular import -- that module itself imports FROM
portfolio_backlog.portfolio_backlog to read the saved backlog it exports)."""

from process_interface.portfolio_backlog.portfolio_backlog import save_portfolio_backlog


def _backlog():
    return {
        "name": "Test Backlog", "summary": "s", "source_artifact": "design", "source_name": "x",
        "epics": [{
            "id": "EPIC-001", "title": "Epic One", "description": "d", "strategic_theme": "t",
            "traces_to": ["FR-1"],
            "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
            "job_size": 3,
            "features": [{
                "id": "FEAT-001", "title": "Feature One", "description": "d", "strategic_theme": "t",
                "traces_to": ["FR-1"],
                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                "job_size": 3,
                "stories": [{
                    "id": "STORY-001", "title": "Story One", "description": "d", "strategic_theme": "t",
                    "traces_to": ["FR-1"],
                    "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                    "job_size": 3, "acceptance_criteria": ["works"],
                }],
            }],
        }],
    }


class TestSavePortfolioBacklogStalenessNote:
    def test_no_note_when_no_project_plan_was_ever_exported(self):
        message = save_portfolio_backlog(_backlog())
        assert message.startswith("SUCCESS")
        assert "NOTE" not in message

    def test_note_appended_when_a_project_plan_already_exists(self):
        from process_interface.docgen.project_plan_export import build_portfolio_backlog_project_plan

        save_portfolio_backlog(_backlog())
        export_result = build_portfolio_backlog_project_plan()
        assert export_result.startswith("Project plan successfully exported to "), export_result

        message = save_portfolio_backlog(_backlog())
        assert message.startswith("SUCCESS")
        assert "NOTE: a project plan and its PERT/CPM diagram were previously exported" in message
        assert "portfolio_backlog_project_plan.xml" in message
        assert "portfolio_backlog_pert_cpm.xml" in message

    def test_no_note_on_a_failed_save(self):
        message = save_portfolio_backlog({"not": "a valid backlog"})
        assert message.startswith("ERROR")
        assert "NOTE" not in message
