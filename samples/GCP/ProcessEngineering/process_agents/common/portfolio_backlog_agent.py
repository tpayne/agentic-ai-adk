"""Builds and persists a traceable SAFe WSJF backlog from saved requirements or design JSON."""

from ..common.utils import (
    load_full_design_context,
    load_requirements_summary,
    save_portfolio_backlog,
)
from ..common.agent_wrappers import ProcessLlmAgent

portfolio_backlog_agent = ProcessLlmAgent(
    name="Portfolio_Backlog_Agent",
    description=(
        "Reads the saved design document or, if no design exists, the saved requirements summary; "
        "generates a traceable SAFe epic/feature/story backlog and saves the supplied-template "
        "workbook with WSJF formulas and editable USD cost assumptions."
    ),
    instruction_file="common/portfolio_backlog_agent.txt",
    tools=[
        load_requirements_summary,
        load_full_design_context,
        save_portfolio_backlog,
    ],
)
