import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _read(relative_path):
    with open(os.path.join(ROOT, relative_path), encoding="utf-8") as file:
        return file.read()


def test_pipeline_registers_backlog_agent_and_source_tools():
    from process_agents.common.portfolio_backlog_pipeline_agent import (
        portfolio_backlog_pipeline,
        portfolio_backlog_review_loop,
        portfolio_backlog_reviewer_instance,
        stop_controller_agent_instance,
    )
    from process_agents.common.portfolio_backlog_agent import portfolio_backlog_agent
    from process_agents.common.portfolio_backlog_reviewer_agent import portfolio_backlog_reviewer_agent
    from process_agents.common.utils import (
        load_full_design_context,
        load_portfolio_backlog,
        load_requirements_summary,
        save_portfolio_backlog,
        load_iteration_feedback,
    )

    assert portfolio_backlog_review_loop in portfolio_backlog_pipeline.sub_agents
    assert portfolio_backlog_agent in portfolio_backlog_review_loop.sub_agents
    assert portfolio_backlog_reviewer_instance in portfolio_backlog_review_loop.sub_agents
    assert stop_controller_agent_instance in portfolio_backlog_review_loop.sub_agents
    assert {
        load_full_design_context,
        load_portfolio_backlog,
        load_requirements_summary,
        save_portfolio_backlog,
        load_iteration_feedback,
    } <= set(portfolio_backlog_agent.tools)
    registry = _read("process_agents/common/agent_registry.py")
    root = _read("process_agents/common/agent.py")
    assert "from .portfolio_backlog_pipeline_agent import portfolio_backlog_pipeline" in registry
    assert root.count("portfolio_backlog_pipeline,") == 2
    assert "from .portfolio_backlog_reviewer_agent import portfolio_backlog_reviewer_agent" in registry
    assert root.count("portfolio_backlog_reviewer_agent,") == 2


def test_portfolio_backlog_reviewer_wiring_and_instructions():
    from process_agents.common.portfolio_backlog_reviewer_agent import portfolio_backlog_reviewer_agent
    from process_agents.common.utils import (
        load_portfolio_backlog,
        load_requirements_summary,
        load_full_design_context,
        save_iteration_feedback,
        load_iteration_feedback,
    )

    assert {
        load_portfolio_backlog,
        load_requirements_summary,
        load_full_design_context,
        save_iteration_feedback,
        load_iteration_feedback,
    } <= set(portfolio_backlog_reviewer_agent.tools)

    text = _read("instructions/common/portfolio_backlog_reviewer_agent.txt")
    assert "WORK BREAKDOWN STRUCTURE (WBS) INTEGRITY" in text
    assert "crude 1-to-1-to-1 dummy hierarchy repetition" in text
    assert "PORTFOLIO_BACKLOG_REVIEW_APPROVED" in text
    assert "ACCEPTANCE CRITERIA SUBSTANCE" in text
    assert "RESOURCING & WSJF PRIORITIZATION" in text


def test_reset_portfolio_backlog_approval_state(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from process_toolkit import paths

    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    os.makedirs("output", exist_ok=True)

    stale_feedback = paths.output_path("iteration_feedback_portfolio_backlog_reviewer.json")
    with open(stale_feedback, "w", encoding="utf-8") as f:
        json.dump({"status": "PORTFOLIO_BACKLOG_REVIEW_APPROVED", "data": []}, f)

    from process_agents.common.portfolio_backlog_pipeline_agent import _reset_portfolio_backlog_approval_state

    context = SimpleNamespace(state={}, invocation_id="test-inv")
    assert _reset_portfolio_backlog_approval_state(context) is None
    assert not os.path.exists(stale_feedback)


def test_backlog_instructions_define_source_precedence_and_quality_contract():
    text = _read("instructions/common/portfolio_backlog_agent.txt")

    assert "it takes precedence" in text
    assert "If both return `NOT_FOUND`" in text
    assert "priority_components" in text
    assert "acceptance_criteria" in text
    assert "source-grounded" in text
    assert "not quotes or an approved" in text
    assert "budget." in text


def test_backlog_consultant_registers_load_tool_only():
    from process_agents.common.portfolio_backlog_consultant_agent import (
        portfolio_backlog_consultant_agent,
    )
    from process_agents.common.utils import load_portfolio_backlog

    assert set(portfolio_backlog_consultant_agent.tools) == {load_portfolio_backlog}

    # Structural guarantee against mutation: no save/persist tool exists on this agent's own
    # tool list at all -- it is read-only.
    tool_names = {getattr(tool, "__name__", "") for tool in portfolio_backlog_consultant_agent.tools}
    assert not any(name.startswith("save_") or name.startswith("persist_") for name in tool_names)

    registry = _read("process_agents/common/agent_registry.py")
    root = _read("process_agents/common/agent.py")
    assert "from .portfolio_backlog_consultant_agent import portfolio_backlog_consultant_agent" in registry
    assert root.count("portfolio_backlog_consultant_agent,") == 2


def test_backlog_consultant_answers_general_questions_without_requiring_a_saved_backlog():
    # CONFIRMED AS A REAL GAP on the sibling neuro-san port (identical agent logic, developed in
    # tandem with this one), on every other saved-document consultant agent on that port before
    # this pattern existed: a purely general backlog-planning question used to be refused outright
    # for lack of a saved backlog, even though answering it needs no backlog at all.
    text = _read("instructions/common/portfolio_backlog_consultant_agent.txt")
    assert "GENERAL: asks about agile/SAFe backlog-planning concepts" in text
    assert "SPECIFIC: references the user's OWN saved backlog" in text
    assert "Do NOT CALL the\n`load_portfolio_backlog` tool for a purely general question" in text


def test_root_router_routes_backlog_consultant_requests():
    text = _read("instructions/common/agent.txt")

    assert "### 4m. ENTERPRISE AGILE PORTFOLIO BACKLOG EXPLANATION, REVIEW, OR GENERAL QUESTION" in text
    assert "→ Call: Portfolio_Backlog_Consultant_Agent" in text
    assert "EVEN IF nothing has ever been saved" in text


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
