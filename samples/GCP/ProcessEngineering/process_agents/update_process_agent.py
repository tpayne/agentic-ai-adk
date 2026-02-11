# process_agents/update_process_agent.py

import logging
from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent, Agent
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .utils import (
    getProperty,
    load_instruction, 
    load_full_process_context,
    load_master_process_json,
    load_iteration_feedback,
    persist_final_json,
    save_iteration_feedback,
)

# Import the base agents to access their configuration
from .design_agent import design_agent
from .compliance_agent import (
    compliance_agent, 
    log_compliance_metadata,
)

from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .doc_creation_agent import build_doc_creation_agent
from .json_writer_agent import json_writer_agent
from .simulation_agent import simulation_agent
from .grounding_agent import grounding_agent
from .subprocess_driver_agent import SubprocessDriverAgent

from .utils_agent import (
    mute_agent, 
    unmute_agent, 
    stop_controller_agent
)

logger = logging.getLogger("ProcessArchitect.UpdateProcessPipeline")

# ------------------------ UPDATE PIPELINE DEFINITION ------------------------
mute_agent_instance = Agent(
    name=mute_agent.name + "_Update",
    model=mute_agent.model,
    description=mute_agent.description,
    instruction=mute_agent.instruction,
    tools=mute_agent.tools,
)

unmute_agent_instance = Agent(
    name=unmute_agent.name + "_Update",
    model=unmute_agent.model,
    description=unmute_agent.description,
    instruction=unmute_agent.instruction,
    tools=unmute_agent.tools,
)

stop_controller_agent_instance = Agent(
    name=stop_controller_agent.name + "_Update",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
)

# ---------------------------------------------------------
# STAGE 1: CONTEXT-AWARE ANALYSIS
# ---------------------------------------------------------
update_analysis_agent = LlmAgent(
    name="Process_Update_Analyst",
    description="Analyzes user requests for process changes and identifies required revisions against the existing design.",
    model=design_agent.model,
    instruction=load_instruction("update_analysis_agent.txt"),
    tools=[load_full_process_context,load_iteration_feedback,save_iteration_feedback],
    generate_content_config=design_agent.generate_content_config,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback
)

# ---------------------------------------------------------
# STAGE 2-6: UNIQUE INSTANCES FOR UPDATE PIPELINE
# Explicit clones (no clone_agent helper)
# ---------------------------------------------------------

design_inst = LlmAgent(
    name=design_agent.name + "_Update",
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    generate_content_config=design_agent.generate_content_config,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback
)

compliance_inst = LlmAgent(
    name=compliance_agent.name + "_Update",
    model=compliance_agent.model,
    description=compliance_agent.description,
    instruction=compliance_agent.instruction,
    tools=compliance_agent.tools,
    output_key=compliance_agent.output_key,
    generate_content_config=compliance_agent.generate_content_config,
    before_model_callback=compliance_agent.before_model_callback,
    after_model_callback=compliance_agent.after_model_callback
)

simulation_inst = LlmAgent(
    name=simulation_agent.name + "_Update",
    model=simulation_agent.model,
    description=simulation_agent.description,
    instruction=simulation_agent.instruction,
    tools=simulation_agent.tools,
    output_key=simulation_agent.output_key,
    generate_content_config=simulation_agent.generate_content_config,
    before_model_callback=simulation_agent.before_model_callback,
    after_model_callback=simulation_agent.after_model_callback
)

normalizer_inst = LlmAgent(
    name=json_normalizer_agent.name + "_Update",
    model=json_normalizer_agent.model,
    description=json_normalizer_agent.description,
    instruction=json_normalizer_agent.instruction,
    tools=json_normalizer_agent.tools,
    generate_content_config=json_normalizer_agent.generate_content_config,
    output_key=json_normalizer_agent.output_key,
    include_contents=json_normalizer_agent.include_contents,
    before_model_callback=json_normalizer_agent.before_model_callback,
    after_model_callback=json_normalizer_agent.after_model_callback
)

