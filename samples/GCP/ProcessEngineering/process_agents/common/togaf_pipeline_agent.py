# process_agents/common/togaf_pipeline_agent.py
#
# Generate/review loop + final document-render stage for TOGAF architecture
# artifacts -- modeled on portfolio_backlog_pipeline_agent.py's own single-
# agent CREATE/UPDATE branching (same two sources, same design-takes-
# precedence rule, see togaf_agent.py), but with ONE lightweight compliance
# review loop bolted on (togaf_compliance_agent + a stop controller,
# max_iterations=SAFE_LOOP_ITERS) -- not Portfolio Backlog's zero review,
# and not the design-document pipeline's full multi-stage HLD/LLD/
# Compliance/Simulation consortium. TOGAF content here is DERIVED/
# transformed from already-validated requirements/design JSON, not
# independently authored from scratch, so it doesn't need that much review
# machinery -- but TOGAF's own reason for existing is governance/compliance,
# so a themed, minimal gate is well-justified.
#
# Structurally closest to cloudarch_pipeline_agent.py (a single generator +
# single reviewer + stop controller inside one LoopAgent, with a
# before_agent_callback resetting stale approval/stop-counter state before
# the loop starts), except TOGAF has a genuine render stage AFTER the
# review loop (the Architecture Vision/Architecture Definition Word
# documents) that CloudArch has no equivalent of -- so the pipeline lock is
# held through that stage too: acquired on the LOOP's own
# before_agent_callback, released on the OUTER SequentialAgent's
# after_agent_callback (release_pipeline_lock_after_run), not right after
# the loop itself.

import logging
import os
from google.adk.agents import LoopAgent, SequentialAgent
from google.genai import types

from .utils import getProperty
from .togaf_agent import togaf_agent
from .togaf_compliance_agent import togaf_compliance_agent
from .doc_creation_agent import build_doc_creation_agent
from .utils_agent import (
    stop_controller_agent,
    status_logger,
    togaf_stop_if_ready,
    acquire_pipeline_lock_for_turn,
    release_pipeline_lock_after_run,
    mute_agent,
    unmute_agent,
)
from .agent_wrappers import ProcessAgent
from process_toolkit.run_lock import PipelineLockedError
from process_toolkit import paths as toolkit_paths
from process_toolkit.feedback.iteration_feedback import reset_feedback_channels

