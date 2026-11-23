# process_agents/requirements_doc_pipeline_agent.py
#
# Creation pipeline for the requirements domain with iterative review:
# synthesizes a requirements register directly from the user's description,
# audits it via Requirements_Reviewer_Agent against ISO-29148 criteria and the
# overarching GOAL in an iterative review loop (up to SAFE_LOOP_ITERS), and
# renders the final ISO/IEC/IEEE 29148-style Word document once approved.
# Follows the design-pipeline pattern: mute/unmute bracketing, loop_control
# stop gating, and pipeline lock release on exit.

import logging
import os
from google.adk.agents import LoopAgent, SequentialAgent
from google.genai import types

from .requirements_synthesis_agent import requirements_synthesis_agent
from .requirements_reviewer_agent import requirements_reviewer_agent
from .doc_creation_agent import build_doc_creation_agent
from .agent_wrappers import ProcessAgent
from .utils import getProperty
from .utils_agent import (
    mute_agent,
    unmute_agent,
    stop_controller_agent,
    status_logger,
    requirements_stop_if_ready,
    acquire_pipeline_lock_for_turn,
    release_pipeline_lock_after_run,
)
from process_interface.run_lock import PipelineLockedError
from process_interface import paths as toolkit_paths
from process_interface.feedback.iteration_feedback import reset_feedback_channels

logger = logging.getLogger("ProcessArchitect.RequirementsDocPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))


def _reset_requirements_approval_state(callback_context=None) -> "types.Content | None":
    """Claims the turn's pipeline lock before the review loop starts and clears
    stale approval/stop-counter state and feedback mailboxes."""
    try:
        acquire_pipeline_lock_for_turn("the requirements document pipeline", callback_context)
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
    name=mute_agent.name + "_RequirementsDoc",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_RequirementsDoc",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_RequirementsDoc",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, requirements_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

requirements_reviewer_instance = ProcessAgent(
    name=requirements_reviewer_agent.name + "_Pipeline",
    model=requirements_reviewer_agent.model,
    description=requirements_reviewer_agent.description,
    instruction=requirements_reviewer_agent.instruction,
    tools=requirements_reviewer_agent.tools,
    output_key=requirements_reviewer_agent.output_key,
    before_model_callback=requirements_reviewer_agent.before_model_callback,
    after_model_callback=requirements_reviewer_agent.after_model_callback,
)

# Iterative review loop auditing requirements quality and goal alignment
requirements_review_loop = LoopAgent(
    name="Requirements_Review_Loop",
    sub_agents=[
        requirements_synthesis_agent,
        requirements_reviewer_instance,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
    before_agent_callback=_reset_requirements_approval_state,
)

requirements_doc_pipeline = SequentialAgent(
    name="Requirements_Doc_Pipeline",
    description=(
        "Use this tool ONLY when the user wants to CREATE a new requirements document from a "
        "description of a product/system/initiative (not from an existing directory of files, "
        "and not from an already-saved requirements summary). Synthesizes a requirements "
        "register grounded in the description, audits and enriches it in an iterative review loop "
        "to ensure it satisfies the GOAL and ISO 29148 quality criteria, saves it, and renders "
        "the final ISO/IEC/IEEE 29148-style Word document in one call."
    ),
    sub_agents=[
        mute_agent_instance,
        requirements_review_loop,
        build_doc_creation_agent("Requirements_Doc_Creation", schema_type="requirements"),
        unmute_agent_instance,
    ],
    after_agent_callback=release_pipeline_lock_after_run,
)
