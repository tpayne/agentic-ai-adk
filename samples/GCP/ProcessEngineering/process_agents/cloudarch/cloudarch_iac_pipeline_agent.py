# process_agents/cloudarch_iac_pipeline_agent.py

import logging
import os
from google.adk.agents import LoopAgent, SequentialAgent
from google.genai import types

from ..common.utils import getProperty
from .cloudarch_iac_agent import cloudarch_iac_agent
from .cloudarch_iac_validator_agent import cloudarch_iac_validator_agent
from .cloudarch_iac_zip_agent import cloudarch_iac_zip_agent
from ..common.utils_agent import (
    stop_controller_agent,
    status_logger,
    iac_stop_if_ready,
    acquire_pipeline_lock_for_turn,
    release_pipeline_lock_after_run,
)
from ..common.agent_wrappers import ProcessAgent
from process_toolkit.run_lock import PipelineLockedError
from process_toolkit import paths as toolkit_paths

logger = logging.getLogger("ProcessArchitect.CloudArchIacPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))


def _reset_iac_approval_state(callback_context=None) -> "types.Content | None":
    """before_agent_callback for CloudArch_IaC_Review_Loop -- same shape as
    cloudarch_pipeline_agent.py's own _reset_cloudarch_approval_state, minus
    the drawio-ownership claim (this pipeline only ever READS the diagram,
    never writes it, so there is no diagram state of its own to reset).
    Claims the shared output/ directory's pipeline lock before touching any
    state, and clears any stale output/approval.json / output/stop_counter.json
    left over from an earlier, unrelated pipeline run -- without this,
    iac_stop_if_ready could see a stale cloudarch_status/compliance_status
    etc. from a different pipeline's last run and exit on iteration 1
    without this run's own CloudArch_IaC_Validator_Agent ever having
    written iac_status at all."""
    try:
        acquire_pipeline_lock_for_turn("the IaC generation pipeline", callback_context)
    except PipelineLockedError as e:
        return types.Content(role="model", parts=[types.Part(text=str(e))])

    for name in ("approval.json", "stop_counter.json"):
        path = toolkit_paths.output_path(name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    return None


# ---------------------------------------------------------
# STOP CONTROLLER CLONE
# ---------------------------------------------------------
# tools is iac_stop_if_ready, NOT stop_controller_agent.tools -- see
# cloudarch_pipeline_agent.py's own identical comment: CloudArch_IaC_
# Validator_Agent writes iac_status, not compliance/simulation/grounding_
# status or cloudarch_status, so the default/cloudarch stop_if_ready
# variants could never recognize an IaC approval.
stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_CloudArch_IaC",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, iac_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# ---------------------------------------------------------
# IAC GENERATE/VALIDATE LOOP
# ---------------------------------------------------------
# Same three-role shape as CloudArch_Pipeline's own generate/review loop
# (cloudarch_pipeline_agent.py): CloudArch_IaC_Agent generates/revises the
# IaC files, CloudArch_IaC_Validator_Agent checks their syntax and writes
# feedback to the iteration-feedback mailbox (channel="iac"), and the stop
# controller ends the loop once the validator reports "IAC APPROVED". On
# the next iteration CloudArch_IaC_Agent reads that mailbox
# (load_iteration_feedback) and applies the validator's own feedback
# before writing again.
#
# NO after_agent_callback releasing the pipeline lock here -- unlike
# CloudArch_Pipeline, this pipeline has a genuine step AFTER the loop
# stops (zipping, and optionally downloading) -- see
# cloudarch_iac_pipeline's own after_agent_callback below instead. See
# design_doc_create_agent.py's own full_design_doc_pipeline for the
# identical reasoning (release at the pipeline's own true final step, not
# at the loop that merely feeds into it).
cloudarch_iac_review_loop = LoopAgent(
    name="CloudArch_IaC_Review_Loop",
    sub_agents=[
        cloudarch_iac_agent,
        cloudarch_iac_validator_agent,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
    before_agent_callback=_reset_iac_approval_state,
)

# ---------------------------------------------------------
# FULL IAC PIPELINE
# ---------------------------------------------------------
# MANDATORY, NO EXCEPTIONS: cloudarch_iac_zip_agent ALWAYS runs once the
# loop above stops, for EVERY stop reason including MAX_ITERATIONS -- not
# only when the validator approved. CloudArch_IaC_Agent may have already
# written real, valid files by that point; an open validation issue on
# one file is not a reason to withhold the zip from the user, and zipping
# is harmless either way. See design_doc_create_agent.py's own
# full_design_doc_pipeline for the same pattern (its own Stage 4 doc-build
# step runs unconditionally after Stage 2's review loop stops, regardless
# of stop reason) -- this is a confirmed, previously-reproduced bug class
# on this project's sibling pipelines: a step that only runs "when
# approved" instead of "always, after the loop stops" is exactly the kind
# of instruction an orchestrator has been observed silently skipping.
# cloudarch_iac_zip_agent.py's own instructions already describe its
# ask-for-a-destination-if-none-given behavior for the zip/download half
# of this step.
cloudarch_iac_pipeline = SequentialAgent(
    name="CloudArch_IaC_Pipeline",
    description="Use this tool to generate validated Infrastructure-as-Code for the current cloud architecture diagram, in the language/tool the user chooses, and zip it for download.",
    sub_agents=[
        cloudarch_iac_review_loop,
        cloudarch_iac_zip_agent,
    ],
    # Releases this turn's pipeline lock unconditionally once the WHOLE
    # pipeline run ends -- see release_pipeline_lock_after_run's own
    # docstring for the exact gap this closes.
    after_agent_callback=release_pipeline_lock_after_run,
)