logger = logging.getLogger("ProcessArchitect.TogafPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))


def _reset_togaf_approval_state(callback_context=None) -> "types.Content | None":
    """Claims this turn's pipeline lock before the review loop starts (see
    acquire_pipeline_lock_for_turn's own docstring) and clears any stale
    output/approval.json / output/stop_counter.json / togaf_compliance
    feedback mailbox left over from an earlier, unrelated pipeline run.

    Needed for the exact reason cloudarch_pipeline_agent.py's own
    _reset_cloudarch_approval_state is: _build_stop_if_ready's stop_if_ready
    (see utils_agent.py) has a blanket check -- "JSON APPROVED" in
    approval_state.get("status", "") -- that fires for EVERY pipeline's
    stop controller, including togaf_stop_if_ready, even though
    togaf_compliance_agent never writes to the "status" key (it writes
    togaf_compliance_status). If an earlier, unrelated process/design-doc
    run left status="JSON APPROVED" sitting in the shared approval.json,
    TOGAF's own stop controller would report "JSON APPROVED detected --
    exiting loop" on iteration 1 regardless of whether togaf_compliance_
    agent has approved anything THIS run.

    reset_feedback_channels() additionally clears the togaf_compliance
    mailbox itself (iteration_feedback_togaf_compliance.json) -- CONFIRMED
    AS A REAL GAP: the neuro-san port's own reset_loop_state already does
    this (see coded_tools/common/reset_loop_state_base.py), but nothing on
    this ADK side ever called the shared function at all. Without it, a
    run that ends right after togaf_compliance_agent writes feedback (STOP/
    APPROVED, or STOP/MAX_ITERATIONS with the mailbox left non-empty) would
    leave that feedback sitting in the mailbox; a LATER, unrelated TOGAF
    request in a NEW turn would then have togaf_agent's own REVISION MODE
    check (load_iteration_feedback channel="togaf_compliance") find that
    stale feedback and incorrectly treat a fresh generate-or-update request
    as a revision pass, applying a prior run's feedback instead of
    genuinely building from the current source.
    """
    try:
        acquire_pipeline_lock_for_turn("the TOGAF architecture pipeline", callback_context)
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


# ---------------------------------------------------------
# UTILITY AGENT CLONES
# ---------------------------------------------------------
# Fresh clones, not the shared mute_agent/unmute_agent singletons directly
# -- each ADK BaseAgent instance can only have ONE parent, and other
# pipelines already claim the originals as their own children. Mirrors
# design_doc_create_agent.py / test_specification_pipeline_agent.py's own
# identical fix for the identical constraint.
mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_TOGAF",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_TOGAF",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

# ---------------------------------------------------------
# STOP CONTROLLER CLONE
# ---------------------------------------------------------
# stop_controller_agent is already used bare (unrenamed) as a child agent
# inside create_process_agent.py's review_loop -- an ADK agent can only
# have one parent, so this second consumer clones it, same as every other
# pipeline's own stop-controller clone does.
#
# tools is togaf_stop_if_ready, NOT stop_controller_agent.tools: the
# default stop_if_ready only ever checks compliance_status/simulation_status
# /grounding_status in approval.json, but togaf_compliance_agent writes
# togaf_compliance_status (see save_iteration_feedback's approval markers).
stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_TOGAF",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, togaf_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# ---------------------------------------------------------
# TOGAF GENERATE/REVIEW LOOP
# ---------------------------------------------------------
# Same three-role shape as CloudArch's own loop: togaf_agent builds/revises
# the TOGAF JSON, togaf_compliance_agent audits it and writes feedback to
# the iteration-feedback mailbox (channel="togaf_compliance"), and the stop
# controller ends the loop once the reviewer reports "TOGAF_COMPLIANCE_
# APPROVED" (or iterations run out -- an open compliance item is feedback
# for a FUTURE revision, not a reason to withhold the documents for the
# TOGAF artifacts that already exist). On the next iteration togaf_agent
# reads that mailbox (load_iteration_feedback) and applies the reviewer's
# feedback before generating again.
#
# togaf_agent and togaf_compliance_agent are used here bare (unrenamed)
# since this is their only pipeline -- neither is a child agent anywhere
# else yet, so no clone is needed for either of them.
togaf_review_loop = LoopAgent(
    name="TOGAF_Compliance_Loop",
    sub_agents=[
        togaf_agent,
        togaf_compliance_agent,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
    # Runs exactly once, before the first loop iteration -- see
    # _reset_togaf_approval_state's own docstring for why this can't live
    # inside togaf_agent's own tools instead.
    before_agent_callback=_reset_togaf_approval_state,
)

# ---------------------------------------------------------
# TOGAF PIPELINE
# ---------------------------------------------------------
togaf_pipeline = SequentialAgent(
    name="TOGAF_Pipeline",
    description=(
        "Generates TOGAF-compliant architecture artifacts (an Architecture Vision Document and an "
        "Architecture Definition Document) from the saved design document or, if none exists, the "
        "saved requirements summary -- audited by a lightweight compliance review before the final "
        "documents are rendered. Also applies explicit user-requested changes to an existing TOGAF "
        "artifact set."
    ),
    sub_agents=[
        mute_agent_instance,
        togaf_review_loop,
        build_doc_creation_agent("TOGAF_Doc_Creation", schema_type="togaf"),
        unmute_agent_instance,
    ],
    # Releases this turn's pipeline lock unconditionally once the WHOLE
    # pipeline run ends -- see release_pipeline_lock_after_run's own
    # docstring for the exact gap this closes (a run that stops mid-loop
    # with no further tool calls, e.g. togaf_agent explaining that no
    # saved source exists, would otherwise leave the lock held
    # indefinitely).
    after_agent_callback=release_pipeline_lock_after_run,
)
