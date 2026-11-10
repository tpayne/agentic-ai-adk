from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRIES = PROJECT_ROOT / "registries"


def test_manifest_registers_backlog_network():
    text = (REGISTRIES / "manifest.hocon").read_text(encoding="utf-8")
    assert '"portfolio_backlog.hocon": true' in text


def test_router_routes_and_enables_backlog_network():
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_start = text.index('"tools": [', orchestrator_start)
    tools_text = text[tools_start:text.index("]", tools_start)]

    assert '"/portfolio_backlog"' in tools_text
    assert "### 1g. ENTERPRISE AGILE PORTFOLIO BACKLOG CREATION" in text
    assert "Enterprise Agile Portfolio Backlog from saved requirements/design -> Portfolio_Backlog_Pipeline" in text


def test_backlog_network_loads_one_source_and_writes_the_workbook():
    text = (REGISTRIES / "portfolio_backlog.hocon").read_text(encoding="utf-8")

    assert '"name": "Portfolio_Backlog_Pipeline"' in text
    assert "it takes precedence over a requirements summary" in text
    assert "If both return NOT_FOUND" in text
    assert "load_requirements_summary" in text
    assert "design_json_tool" in text
    assert "save_portfolio_backlog" in text
    assert "priority_components" in text
    assert "acceptance_criteria" in text
    assert "Assumptions worksheet" in text


def test_coded_tool_delegates_to_shared_backlog_persistence():
    text = (
        PROJECT_ROOT
        / "coded_tools"
        / "portfolio_backlog"
        / "save_portfolio_backlog_tool.py"
    ).read_text(encoding="utf-8")
    assert "process_toolkit.portfolio_backlog.portfolio_backlog" in text
    assert "save_portfolio_backlog(backlog, sly_data)" in text


def test_web_artifact_routes_expose_backlog_json_and_workbook():
    text = (PROJECT_ROOT / "cli.py").read_text(encoding="utf-8")

    assert '"portfolio_backlog": "portfolio_backlog.json"' in text
    assert '"/artifacts/portfolio_backlog_workbook/download"' in text
