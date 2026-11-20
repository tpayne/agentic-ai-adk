from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRIES = PROJECT_ROOT / "registries"


def test_manifest_registers_project_plan_export_network():
    text = (REGISTRIES / "manifest.hocon").read_text(encoding="utf-8")
    assert '"project_plan_export.hocon": true' in text


def test_router_routes_and_enables_project_plan_export_network():
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_start = text.index('"tools": [', orchestrator_start)
    tools_text = text[tools_start:text.index("]", tools_start)]

    assert '"/project_plan_export"' in tools_text
    assert "# PROJECT PLAN (MS PROJECT / PROJECTLIBRE) EXPORT" in text
    assert "call `/project_plan_export`" in text


def test_router_requires_specific_wording_not_a_bare_plan():
    # CONFIRMED anti-collision discipline, same as the vsdx/"vision
    # document" substring guard: a bare "plan" must not trigger this
    # section, since that word alone is routine phrasing for the
    # backlog/proposal itself.
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    section_start = text.index("# PROJECT PLAN (MS PROJECT / PROJECTLIBRE) EXPORT")
    section_text = text[section_start:section_start + 2000]
    assert 'Do NOT trigger on a bare "plan" alone' in section_text
    assert '"project plan"' in section_text
    assert '"MS Project"' in section_text
    assert '"ProjectLibre"' in section_text


def test_project_plan_export_network_front_man_determines_schema_type():
    text = (REGISTRIES / "project_plan_export.hocon").read_text(encoding="utf-8")
    assert '"name": "Project_Plan_Export_Agent_Main"' in text
    assert "DETERMINE schema_type FIRST" in text
    assert "schema_type =" in text
    assert "export_project_plan" in text
    assert '"enum": ["portfolio_backlog", "proposal_response"]' in text


def test_project_plan_export_network_never_overwrites_the_saved_source_json():
    # Structural guarantee: the ONLY tool this network's front-man can
    # call is export_project_plan, which itself has no save/persist path
    # for portfolio_backlog.json/proposal_response.json -- this network
    # cannot mutate either source artifact even if asked to.
    text = (REGISTRIES / "project_plan_export.hocon").read_text(encoding="utf-8")
    assert '"tools": ["export_project_plan"]' in text
    assert "save_portfolio_backlog" not in text
    assert "save_proposal_response" not in text


def test_coded_tool_delegates_to_shared_project_plan_persistence():
    text = (
        PROJECT_ROOT / "coded_tools" / "project_plan_export" / "project_plan_export_tool.py"
    ).read_text(encoding="utf-8")
    assert "from process_interface.docgen.project_plan_export import" in text
    assert "build_portfolio_backlog_project_plan" in text
    assert "build_proposal_response_project_plan" in text


def test_portfolio_backlog_gained_an_optional_non_authoritative_directory_read_step():
    text = (REGISTRIES / "portfolio_backlog.hocon").read_text(encoding="utf-8")
    assert "OPTIONAL SUPPORTING CONTEXT: EXISTING PROJECT PLAN" in text
    assert "load_directory_context" in text
    assert "NEVER replaces the design/requirements_summary source of truth" in text
    assert "NEVER introduces an epic/feature/story/traces_to that isn't grounded" in text
    assert '"class": "load_directory_context_tool.LoadDirectoryContextCodedTool"' in text
