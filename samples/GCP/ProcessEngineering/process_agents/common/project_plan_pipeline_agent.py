# process_agents/common/project_plan_pipeline_agent.py
#
# Pipeline for exporting and reviewing Microsoft Project (MSPDI XML) project plans
# and companion PERT/CPM network diagrams from the saved portfolio backlog or proposal
# response. Follows the design-pipeline pattern:
# - Mute / unmute bracketing
# - Iterative review loop with Project_Plan_Reviewer_Agent
# - Stop controller gated on project_plan_review_status == APPROVED
# - Automatic pipeline lock acquisition and release

import logging
import os
from google.adk.agents import LoopAgent, SequentialAgent
from google.genai import types

from .project_plan_export_agent import project_plan_export_agent
from .project_plan_reviewer_agent import project_plan_reviewer_agent
from .agent_wrappers import ProcessAgent
from .utils import getProperty
from .utils_agent import (
    mute_agent,
    unmute_agent,
    stop_controller_agent,
    status_logger,
    project_plan_stop_if_ready,
    acquire_pipeline_lock_for_turn,
    release_pipeline_lock_after_run,
)
from process_interface.run_lock import PipelineLockedError
from process_interface import paths as toolkit_paths
from process_interface.feedback.iteration_feedback import reset_feedback_channels

logger = logging.getLogger("ProcessArchitect.ProjectPlanPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))


def _reset_project_plan_approval_state(callback_context=None) -> "types.Content | None":
    """Claims the turn's pipeline lock before the review loop starts and clears
    stale approval/stop-counter state and feedback mailboxes."""
    try:
        acquire_pipeline_lock_for_turn("the project plan pipeline", callback_context)
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
    name=mute_agent.name + "_ProjectPlan",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_ProjectPlan",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_ProjectPlan",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, project_plan_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

project_plan_export_instance = ProcessAgent(
    name=project_plan_export_agent.name + "_Pipeline",
    model=project_plan_export_agent.model,
    description=project_plan_export_agent.description,
    instruction=project_plan_export_agent.instruction,
    tools=project_plan_export_agent.tools,
    output_key=project_plan_export_agent.output_key,
    before_model_callback=project_plan_export_agent.before_model_callback,
    after_model_callback=project_plan_export_agent.after_model_callback,
)

project_plan_reviewer_instance = ProcessAgent(
    name=project_plan_reviewer_agent.name + "_Pipeline",
    model=project_plan_reviewer_agent.model,
    description=project_plan_reviewer_agent.description,
    instruction=project_plan_reviewer_agent.instruction,
    tools=project_plan_reviewer_agent.tools,
    output_key=project_plan_reviewer_agent.output_key,
    before_model_callback=project_plan_reviewer_agent.before_model_callback,
    after_model_callback=project_plan_reviewer_agent.after_model_callback,
)

# Iterative review loop auditing schedule compliance, concurrency, resourcing, and goal alignment
project_plan_review_loop = LoopAgent(
    name="Project_Plan_Review_Loop",
    sub_agents=[
        project_plan_export_instance,
        project_plan_reviewer_instance,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
    before_agent_callback=_reset_project_plan_approval_state,
)

project_plan_pipeline = SequentialAgent(
    name="Project_Plan_Pipeline",
    description=(
        "Exports the current Enterprise Agile Portfolio Backlog or Proposal Response as a Microsoft "
        "Project / ProjectLibre (MSPDI XML) project plan file and companion PERT/CPM diagram, audited "
        "and verified in an iterative review loop to ensure strict timescale compliance (zero overrun), "
        "phase concurrency, resource allocations, and deliverable coverage meeting the project GOAL."
    ),
    sub_agents=[
        mute_agent_instance,
        project_plan_review_loop,
        unmute_agent_instance,
    ],
    after_agent_callback=release_pipeline_lock_after_run,
)
