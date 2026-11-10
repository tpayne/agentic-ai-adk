"""One-shot pipeline for generating the Enterprise Agile Portfolio Backlog workbook."""

from google.adk.agents import SequentialAgent

from .portfolio_backlog_agent import portfolio_backlog_agent

portfolio_backlog_pipeline = SequentialAgent(
    name="Portfolio_Backlog_Pipeline",
    description=(
        "Uses the saved design document when present, otherwise the saved requirements summary, "
        "to produce a traceable epic/feature/story backlog in the supplied portfolio workbook "
        "template, including editable USD costing assumptions."
    ),
    sub_agents=[portfolio_backlog_agent],
)
