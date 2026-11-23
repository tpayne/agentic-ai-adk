"""Builds and persists an Enterprise Agile Portfolio Backlog from saved requirements or design JSON."""

from ..common.utils import (
    load_directory_context,
    load_full_design_context,
    load_iteration_feedback,
    load_portfolio_backlog,
    load_requirements_summary,
    save_portfolio_backlog,
)
from ..common.agent_wrappers import ProcessLlmAgent

portfolio_backlog_agent = ProcessLlmAgent(
    name="Portfolio_Backlog_Agent",
    description=(
        "Reads the saved design document or, if no design exists, the saved requirements summary; "
        "generates a traceable epic/feature/story backlog and saves the supplied-template "
        "workbook with WSJF formulas and editable USD cost assumptions. In revision mode, applies "
        "feedback from the reviewer loop to enrich task breakdowns and ensure goal fulfillment. "
        "Optionally reads a user-named directory of reference material (e.g. an existing project "
        "plan) as non-authoritative background only."
    ),
    instruction_file="common/portfolio_backlog_agent.txt",
    tools=[
        load_requirements_summary,
        load_full_design_context,
        load_portfolio_backlog,
        load_iteration_feedback,
        save_portfolio_backlog,
        load_directory_context,
    ],
)
