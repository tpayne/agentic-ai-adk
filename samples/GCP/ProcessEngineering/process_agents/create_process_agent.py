# process_agents/create_process_agent.py

from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent
from google.adk.tools.tool_context import ToolContext

import time
import logging
import random

# Import sub-agents
from .analysis_agent import analysis_agent
from .design_agent import design_agent as design_agent
from .compliance_agent import compliance_agent
from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .edge_inference_agent import edge_inference_agent
from .doc_generation_agent import doc_generation_agent
from .json_writer_agent import json_writer_agent
from .simulation_agent import simulation_agent
from .grounding_agent import grounding_agent
from .subprocess_driver_agent import SubprocessDriverAgent
from .utils import getProperty

logger = logging.getLogger("ProcessArchitect.CreateProcessPipeline")

# ---------------------------------------------------------
# PIPELINE DEFINITION
# ---------------------------------------------------------

# Design → Compliance loop: Iteratively refines the process 
# Note: This loop needs an exit_loop added to optimize termination,
# currently it relies on max_iterations and burns unnecessary tokens.

design_instance = LlmAgent(
    name=design_agent.name + '_Design_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

design_compliance_instance = LlmAgent(
    name=design_agent.name + '_Compliance_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

design_simulation_instance = LlmAgent(
    name=design_agent.name + '_Simulation_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

design_grounding_instance = LlmAgent(
    name=design_agent.name + '_Grounding_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

review_loop = LoopAgent(
    name="Design_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Design_Stage",
            sub_agents=[
                design_instance,
                compliance_agent,
                design_compliance_instance,
                simulation_agent,
                design_simulation_instance,
                grounding_agent,
                design_grounding_instance,
            ],
        ),
    ],
    max_iterations=getProperty("loopInterations")
)


# JSON Normalization → Review loop: Stabilizes the process JSON
json_normalization_loop = SequentialAgent(
    name="JSON_Normalization_Retry_Loop",
    sub_agents=[
        LoopAgent(
            name="Normalizer_Review_Sequence",
            sub_agents=[json_normalizer_agent, json_review_agent],
            max_iterations=getProperty("loopInterations") # The max iterations for this loop. Adjust as needed.
        ),
        json_writer_agent
    ],
)

# Build the full design pipeline
subprocess_stage = SubprocessDriverAgent(name="Subprocess_Driver_Agent_Create")

full_design_pipeline = SequentialAgent(
    name="Full_Design_Pipeline",
    description="Use this tool ONLY when the user wants to CREATE, DESIGN, or GENERATE a new business process from scratch.",
    sub_agents=[
        analysis_agent,          # Stage 1: Requirements
        review_loop,             # Stage 2: Design/Audit Loop
        json_normalization_loop, # Stage 3: Stabilization (writes process_data.json)
        subprocess_stage,        # Stage 4: Per-step subprocess generation (writes output/subprocesses/*.json)
        edge_inference_agent,    # Stage 5: Logical Flow
        doc_generation_agent     # Stage 6: Artifact Build
    ]
)


