# process_agents/create_process_agent.py
from webbrowser import get
from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent, Agent
from google.adk.tools.tool_context import ToolContext
from google.genai import types
import time
import logging
import random
import os
import sys
import json
from typing import Any

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

from .utils import (
    getProperty, 
    load_instruction,
)

from .utils_agent import (
    mute_agent, 
    unmute_agent, 
    stop_controller_agent
)

logger = logging.getLogger("ProcessArchitect.CreateProcessPipeline")

# ------------------------- PIPELINE DEFINITION -------------------------

# Safe timebox for loops (correct key + default)
SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=6))

# ---------- Existing design agents ----------
design_instance = LlmAgent(
    name=design_agent.name + '_Design_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    generate_content_config=design_agent.generate_content_config,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

design_compliance_instance = Agent(
    name=design_agent.name + '_Compliance_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

design_simulation_instance = Agent(
    name=design_agent.name + '_Simulation_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

design_grounding_instance = Agent(
    name=design_agent.name + '_Grounding_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
) 


# ---------- Add Stop_Controller FIRST in the loop stage ----------

sub_agents = [
    design_instance,
    compliance_agent,
    design_compliance_instance,
    simulation_agent,
    design_simulation_instance,
]

if getProperty("enableGroundingAgent", default="true"):
    sub_agents += [
        grounding_agent,
        design_grounding_instance,
    ]

sub_agents.append(stop_controller_agent)

review_loop = LoopAgent(
    name="Design_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Design_Stage",
            sub_agents=sub_agents,
        ),
    ],
    max_iterations=SAFE_LOOP_ITERS
)

json_stop_agent = Agent(
    name="JSON_Review_Stop_Controller",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# JSON Normalization → Review loop
json_normalization_loop = SequentialAgent(
    name="JSON_Normalization_Retry_Loop",
    sub_agents=[
        LoopAgent(
            name="Normalizer_Review_Sequence",
            sub_agents=[json_normalizer_agent, json_review_agent, json_stop_agent],
            max_iterations=SAFE_LOOP_ITERS
        ),
        json_writer_agent
    ],
)

# Build the full design pipeline
subprocess_stage = SubprocessDriverAgent(name="Subprocess_Driver_Agent_Create")

# ---------- FIXED: correct variable name (no line break) ----------
full_design_pipeline = SequentialAgent(
    name="Full_Design_Pipeline",
    description="Use this tool ONLY when the user wants to CREATE, DESIGN, or GENERATE a new business process from scratch.",
    sub_agents=[
        mute_agent,                # Mute console output
        analysis_agent,            # Stage 1: Requirements
        review_loop,               # Stage 2: Design/Audit Loop
        json_normalization_loop,   # Stage 3: Stabilization (writes process_data.json)
        subprocess_stage,          # Stage 4: Per-step subprocess generation (writes output/subprocesses/*.json)
        edge_inference_agent,      # Stage 5: Logical Flow
        doc_generation_agent,      # Stage 6: Artifact Build
        unmute_agent               # Restore console output
    ]
)