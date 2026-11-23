# process_agents/common/portfolio_backlog_reviewer_agent.py
#
# Audits the quality, granularity, and goal alignment of the Enterprise Agile
# Portfolio Backlog. Verifies realistic multi-tier WBS breakdown (no 1-to-1 dummy
# task duplicates), WSJF priority components, acceptance criteria, role allocations,
# and traceability to requirements/goals. In pipeline mode, records structured review
# feedback into the iteration mailbox and signals PORTFOLIO_BACKLOG_REVIEW_APPROVED
# when verified.

import logging

logger = logging.getLogger("ProcessArchitect.PortfolioBacklogReviewer")

from ..common.utils import (
    load_portfolio_backlog,
    load_requirements_summary,
    load_full_design_context,
    save_iteration_feedback,
    load_iteration_feedback,
)
from ..common.agent_wrappers import ProcessLlmAgent

portfolio_backlog_reviewer_agent = ProcessLlmAgent(
    name="Portfolio_Backlog_Reviewer_Agent",
    description=(
        "Audits the quality, granularity, and goal alignment of the saved Enterprise Agile "
        "Portfolio Backlog. Enforces realistic multi-tier WBS structure (no crude 1-to-1 dummy "
        "task repetitions), observable acceptance criteria, role allocations, WSJF components, "
        "and traceability to requirements and primary goals. Persists review feedback and signals "
        "PORTFOLIO_BACKLOG_REVIEW_APPROVED when all audit criteria are satisfied."
    ),
    instruction_file="common/portfolio_backlog_reviewer_agent.txt",
    tools=[
        load_portfolio_backlog,
        load_requirements_summary,
        load_full_design_context,
        save_iteration_feedback,
        load_iteration_feedback,
    ],
)
