# process_agents/itsm/create_itsm_agent.py
#
# Generate/review loop + final document-render stage for a NEW ITSM
# process document. Mirrors togaf_pipeline_agent.py's flat generator ->
# compliance -> stop-controller loop shape (NOT create_process_agent.py's
# "regenerator clone between each reviewer" dance -- itsm.hocon's own
# REQUIRED SEQUENCE is flat: ITSM_Agent -> ITSM_Compliance_Agent ->
# ITSM_Simulation_Agent -> loop_control, looping back to ITSM_Agent itself
# on the next iteration), extended with a THIRD loop member
# (ITSM_Simulation_Agent, informational input to the SAME
# itsm_compliance_status-only stop gate -- not an independent approval
# gate) and preceded by its own dedicated ITSM_Analysis_Agent stage
# (process.py's own shape, since ITSM -- unlike TOGAF -- authors content
# fresh from a brief rather than deriving it from an already-saved
# design/requirements document). No subprocess-expansion stage and no
# JSON-normalization loop -- ITSM has no equivalent of either (ITSM_Agent
# validates and persists the complete document itself, same as
# togaf_agent.py does).

import logging
from google.adk.agents import LoopAgent, SequentialAgent

from ..common.utils import getProperty
from .analysis_agent import itsm_analysis_agent
from .itsm_agent import itsm_agent
from .compliance_agent import itsm_compliance_agent
from .simulation_agent import itsm_simulation_agent
from ..common.doc_creation_agent import build_doc_creation_agent
from ..common.utils_agent import (
    stop_controller_agent,
    status_logger,
    itsm_stop_if_ready,
    release_pipeline_lock_after_run,
    mute_agent,
    unmute_agent,
)
from ..common.agent_wrappers import ProcessAgent

logger = logging.getLogger("ProcessArchitect.CreateItsmPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))

# ---------------------------------------------------------
# UTILITY AGENT CLONES
# ---------------------------------------------------------
# Fresh clones, not the shared mute_agent/unmute_agent/stop_controller_agent
# singletons directly -- each ADK BaseAgent instance can only have ONE
# parent, and other pipelines already claim the originals as their own
# children. Mirrors togaf_pipeline_agent.py's own identical fix for the
# identical constraint.
mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_ITSM",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_ITSM",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

# tools is [status_logger, itsm_stop_if_ready], NOT stop_controller_agent.tools:
# the default stop_if_ready only ever checks compliance_status/simulation_status/
# grounding_status in approval.json, but ITSM_Compliance_Agent writes
# itsm_compliance_status (see save_iteration_feedback's approval markers).
stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_ITSM",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, itsm_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# ---------------------------------------------------------
# ITSM GENERATE/REVIEW LOOP
# ---------------------------------------------------------
# itsm_agent builds/revises the ITSM JSON, itsm_compliance_agent and
# itsm_simulation_agent each audit it and write their own feedback to the
# iteration-feedback mailbox, and the stop controller ends the loop once
# ITSM_Compliance_Agent reports "ITSM_COMPLIANCE_APPROVED" (or iterations
# run out -- an open compliance item is feedback for a FUTURE revision,
# not a reason to withhold the document for the ITSM process that already
# exists). On the next iteration itsm_agent reads both mailboxes
# (load_iteration_feedback) and applies the reviewers' feedback before
# building again.
#
# itsm_agent/itsm_compliance_agent/itsm_simulation_agent are used here
# bare (unrenamed) since this is their only pipeline -- neither is a child
# agent anywhere else yet, so no clone is needed for any of them (the
# UPDATE pipeline's own update_itsm_agent.py clones each of these for
# itself, the same way togaf_pipeline_agent.py's siblings do for shared
# agents used in more than one pipeline).
itsm_review_loop = LoopAgent(
    name="ITSM_Compliance_Loop",
    sub_agents=[
        itsm_agent,
        itsm_compliance_agent,
        itsm_simulation_agent,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
)

# ---------------------------------------------------------
# ITSM PIPELINE
# ---------------------------------------------------------
full_itsm_pipeline = SequentialAgent(
    name="Full_ITSM_Pipeline",
    description=(
        "Use this tool ONLY when the user wants to CREATE or GENERATE a NEW best-of-breed ITSM "
        "process document (incident/problem/change management, request fulfillment, SLAs, a light "
        "CMDB, and RACI governance) from scratch, audited by compliance and structural risk/"
        "coverage review before the final document is rendered."
    ),
    sub_agents=[
        mute_agent_instance,
        itsm_analysis_agent,
        itsm_review_loop,
        build_doc_creation_agent("ITSM_Doc_Creation", schema_type="itsm"),
        unmute_agent_instance,
    ],
    # Releases this turn's pipeline lock unconditionally once the WHOLE
    # pipeline run ends -- see release_pipeline_lock_after_run's own
    # docstring for the exact gap this closes (a run that stops mid-loop
    # with no further tool calls would otherwise leave the lock held
    # indefinitely).
    after_agent_callback=release_pipeline_lock_after_run,
)
