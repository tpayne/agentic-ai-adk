import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _read(relative_path):
    with open(os.path.join(ROOT, relative_path), encoding="utf-8") as file:
        return file.read()


def test_project_plan_export_agent_registers_the_export_tool_only():
    from process_agents.common.project_plan_export_agent import (
        project_plan_export_agent, export_project_plan,
    )

    assert project_plan_export_agent.name == "Project_Plan_Export_Agent"
    assert set(project_plan_export_agent.tools) == {export_project_plan}


def test_export_project_plan_rejects_an_unknown_schema_type_without_fabricating_anything():
    from process_agents.common.project_plan_export_agent import export_project_plan

    result = export_project_plan("bogus")
    assert result.startswith("ERROR:")


def test_registry_and_root_wiring():
    registry = _read("process_agents/common/agent_registry.py")
    root = _read("process_agents/common/agent.py")

    assert "from .project_plan_export_agent import project_plan_export_agent" in registry
    assert root.count("project_plan_export_agent,") == 2


def test_root_router_routes_project_plan_export_requests():
    text = _read("instructions/common/agent.txt")

    assert "## 9b. PROJECT PLAN (MS PROJECT / PROJECTLIBRE) EXPORT" in text
    assert "Call: Project_Plan_Export_Agent" in text
    assert '"project plan"' in text
    assert '"MS Project"' in text or "Microsoft Project" in text
    assert '"ProjectLibre"' in text


def test_router_requires_specific_wording_not_a_bare_plan():
    text = _read("instructions/common/agent.txt")
    section_start = text.index("## 9b. PROJECT PLAN (MS PROJECT / PROJECTLIBRE) EXPORT")
    section_text = text[section_start:section_start + 2000]
    assert 'Do NOT trigger on a bare "plan" alone' in section_text


def test_portfolio_backlog_gained_an_optional_non_authoritative_directory_read_step():
    text = _read("instructions/common/portfolio_backlog_agent.txt")
    registry_agent = _read("process_agents/common/portfolio_backlog_agent.py")

    assert "OPTIONAL SUPPORTING CONTEXT: EXISTING PROJECT PLAN" in text
    assert "NEVER replaces the design/requirements_summary source of truth" in text
    assert "NEVER introduces an epic/feature/story/traces_to that isn't grounded" in text
    assert "load_directory_context" in registry_agent


def test_router_acknowledges_project_plan_wording_when_nothing_is_saved_yet():
    # CONFIRMED AS A REAL PRODUCTION BUG on the sibling neuro-san port
    # (identical router logic, developed in tandem with this one): a live
    # run asked for a project plan (nothing saved yet) and the router
    # silently dropped "project plan" entirely, asking an unrelated
    # "Business Process Design or Portfolio Backlog?" clarifying question
    # that never mentioned a project plan at all -- even though that is
    # exactly what was asked for. This carve-out must exist so that
    # failure mode cannot recur.
    text = _read("instructions/common/agent.txt")
    assert "### PROJECT PLAN REQUESTED BUT NOTHING SAVED YET" in text
    section_start = text.index("### PROJECT PLAN REQUESTED BUT NOTHING SAVED YET")
    section_text = text[section_start:section_start + 2500]
    assert "CONFIRMED AS A REAL PRODUCTION BUG" in section_text
    assert "Business Process Design" in section_text
    assert "never mentioned a project" in section_text
    assert "you MUST explicitly acknowledge \"project plan\"" in section_text


def test_ambiguous_intent_rule_lists_all_nine_domains_it_claims_to_cover():
    # CONFIRMED AS A REAL BUG: Rule 11 claimed to cover "all nine" domains
    # but its own parenthetical list only named six, omitting Test
    # Specification, TOGAF, and Portfolio Backlog entirely.
    text = _read("instructions/common/agent.txt")
    section_start = text.index("## 11. AMBIGUOUS OR UNCLEAR INTENT")
    section_text = text[section_start:section_start + 800]
    assert "all nine" in section_text
    for domain in (
        "PROCESS", "DESIGN DOCUMENT", "CLOUD ARCHITECTURE DIAGRAM", "REQUIREMENTS SUMMARY",
        "PROPOSAL RESPONSE", "TEST SPECIFICATION", "PORTFOLIO BACKLOG", "TOGAF", "ITSM",
    ):
        assert domain in section_text, f"domain {domain!r} missing from Rule 11's own list"


def test_export_project_plan_accepts_resources_duration_and_holiday_calendar():
    import inspect

    from process_agents.common.project_plan_export_agent import export_project_plan

    params = inspect.signature(export_project_plan).parameters
    assert "resources" in params
    assert "target_duration_weeks" in params
    assert "holiday_calendar" in params


def test_front_man_instructs_extraction_not_fabrication_of_planning_assumptions():
    # CONFIRMED AS A REAL GAP otherwise: without this, the front-man would
    # have no guidance on resources/duration/holidays at all -- and no
    # instruction NOT to fabricate a role/percentage/target the user never
    # actually stated.
    text = _read("instructions/common/project_plan_export_agent.txt")
    assert "OPTIONAL PLANNING ASSUMPTIONS" in text
    assert "never fabricate any of" in text
    assert "never invent a" in text
    assert 'Only "uk" is supported' in text
    assert "WARNING" in text
