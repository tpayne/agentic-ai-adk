# process_agents/create_process_agent.py
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

logger = logging.getLogger("ProcessArchitect.CreateProcessPipeline")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ------------------------- PIPELINE DEFINITION -------------------------

# Safe timebox for loops (correct key + default)
SAFE_LOOP_ITERS = int(getProperty("loopIterations", default=6))

# ---------- Programmatic stop/kill-switch tool ----------
def _contains_marker(obj: Any, needle: str) -> bool:
    """Recursive search for case-insensitive needle in dict/list/str."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    if obj is None:
        return False
    if isinstance(obj, str):
        return needle.lower() in obj.lower()
    if isinstance(obj, dict):
        return any(_contains_marker(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_marker(x, needle) for x in obj)
    return False

def stop_if_ready(tool_context: ToolContext):
    """
    Hard stop if either:
      - loopHardStop property is "true"/"1"/"on"; OR
      - approval.json indicates all three approvals:
            compliance_status = APPROVED
            simulation_status = APPROVED
            grounding_status = APPROVED
    """

    # --- Hard stop override ---
    logger.debug("Evaluating stop_if_ready conditions.")
    hard_stop = str(getProperty("loopHardStop", default=False)).lower() in ("1", "true", "yes", "on")
    if hard_stop:
        tool_context.actions.escalate = True
        return "loopHardStop activated — exiting loop."

    # --- Load cumulative approval state ---
    approval_path = os.path.join(PROJECT_ROOT, "output", "approval.json")
    approval_state = {}

    if os.path.exists(approval_path):
        try:
            with open(approval_path, "r", encoding="utf-8") as f:
                approval_state = json.load(f)
        except Exception:
            approval_state = {}

    logger.debug(f"Current approval state: {approval_state}")
    # --- Check for all three approvals ---
    required = {
        "compliance_status": "APPROVED",
        "simulation_status": "APPROVED",
        "grounding_status": "APPROVED",
    }

    if all(approval_state.get(k) == v for k, v in required.items()):
        tool_context.actions.escalate = True
        logger.debug("All approvals present — exiting loop.")
        return "All approvals present — exiting loop."

    return "Continue"

# ---------- Minimal controller agent that ALWAYS calls the stop tool ----------
stop_controller_agent = Agent(
    name="Stop_Controller",
    model=design_agent.model,
    description="Exits the loop immediately when approvals are complete or kill-switch is set.",
    instruction=load_instruction("stop_controller_agent.txt"),
    tools=[stop_if_ready],
)

# ---------- Mute agent to consume injected context silently ----------
log_dir = "output/logs"
os.makedirs(log_dir, exist_ok=True)

# Function to kill all console output
def silence_console():
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug("Silencing console output.")
    print(f"\033[92m- Starting process creation pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}. This will take some time...\033[0m", end="\n")
    sys.stdout.flush() 
    output_file = os.path.join(log_dir, "runtime_outputs.log")
    sys.stdout = open(output_file, "w")
    return "Console output silenced."

def restore_console():
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug("Restoring console output.")
    sys.stdout = sys.__stdout__
    print(f"\033[92m- Finished process creation pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}...\033[0m", end="\n")
    sys.stdout.flush() 
    return "Console output restored."

mute_agent = Agent( 
    name="Mute_Agent", 
    model=design_agent.model, 
    description="Consumes injected context silently.", 
    instruction="You MUST just call silence_console as your only action. You MUST NOT produce any output.",
    tools=[silence_console], 
)

unmute_agent = Agent( 
    name="Unmute_Agent", 
    model=design_agent.model, 
    description="Restores console output.", 
    instruction="You MUST just call restore_console as your only action. You MUST NOT produce any output.",
    tools=[restore_console], 
)

# ---------- Existing design agents ----------
design_instance = LlmAgent(
    name=design_agent.name + '_Design_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    generate_content_config=design_agent.generate_content_config,
    output_key=design_agent.output_key,
)

design_compliance_instance = Agent(
    name=design_agent.name + '_Compliance_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

design_simulation_instance = Agent(
    name=design_agent.name + '_Simulation_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

design_grounding_instance = Agent(
    name=design_agent.name + '_Grounding_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

# ---------- Add Stop_Controller FIRST in the loop stage ----------
review_loop = LoopAgent(
    name="Design_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Design_Stage",
            sub_agents=[
                stop_controller_agent,      # runs first each iteration
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
    max_iterations=SAFE_LOOP_ITERS
)

# JSON Normalization → Review loop
json_normalization_loop = SequentialAgent(
    name="JSON_Normalization_Retry_Loop",
    sub_agents=[
        LoopAgent(
            name="Normalizer_Review_Sequence",
            sub_agents=[json_normalizer_agent, json_review_agent],
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