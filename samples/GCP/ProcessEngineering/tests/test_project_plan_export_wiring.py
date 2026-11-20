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
