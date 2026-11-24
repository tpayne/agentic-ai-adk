# process_agents/common/project_plan_reviewer_agent.py
#
# Audits the exported project plan (MSPDI XML and PERT/CPM schedule) against
# engagement timescale, phase concurrency, resource allocations, and required
# deliverables to ensure it fully satisfies the project GOAL. In pipeline mode,
# records structured review feedback into the iteration mailbox and signals
# PROJECT_PLAN_REVIEW_APPROVED when verified.

import logging

logger = logging.getLogger("ProcessArchitect.ProjectPlanReviewer")

from ..common.utils import (
    inspect_project_plan,
    load_portfolio_backlog,
    load_requirements_summary,
    save_iteration_feedback,
    load_iteration_feedback,
)
from ..common.agent_wrappers import ProcessLlmAgent

project_plan_reviewer_agent = ProcessLlmAgent(
    name="Project_Plan_Reviewer_Agent",
    description=(
        "Audits the exported project plan (MSPDI XML schedule) against engagement timescale, "
        "phase concurrency, resource allocations, and required deliverables to ensure it fully "
        "satisfies the project GOAL. Checks for zero calendar overrun, proper concurrent streams, "
        "correct role allocations, and milestone deliverable handoffs. Persists review feedback "
        "and signals PROJECT_PLAN_REVIEW_APPROVED when all audit criteria are satisfied."
    ),
    instruction_file="common/project_plan_reviewer_agent.txt",
    tools=[
        inspect_project_plan,
        load_portfolio_backlog,
        load_requirements_summary,
        save_iteration_feedback,
        load_iteration_feedback,
    ],
)
