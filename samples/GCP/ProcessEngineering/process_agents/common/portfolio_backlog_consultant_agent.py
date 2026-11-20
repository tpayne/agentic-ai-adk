"""Developed in tandem with samples/Neurosan/ProcessEngineering's own
Portfolio_Backlog_Consultant_Agent (registries/portfolio_backlog_consultant.hocon). Mirrors
itsm/consultant_agent.py's own dual-mode (GENERAL vs SPECIFIC) shape exactly -- built in from the
start here, since the Enterprise Agile Portfolio Backlog never had its own consultant agent at all
before this."""

from ..common.utils import load_portfolio_backlog
from ..common.agent_wrappers import ProcessLlmAgent

portfolio_backlog_consultant_agent = ProcessLlmAgent(
    name="Portfolio_Backlog_Consultant_Agent",
    description=(
        "Use this for questions about an EXISTING Enterprise Agile Portfolio Backlog -- its epics, "
        "features, stories, traceability, and priority scores -- or general agile/SAFe "
        "backlog-planning questions that need no saved backlog at all. It cannot create or modify "
        "a backlog."
    ),
    instruction_file="common/portfolio_backlog_consultant_agent.txt",
    tools=[load_portfolio_backlog],
)