reviewer_inst = LlmAgent(
    name=json_review_agent.name + "_Update",
    model=json_review_agent.model,
    description=json_review_agent.description,
    instruction=json_review_agent.instruction,
    tools=json_review_agent.tools,
    generate_content_config=json_review_agent.generate_content_config,
    output_key=json_review_agent.output_key,
    include_contents=json_review_agent.include_contents,
    before_model_callback=json_review_agent.before_model_callback,
    after_model_callback=json_review_agent.after_model_callback
)

writer_inst = Agent(
    name=json_writer_agent.name + "_Update",
    model=json_writer_agent.model,
    description=json_writer_agent.description,
    instruction=json_writer_agent.instruction,
    tools=json_writer_agent.tools,
    generate_content_config=json_writer_agent.generate_content_config,
    output_key=json_writer_agent.output_key,
    before_model_callback=json_writer_agent.before_model_callback,
    after_model_callback=json_writer_agent.after_model_callback
)

design_simulation_inst = Agent(
    name=design_agent.name + "_Simulation_Update",
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

design_grounding_inst = Agent(
    name=design_agent.name + "_Grounding_Update",
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

grounding_inst = LlmAgent(
    name=grounding_agent.name + "_Update",
    model=grounding_agent.model,
    description=grounding_agent.description,
    instruction=grounding_agent.instruction,
    tools=grounding_agent.tools,
    output_key=grounding_agent.output_key,
    generate_content_config=grounding_agent.generate_content_config,
    before_model_callback=grounding_agent.before_model_callback,
    after_model_callback=grounding_agent.after_model_callback,
)

# Subprocess driver is NOT an LlmAgent — clone manually
subprocess_inst = SubprocessDriverAgent(name="Subprocess_Driver_Agent_Update")

# Specialized instance for internal compliance logic
design_compliance_inst = Agent(
    name=design_agent.name + "_Compliance_Update_Review",
    model=design_agent.model,
    instruction=design_agent.instruction,
    output_key=design_agent.output_key,
    tools=design_agent.tools,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

# ---------------------------------------------------------
# RE-ASSEMBLE THE UPDATE PIPELINE
# ---------------------------------------------------------
# ---------- Add Stop_Controller FIRST in the loop stage ----------

sub_update_agents = [
    design_inst,
    compliance_inst,
    design_compliance_inst,
    simulation_inst,
    design_simulation_inst,
]

if getProperty("enableGroundingAgent", default="true"):
    logger.debug("Grounding agent ENABLED in design loop.")
    sub_update_agents += [
        grounding_inst,
        design_grounding_inst,
    ]
else:
    logger.debug("Grounding agent DISABLED in design loop.")

sub_update_agents.append(stop_controller_agent_instance)

review_update_loop = LoopAgent(
    name="Update_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Update_Stage",
            sub_agents=sub_update_agents,
        )
    ],
    max_iterations=int(getProperty("loopIterations", default=6)),
)

json_stop_agent_instance = Agent(
    name="JSON_Review_Stop_Controller_Update",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

json_update_normalization_loop = SequentialAgent(
    name="Update_Normalization_Loop",
    sub_agents=[
        LoopAgent(
            name="Update_Normalizer_Sequence",
            sub_agents=[normalizer_inst, reviewer_inst, json_stop_agent_instance],
            max_iterations=int(getProperty("loopIterations", default=6)),
        ),
        writer_inst,
    ],
)

# ---------------------------------------------------------
# UPDATE PROCESS PIPELINE
# ---------------------------------------------------------
update_design_pipeline = SequentialAgent(
    name="Update_Design_Pipeline",
    description="Use this tool ONLY when the user wants to MODIFY, CHANGE, or UPDATE an existing process.",
    sub_agents=[
        mute_agent_instance,                    # Mute console output
        update_analysis_agent,                  # Step 1: Context Loading & Merging
        review_update_loop,                     # Step 2: Re-Design & Audit
        json_update_normalization_loop,         # Step 3: Stabilization
        subprocess_inst,                        # Step 4: Subprocess Regeneration
        build_doc_creation_agent("Update"),     # Step 5: Artifact Build        
        unmute_agent_instance,                  # Unmute console output
    ],
)
