# process_agents/update_process_agent.py

import logging
from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent
from google.genai import types

from .utils import (
    load_instruction, 
    load_full_process_context,
    load_master_process_json,
    persist_final_json,
)

# Import the base agents to access their configuration
from .design_agent import design_agent
from .compliance_agent import (
    compliance_agent, 
    log_compliance_metadata,
    load_iteration_feedback,
)

from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .edge_inference_agent import edge_inference_agent
from .doc_generation_agent import doc_generation_agent
from .json_writer_agent import json_writer_agent
from .simulation_agent import simulation_agent
from .subprocess_driver_agent import SubprocessDriverAgent

logger = logging.getLogger("ProcessArchitect.UpdateProcessPipeline")

# ---------------------------------------------------------
# STAGE 1: CONTEXT-AWARE ANALYSIS
# ---------------------------------------------------------
update_analysis_agent = LlmAgent(
    name="Process_Update_Analyst",
    model="gemini-2.0-flash-001",
    instruction=load_instruction("update_analysis_agent.txt"),
    tools=[load_full_process_context,persist_final_json,load_iteration_feedback],
    output_key="analysis_output",
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
)

compliance_inst = LlmAgent(
    name=compliance_agent.name + "_Update",
    model=compliance_agent.model,
    description=compliance_agent.description,
    instruction=compliance_agent.instruction,
    tools=compliance_agent.tools,
    output_key=compliance_agent.output_key,
    generate_content_config=compliance_agent.generate_content_config,
)

simulation_inst = LlmAgent(
    name=simulation_agent.name + "_Update",
    model=simulation_agent.model,
    description=simulation_agent.description,
    instruction=simulation_agent.instruction,
    tools=simulation_agent.tools,
    output_key=simulation_agent.output_key,
    generate_content_config=simulation_agent.generate_content_config,
)

normalizer_inst = LlmAgent(
    name=json_normalizer_agent.name + "_Update",
    model=json_normalizer_agent.model,
    description=json_normalizer_agent.description,
    instruction=json_normalizer_agent.instruction,
    tools=json_normalizer_agent.tools,
    generate_content_config=json_normalizer_agent.generate_content_config,
    output_key=json_normalizer_agent.output_key,
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
)

writer_inst = LlmAgent(
    name=json_writer_agent.name + "_Update",
    model=json_writer_agent.model,
    description=json_writer_agent.description,
    instruction=json_writer_agent.instruction,
    tools=json_writer_agent.tools,
    generate_content_config=json_writer_agent.generate_content_config,
)

edge_inst = LlmAgent(
    name=edge_inference_agent.name + "_Update",
    model=edge_inference_agent.model,
    description=edge_inference_agent.description,
    instruction=edge_inference_agent.instruction,
    tools=edge_inference_agent.tools,
    include_contents=edge_inference_agent.include_contents,
    generate_content_config=edge_inference_agent.generate_content_config,
)

doc_inst = LlmAgent(
    name=doc_generation_agent.name + "_Update",
    model=doc_generation_agent.model,
    description=doc_generation_agent.description,
    instruction=doc_generation_agent.instruction,
    tools=doc_generation_agent.tools,
)

# Subprocess driver is NOT an LlmAgent — clone manually
subprocess_inst = SubprocessDriverAgent(name="Subprocess_Driver_Agent_Update")

# Specialized instance for internal compliance logic
design_compliance_inst = LlmAgent(
    name="Design_Compliance_Update_Review",
    model=design_agent.model,
    instruction="Review the design against compliance rules. Report findings ONLY via log_design_metadata. Output ONLY 'REVIEW_COMPLETE'.",
    output_key="update_compliance_review",
    tools=[load_master_process_json,log_compliance_metadata],
)

# ---------------------------------------------------------
# RE-ASSEMBLE THE UPDATE PIPELINE
# ---------------------------------------------------------

review_update_loop = LoopAgent(
    name="Update_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Update_Stage",
            sub_agents=[
                design_inst,
                compliance_inst,
                design_compliance_inst,
                simulation_inst,
            ],
        )
    ],
    max_iterations=5,
)

json_update_normalization_loop = SequentialAgent(
    name="Update_Normalization_Loop",
    sub_agents=[
        LoopAgent(
            name="Update_Normalizer_Sequence",
            sub_agents=[normalizer_inst, reviewer_inst],
            max_iterations=5,
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
        update_analysis_agent,          # Step 1: Context Loading & Merging
        review_update_loop,             # Step 2: Re-Design & Audit
        json_update_normalization_loop, # Step 3: Stabilization
        subprocess_inst,                # Step 4: Subprocess Regeneration
        edge_inst,                      # Step 5: Logic Flow
        doc_inst,                       # Step 6: Artifact Re-Build
    ],
)
