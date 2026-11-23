"""Pipeline for creating or updating the portfolio backlog with iterative review."""

import logging
import os
from google.adk.agents import LoopAgent, SequentialAgent
from google.genai import types

from .portfolio_backlog_agent import portfolio_backlog_agent
from .portfolio_backlog_reviewer_agent import portfolio_backlog_reviewer_agent
from .agent_wrappers import ProcessAgent
from .utils import getProperty
from .utils_agent import (
    mute_agent,
    unmute_agent,
    stop_controller_agent,
    status_logger,
    portfolio_backlog_stop_if_ready,
    acquire_pipeline_lock_for_turn,
    release_pipeline_lock_after_run,
)
from process_interface.run_lock import PipelineLockedError
from process_interface import paths as toolkit_paths
from process_interface.feedback.iteration_feedback import reset_feedback_channels

logger = logging.getLogger("ProcessArchitect.PortfolioBacklogPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))


def _reset_portfolio_backlog_approval_state(callback_context=None) -> "types.Content | None":
    """Claims the turn's pipeline lock before the review loop starts and clears
    stale approval/stop-counter state and feedback mailboxes."""
    try:
        acquire_pipeline_lock_for_turn("the portfolio backlog pipeline", callback_context)
    except PipelineLockedError as e:
        return types.Content(role="model", parts=[types.Part(text=str(e))])

    for name in ("approval.json", "stop_counter.json"):
        path = toolkit_paths.output_path(name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    reset_feedback_channels()
    return None


# Fresh clones of utility agents
mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_PortfolioBacklog",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_PortfolioBacklog",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_PortfolioBacklog",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, portfolio_backlog_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

portfolio_backlog_reviewer_instance = ProcessAgent(
    name=portfolio_backlog_reviewer_agent.name + "_Pipeline",
    model=portfolio_backlog_reviewer_agent.model,
    description=portfolio_backlog_reviewer_agent.description,
    instruction=portfolio_backlog_reviewer_agent.instruction,
    tools=portfolio_backlog_reviewer_agent.tools,
    output_key=portfolio_backlog_reviewer_agent.output_key,
    before_model_callback=portfolio_backlog_reviewer_agent.before_model_callback,
    after_model_callback=portfolio_backlog_reviewer_agent.after_model_callback,
)

# Iterative review loop auditing WBS granularity, acceptance criteria, and goal alignment
portfolio_backlog_review_loop = LoopAgent(
    name="Portfolio_Backlog_Review_Loop",
    sub_agents=[
        portfolio_backlog_agent,
        portfolio_backlog_reviewer_instance,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
    before_agent_callback=_reset_portfolio_backlog_approval_state,
)

portfolio_backlog_pipeline = SequentialAgent(
    name="Portfolio_Backlog_Pipeline",
    description=(
        "Creates a traceable backlog from saved requirements/design or applies explicit changes "
        "to an existing backlog, audited and enriched in an iterative review loop to ensure realistic "
        "WBS task breakdown (no 1-to-1 dummy task repeats), valid resourcing, and core GOAL alignment, "
        "then saves its JSON and supplied-template workbook."
    ),
    sub_agents=[
        mute_agent_instance,
        portfolio_backlog_review_loop,
        unmute_agent_instance,
    ],
    after_agent_callback=release_pipeline_lock_after_run,
)
