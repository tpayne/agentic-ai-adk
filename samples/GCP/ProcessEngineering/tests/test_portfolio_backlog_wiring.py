import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _read(relative_path):
    with open(os.path.join(ROOT, relative_path), encoding="utf-8") as file:
        return file.read()


def test_pipeline_registers_backlog_agent_and_source_tools():
    from process_agents.common.portfolio_backlog_pipeline_agent import portfolio_backlog_pipeline
    from process_agents.common.portfolio_backlog_agent import portfolio_backlog_agent
    from process_agents.common.utils import (
        load_full_design_context,
        load_portfolio_backlog,
        load_requirements_summary,
        save_portfolio_backlog,
    )

    assert portfolio_backlog_agent in portfolio_backlog_pipeline.sub_agents
    assert {
        load_full_design_context,
        load_portfolio_backlog,
        load_requirements_summary,
        save_portfolio_backlog,
    } <= set(portfolio_backlog_agent.tools)
    registry = _read("process_agents/common/agent_registry.py")
    root = _read("process_agents/common/agent.py")
    assert "from .portfolio_backlog_pipeline_agent import portfolio_backlog_pipeline" in registry
    assert root.count("portfolio_backlog_pipeline,") == 2


def test_backlog_instructions_define_source_precedence_and_quality_contract():
    text = _read("instructions/common/portfolio_backlog_agent.txt")

    assert "it takes precedence" in text
    assert "If both return `NOT_FOUND`" in text
    assert "priority_components" in text
    assert "acceptance_criteria" in text
    assert "source-grounded" in text
    assert "not quotes or an approved" in text
    assert "budget." in text


def test_root_router_routes_specific_enterprise_agile_backlog_requests():
    text = _read("instructions/common/agent.txt")

    assert "Enterprise Agile Portfolio Backlog signals are" in text
    assert "### 1g. ENTERPRISE AGILE PORTFOLIO BACKLOG CREATION OR UPDATE" in text
    assert "→ Call: Portfolio_Backlog_Pipeline" in text
    assert "loads and modifies the" in text
    assert "`portfolio_backlog.json`" in text
    assert "Enterprise Agile Portfolio Backlog creation or update → Portfolio_Backlog_Pipeline" in text


def test_web_artifact_routes_expose_backlog_json_and_workbook():
    text = _read("process_agents/common/agent.py")

    assert '"portfolio_backlog": "portfolio_backlog.json"' in text
    assert '"/artifacts/portfolio_backlog_workbook/download"' in text
