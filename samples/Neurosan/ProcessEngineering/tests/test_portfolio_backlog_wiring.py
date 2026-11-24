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
    assert "### 1g. ENTERPRISE AGILE PORTFOLIO BACKLOG CREATION OR UPDATE" in text
    assert "Enterprise Agile Portfolio Backlog creation or update -> Portfolio_Backlog_Pipeline" in text


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
    assert "load_portfolio_backlog" in text
    assert "loader's top-level status field" in text
    assert "preserve all unrelated items" in text


def test_manifest_registers_backlog_consultant_network():
    text = (REGISTRIES / "manifest.hocon").read_text(encoding="utf-8")
    assert '"portfolio_backlog_consultant.hocon": true' in text


def test_router_routes_and_enables_backlog_consultant_network():
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_start = text.index('"tools": [', orchestrator_start)
    tools_text = text[tools_start:text.index("]", tools_start)]

    assert '"/portfolio_backlog_consultant"' in tools_text
    assert "### 4m. ENTERPRISE AGILE PORTFOLIO BACKLOG EXPLANATION, REVIEW, OR GENERAL QUESTION" in text
    assert "-> Call: Portfolio_Backlog_Consultant_Agent" in text
    # The whole point of this network: a general backlog-planning question must route here even
    # with nothing saved -- CONFIRMED AS A REAL GAP every other saved-document consultant agent
    # on this port had before this pattern existed (see test_consultant_dual_mode_pattern.py).
    assert "EVEN IF nothing has ever been saved" in text


def test_backlog_consultant_answers_general_questions_without_requiring_a_saved_backlog():
    text = (REGISTRIES / "portfolio_backlog_consultant.hocon").read_text(encoding="utf-8")
    assert "GENERAL: asks about agile/SAFe backlog-planning concepts" in text
    assert "SPECIFIC: references the user's OWN saved backlog" in text
    assert "Do NOT call load_portfolio_backlog for\na purely general question" in text
    assert '"class": "load_portfolio_backlog_tool.LoadPortfolioBacklogCodedTool"' in text


def test_coded_tool_delegates_to_shared_backlog_persistence():
    text = (
        PROJECT_ROOT
        / "coded_tools"
        / "portfolio_backlog"
        / "save_portfolio_backlog_tool.py"
    ).read_text(encoding="utf-8")
    # Delegates through process_interface (the compliance chokepoint), not
    # process_toolkit directly -- process_interface itself decides whether
    # that call stays local or redirects to the MCP server, per
    # PROCESS_TOOLKIT_MODE.
    assert "process_interface.portfolio_backlog.portfolio_backlog" in text
    assert "save_portfolio_backlog(backlog, sly_data)" in text


def test_load_coded_tool_delegates_to_shared_backlog_loader():
    text = (
        PROJECT_ROOT
        / "coded_tools"
        / "portfolio_backlog"
        / "load_portfolio_backlog_tool.py"
    ).read_text(encoding="utf-8")
    assert "process_interface.portfolio_backlog.portfolio_backlog" in text
    assert "load_portfolio_backlog(sly_data)" in text


def test_load_coded_tool_returns_saved_backlog_from_session_state():
    from coded_tools.portfolio_backlog.load_portfolio_backlog_tool import (
        LoadPortfolioBacklogCodedTool,
    )

    backlog = {"name": "Existing backlog", "epics": []}

    result = LoadPortfolioBacklogCodedTool().invoke(
        {}, {"portfolio_backlog": backlog}
    )

    assert result["status"] == "OK"
    assert result["name"] == "Existing backlog"


def test_web_artifact_routes_expose_backlog_json_and_workbook():
    text = (PROJECT_ROOT / "cli.py").read_text(encoding="utf-8")

    assert '"portfolio_backlog": "portfolio_backlog.json"' in text
    assert '"/artifacts/portfolio_backlog_workbook/download"' in text


def test_portfolio_backlog_reviewer_shims_reexport_canonical_classes():
    from coded_tools.portfolio_backlog_reviewer.load_portfolio_backlog_tool import (
        LoadPortfolioBacklogCodedTool as ReviewerLoadPortfolioBacklog,
    )
    from coded_tools.portfolio_backlog.load_portfolio_backlog_tool import (
        LoadPortfolioBacklogCodedTool as CanonicalLoadPortfolioBacklog,
    )
    from coded_tools.portfolio_backlog_reviewer.load_requirements_summary_tool import (
        LoadRequirementsSummaryCodedTool as ReviewerLoadRequirementsSummary,
    )
    from coded_tools.requirements_summary.load_requirements_summary_tool import (
        LoadRequirementsSummaryCodedTool as CanonicalLoadRequirementsSummary,
    )
    from coded_tools.portfolio_backlog_reviewer.design_json_tool import (
        LoadFullDesignContextCodedTool as ReviewerLoadFullDesignContext,
    )
    from coded_tools.design.design_json_tool import (
        LoadFullDesignContextCodedTool as CanonicalLoadFullDesignContext,
    )

    assert ReviewerLoadPortfolioBacklog is CanonicalLoadPortfolioBacklog
    assert ReviewerLoadRequirementsSummary is CanonicalLoadRequirementsSummary
    assert ReviewerLoadFullDesignContext is CanonicalLoadFullDesignContext

