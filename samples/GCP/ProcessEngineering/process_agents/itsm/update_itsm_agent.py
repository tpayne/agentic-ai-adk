# process_agents/itsm/update_itsm_agent.py
#
# Update-pipeline mirror of create_itsm_agent.py's Full_ITSM_Pipeline --
# same flat ITSM_Agent -> ITSM_Compliance_Agent -> ITSM_Simulation_Agent ->
# stop-controller loop, but entered via ITSM_Update_Analyst (diffs a
# change request against the EXISTING baseline, which "update" presupposes
# already exists, rather than extracting fresh requirements from nothing)
# and using explicit clones of itsm_agent/itsm_compliance_agent/
# itsm_simulation_agent/mute_agent/unmute_agent/stop_controller_agent --
# each ADK BaseAgent instance can only have ONE parent, and
# create_itsm_agent.py's own pipeline already claims the originals as its
# own children (same reasoning as update_process_agent.py's own clones of
# design_agent/compliance_agent/simulation_agent).

import logging
from google.adk.agents import LoopAgent, SequentialAgent

from ..common.utils import (
    load_master_itsm_json,
    load_iteration_feedback,
    save_iteration_feedback,
    getProperty,
)
from .analysis_agent import log_itsm_analysis_metadata
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
from ..common.agent_wrappers import ProcessLlmAgent, ProcessAgent

logger = logging.getLogger("ProcessArchitect.UpdateItsmPipeline")

SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=2))

# ---------------------------------------------------------
# STAGE 1: CHANGE-REQUEST ANALYSIS (diffs against the existing baseline)
# ---------------------------------------------------------
itsm_update_analyst = ProcessLlmAgent(
    name="ITSM_Update_Analyst",
    description=(
        "Diffs a change request against the existing ITSM process document and produces a "
        "structured delta instruction for ITSM_Agent."
    ),
    instruction_file="itsm/update_analysis_agent.txt",
    tools=[
        load_master_itsm_json,
        load_iteration_feedback,
        log_itsm_analysis_metadata,
        save_iteration_feedback,
    ],
)

# ---------------------------------------------------------
# STAGE 2: CLONED LOOP AGENTS
# ---------------------------------------------------------
itsm_inst = ProcessLlmAgent(
    name=itsm_agent.name + "_Update",
    model=itsm_agent.model,
    description=itsm_agent.description,
    instruction=itsm_agent.instruction,
    tools=itsm_agent.tools,
    generate_content_config=itsm_agent.generate_content_config,
    output_key=itsm_agent.output_key,
    before_model_callback=itsm_agent.before_model_callback,
    after_model_callback=itsm_agent.after_model_callback,
)

itsm_compliance_inst = ProcessLlmAgent(
    name=itsm_compliance_agent.name + "_Update",
    model=itsm_compliance_agent.model,
    description=itsm_compliance_agent.description,
    instruction=itsm_compliance_agent.instruction,
    tools=itsm_compliance_agent.tools,
    output_key=itsm_compliance_agent.output_key,
    generate_content_config=itsm_compliance_agent.generate_content_config,
    before_model_callback=itsm_compliance_agent.before_model_callback,
    after_model_callback=itsm_compliance_agent.after_model_callback,
)

itsm_simulation_inst = ProcessLlmAgent(
    name=itsm_simulation_agent.name + "_Update",
    model=itsm_simulation_agent.model,
    description=itsm_simulation_agent.description,
    instruction=itsm_simulation_agent.instruction,
    tools=itsm_simulation_agent.tools,
    output_key=itsm_simulation_agent.output_key,
    generate_content_config=itsm_simulation_agent.generate_content_config,
    before_model_callback=itsm_simulation_agent.before_model_callback,
    after_model_callback=itsm_simulation_agent.after_model_callback,
)

mute_agent_instance = ProcessAgent(
    name=mute_agent.name + "_ITSM_Update",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = ProcessAgent(
    name=unmute_agent.name + "_ITSM_Update",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

stop_controller_agent_instance = ProcessAgent(
    name=stop_controller_agent.name + "_ITSM_Update",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=[status_logger, itsm_stop_if_ready],
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# ---------------------------------------------------------
# RE-ASSEMBLE THE UPDATE LOOP
# ---------------------------------------------------------
itsm_update_review_loop = LoopAgent(
    name="ITSM_Update_Compliance_Loop",
    sub_agents=[
        itsm_inst,
        itsm_compliance_inst,
        itsm_simulation_inst,
        stop_controller_agent_instance,
    ],
    max_iterations=SAFE_LOOP_ITERS,
)

# ---------------------------------------------------------
# UPDATE ITSM PIPELINE
# ---------------------------------------------------------
update_itsm_pipeline = SequentialAgent(
    name="Update_ITSM_Pipeline",
    description=(
        "Use this tool ONLY when the user wants to MODIFY, CHANGE, or UPDATE an EXISTING ITSM "
        "process document. Cannot create a brand-new one from nothing -- use Full_ITSM_Pipeline "
        "for that."
    ),
    sub_agents=[
        mute_agent_instance,
        itsm_update_analyst,
        itsm_update_review_loop,
        build_doc_creation_agent("ITSM_Update_Doc_Creation", schema_type="itsm"),
        unmute_agent_instance,
    ],
    # Releases this turn's pipeline lock unconditionally once the WHOLE
    # pipeline run ends -- see release_pipeline_lock_after_run's own
    # docstring for the exact gap this closes.
    after_agent_callback=release_pipeline_lock_after_run,
)
