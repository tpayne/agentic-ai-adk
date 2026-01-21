# process_agents/design_agent.py
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.genai import types

import time
import logging
import random

from .utils import (
    load_instruction,
    persist_final_json,
    load_iteration_feedback,
    load_master_process_json,
    getProperty
)

logger = logging.getLogger("ProcessArchitect.Design")

def log_design_metadata(process_name: str, goal_count: int):
    """Internal tool to track design progress."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Design Metadata - Process: {process_name}, Goals Identified: {goal_count}.")
    return f"Design started for {process_name} with {goal_count} identified objectives."

def exit_loop(tool_context: ToolContext):
    """
    Simplified for V2: The JSON is already saved via persist_final_json.
    This tool now ONLY signals the orchestrator to terminate.
    """
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug("Termination signal received. Exiting loop.")
    tool_context.actions.escalate = True
    return "Exit signaled. Loop terminating."

# -----------------------------
# DESIGN AGENT
# -----------------------------
design_agent = LlmAgent(
    name="Design_Agent",
    model="gemini-2.0-flash-001",
    description="Architects detailed business process workflows.",
    instruction=load_instruction("design_agent.txt"),
    tools=[
        exit_loop, 
        load_iteration_feedback,
        log_design_metadata,
        load_master_process_json,
        persist_final_json,
    ],
    output_key="approved_json",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
    ),
)
