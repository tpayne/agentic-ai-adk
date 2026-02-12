# utils_agent.py
import logging
from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext
import os
import time
import random
import json
import sys

from typing import Any

logger = logging.getLogger("ProcessArchitect.UtilsAgent")

from .utils import (
    load_instruction,
    getProperty,
    CleanedStdout
)

from .design_agent import design_agent

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

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

def status_logger(goal_count: int):
    """Internal tool to track progress."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"StopAgent - Logger Goals Identified: {goal_count}.")
    return f"Logging status with {goal_count} identified objectives."

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
    # --- Check for all three approvals OR JSON APPROVED ---
    required = {
        "compliance_status": "APPROVED",
        "simulation_status": "APPROVED",
    }

    if (getProperty("enableGroundingAgent", default="true")): 
        required["grounding_status"] = "APPROVED"

    if "JSON APPROVED" in approval_state.get("status", "").strip().upper():
        tool_context.actions.escalate = True
        logger.debug("status=JSON APPROVED detected — exiting loop.")
        return "status=JSON APPROVED detected — exiting loop."

    if any(approval_state.get(k) == "JSON APPROVED" for k in required.keys()):
        tool_context.actions.escalate = True
        logger.debug("One or more fields = JSON APPROVED — exiting loop.")
        return "JSON APPROVED detected — exiting loop."

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
    tools=[status_logger,stop_if_ready],
)

# ---------- Mute agent to consume injected context silently ----------
log_dir = "output/logs"
os.makedirs(log_dir, exist_ok=True)

from .utils import (
    ANSI_GREEN, 
    ANSI_RESET 
)

# Function to kill all console output
def silence_console():
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug("Silencing console output.")
    print(f"{ANSI_GREEN}- Starting process pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}. This will take some time...{ANSI_RESET}", end="\n")
    sys.stdout.flush()
    output_file = os.path.join(log_dir, "runtime_outputs.log")
    sys.stdout = CleanedStdout(output_file)
    return "Console output silenced."

def restore_console():
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug("Restoring console output.")
    sys.stdout = sys.__stdout__
    print(f"{ANSI_GREEN}- Finished process pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}...{ANSI_RESET}", end="\n")
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
