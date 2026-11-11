"""One-shot pipeline for creating or updating the portfolio backlog and workbook."""

from google.adk.agents import SequentialAgent

from .portfolio_backlog_agent import portfolio_backlog_agent

portfolio_backlog_pipeline = SequentialAgent(
    name="Portfolio_Backlog_Pipeline",
    description=(
        "Creates a traceable backlog from saved requirements/design or applies explicit changes "
        "to an existing backlog, then saves its JSON and supplied-template workbook."
    ),
    sub_agents=[portfolio_backlog_agent],
)
