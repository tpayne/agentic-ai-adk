# process_agents/cloudarch_pipeline_agent.py

import logging
import os
from google.adk.agents import LoopAgent
from google.genai import types

from ..common.utils import getProperty
from .cloudarch_agent import cloudarch_agent
from .cloudarch_reviewer_agent import cloudarch_reviewer_agent
from ..common.utils_agent import stop_controller_agent, status_logger, cloudarch_stop_if_ready
from ..common.agent_wrappers import ProcessAgent
from ..common.utils_agent import PIPELINE_LOCK_TOKEN_STATE_KEY
from process_toolkit.run_lock import acquire_pipeline_lock, release_pipeline_lock, PipelineLockedError

logger = logging.getLogger("ProcessArchitect.CloudArchPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))


def _reset_cloudarch_approval_state(callback_context=None) -> "types.Content | None":
    """
    Claims the shared output/ directory's pipeline lock (see
    process_toolkit.run_lock) before touching any state. Unlike the two
    create pipelines' own reset tools, this runs as a before_agent_callback
    rather than a model-invoked tool, so a lock conflict can short-circuit
    the whole CloudArch_Pipeline run deterministically: returning a
    types.Content here (rather than None) ends the invocation immediately
    with that content as the agent's entire response -- see ADK's own
    BaseAgent._handle_before_agent_callback (end_invocation_on_content=True)
    -- instead of depending on an LLM instruction to notice and relay an
    error string, the way the process/design-doc pipelines' own reset tools
    have to (those run as ordinary tool calls inside an LLM turn, with no
    equivalent short-circuit available).

    Clears any stale output/approval.json / output/stop_counter.json left
    over from an earlier, unrelated pipeline run, before CloudArch_Pipeline's
    review loop starts.

    process/analysis_agent.py and design/design_doc_analysis_agent.py both
    already do this at the start of their own pipelines, but CloudArch never
    had an equivalent -- and it needs one for a subtler reason than "stale
    data looks confusing": _build_stop_if_ready's stop_if_ready (see
    common/utils_agent.py) has a blanket check --
    `"JSON APPROVED" in approval_state.get("status", "")` -- that fires for
    EVERY pipeline's stop controller, including cloudarch_stop_if_ready, even
    though CloudArch's own reviewer never writes to the "status" key (it
    writes cloudarch_status). If an earlier, unrelated process/design-doc run
    left status="JSON APPROVED" sitting in the shared approval.json,
    CloudArch's stop controller would report "JSON APPROVED detected --
    exiting loop" on iteration 1 regardless of whether cloudarch_reviewer_agent
    has approved anything THIS run -- confirmed from a real run's log, where
    the stop reason was misleadingly "JSON APPROVED detected" instead of the
    genuine cloudarch_status=APPROVED reason, and the same stale marker could
    just as easily short-circuit a run that genuinely still needed revision.

    Runs exactly once per CloudArch_Pipeline invocation via before_agent_callback
    -- NOT as one of cloudarch_agent's own tools, since that agent runs on
    every loop iteration and a reset there would erase cloudarch_status right
    after cloudarch_reviewer_agent writes it on iteration 1, breaking the
    approval check on iteration 2 for any run that needs more than one pass.
    """
    try:
        token = acquire_pipeline_lock("the cloud architecture pipeline")
    except PipelineLockedError as e:
        return types.Content(role="model", parts=[types.Part(text=str(e))])
    if callback_context is not None:
        callback_context.state[PIPELINE_LOCK_TOKEN_STATE_KEY] = token

    for name in ("approval.json", "stop_counter.json"):
        path = os.path.join("output", name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    return None


def _release_cloudarch_pipeline_lock(callback_context=None) -> None:
    """Releases the lock _reset_cloudarch_approval_state claimed above,
    once the review loop has genuinely finished (approved, or exhausted
    max_iterations) -- registered as cloudarch_review_loop's own
    after_agent_callback below, which ADK fires exactly once, after the
    LoopAgent's last iteration, regardless of how many iterations it
    actually took. This is the right choke point for CloudArch
    specifically (unlike process/design, where further stages -- subprocess
    expansion, diagram/doc generation -- still follow the review loop's own
    stop, cloudarch.hocon's neuro-san equivalent and this ADK pipeline both
    have nothing left to do once the loop itself stops)."""
    if callback_context is not None:
        release_pipeline_lock(callback_context.state.get(PIPELINE_LOCK_TOKEN_STATE_KEY))

# ---------------------------------------------------------
# STOP CONTROLLER CLONE
# ---------------------------------------------------------
# stop_controller_agent is already used bare (unrenamed) as a child agent
# inside create_process_agent.py's review_loop -- an ADK agent can only
# have one parent, so this second consumer clones it, same as
# design_doc_create_agent.py / design_doc_update_agent.py /
# update_process_agent.py all do for the same reason.
#
# tools is cloudarch_stop_if_ready, NOT stop_controller_agent.tools: the
# default stop_if_ready only ever checks compliance_status/simulation_status
# /grounding_status in approval.json, but cloudarch_reviewer_agent writes
# cloudarch_status (see save_iteration_feedback's approval_markers). Using
# the default meant this stop controller could never recognize a CloudArch
# approval and always ran the full loopIterations regardless of review
# outcome -- confirmed from a real run's log: the reviewer approved on
# iteration 1, approval.json correctly recorded cloudarch_status=APPROVED,
# and stop_if_ready still reported "no stop conditions met" because it
# wasn't one of the keys it was ever checking.
stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_CloudArch",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, cloudarch_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# ---------------------------------------------------------
# CLOUDARCH GENERATE/REVIEW LOOP
# ---------------------------------------------------------
# Same three-role shape as the JSON normalization loops elsewhere
# (normalizer, reviewer, stop -- see json_normalization_loop in
# create_process_agent.py): cloudarch_agent generates/refines the
# architecture, cloudarch_reviewer_agent audits it and writes feedback
# to the iteration-feedback mailbox, and the stop controller ends the
# loop once the reviewer reports "CLOUDARCH APPROVED". On the next
# iteration cloudarch_agent reads that mailbox (load_iteration_feedback)
# and applies the reviewer's feedback before generating again.
#
# cloudarch_agent and cloudarch_reviewer_agent are used here bare
# (unrenamed) since this is their only pipeline -- neither is a child
# agent anywhere else yet, so no clone is needed for either of them.
cloudarch_review_loop = LoopAgent(
    name="CloudArch_Pipeline",
    description="Use this tool to generate or refine a cloud architecture (drawio diagram), audited by a reviewer agent before it is finalized.",
    sub_agents=[
        cloudarch_agent,
        cloudarch_reviewer_agent,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
    # Runs exactly once, before the first loop iteration -- see
    # _reset_cloudarch_approval_state's docstring for why this can't live
    # inside cloudarch_agent's own tools instead.
    before_agent_callback=_reset_cloudarch_approval_state,
    # Runs exactly once, after the LAST loop iteration (however many that
    # took) -- see _release_cloudarch_pipeline_lock's own docstring.
    after_agent_callback=_release_cloudarch_pipeline_lock,
)

# ---------------------------------------------------------
# CLOUDARCH PIPELINE
# ---------------------------------------------------------
cloudarch_pipeline = cloudarch_review_loop
