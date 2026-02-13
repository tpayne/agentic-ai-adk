# process_agents/create_process_agent.py

# Standard / third-party imports
from webbrowser import get
from google.adk.agents import LoopAgent, SequentialAgent  # core agent orchestrators
from google.adk.tools.tool_context import ToolContext
from google.genai import types
import time
import logging
import random
import os
import sys
import json
from typing import Any

# Import sub-agents (each is defined in sibling modules)
from .analysis_agent import analysis_agent
from .design_agent import design_agent as design_agent
from .compliance_agent import compliance_agent
from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .doc_creation_agent import build_doc_creation_agent
from .json_writer_agent import json_writer_agent
from .simulation_agent import simulation_agent
from .grounding_agent import grounding_agent
from .subprocess_driver_agent import SubprocessDriverAgent  # driver for subprocess generation
from .utils import (
    getProperty,
)
from .utils_agent import (
    mute_agent,
    unmute_agent,
    stop_controller_agent
)

# Wrapper classes that adapt LLM agents into the process pipeline
from .agent_wrappers import ProcessLlmAgent, ProcessAgent

logger = logging.getLogger("ProcessArchitect.CreateProcessPipeline")

# ------------------------- PIPELINE DEFINITION -------------------------
# Safe timebox for loops: read configurable value or fall back to a conservative default.
SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=6))

# ---------- Existing design agents ----------
# Create a ProcessLlmAgent wrapper instance for the design agent (keeps LLM-specific behaviour)
design_instance = ProcessLlmAgent(
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

# Create additional ProcessAgent instances used in various loop roles (compliance, simulation, grounding)
design_compliance_instance = ProcessAgent(
    name=design_agent.name + '_Compliance_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

design_simulation_instance = ProcessAgent(
    name=design_agent.name + '_Simulation_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
    before_model_callback=design_agent.before_model_callback,
    after_model_callback=design_agent.after_model_callback,
)

design_grounding_instance = ProcessAgent(
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
# Assemble sub-agents for the iterative design-compliance loop
sub_agents = [
    design_instance,
    compliance_agent,
    design_compliance_instance,
    simulation_agent,
    design_simulation_instance,
]

# Optionally include grounding agents based on configuration
if getProperty("enableGroundingAgent", default="true"):
    logger.debug("Grounding agent ENABLED in design loop.")
    sub_agents += [
        grounding_agent,
        design_grounding_instance,
    ]
else:
    logger.debug("Grounding agent DISABLED in design loop.")

# Always append the stop controller to allow early termination of the loop
sub_agents.append(stop_controller_agent)

# Define a looped stage that runs the design/compliance sequence up to SAFE_LOOP_ITERS times
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

# Wrap the stop controller as a ProcessAgent for use in other sequences (e.g., JSON review)
json_stop_agent = ProcessAgent(
    name="JSON_Review_Stop_Controller",
    model=stop_controller_agent.model,
    description=stop_controller_agent.description,
    instruction=stop_controller_agent.instruction,
    tools=stop_controller_agent.tools,
    output_key=stop_controller_agent.output_key,
    before_model_callback=stop_controller_agent.before_model_callback,
    after_model_callback=stop_controller_agent.after_model_callback,
)

# JSON Normalization pipeline: normalize, review (with stop), then write JSON output
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

# Build the full design pipeline: mute output, analysis, iterative design, normalization, subprocess generation, docs, unmute
subprocess_stage = SubprocessDriverAgent(name="Subprocess_Driver_Agent_Create")  # orchestrates per-step subprocess generation

full_design_pipeline = SequentialAgent(
    name="Full_Design_Pipeline",
    description="Use this tool ONLY when the user wants to CREATE, DESIGN, or GENERATE a new business process from scratch.",
    sub_agents=[
        mute_agent,              # Temporarily suppress noisy output during pipeline run
        analysis_agent,          # Stage 1: Requirements elicitation / analysis
        review_loop,             # Stage 2: Iterative design + compliance loop
        json_normalization_loop, # Stage 3: Stabilize and persist process JSON
        subprocess_stage,        # Stage 4: Generate per-step subprocess artifacts
        build_doc_creation_agent("Create"),  # Stage 5: Produce deliverables/documentation
        unmute_agent             # Restore console output
    ]
)