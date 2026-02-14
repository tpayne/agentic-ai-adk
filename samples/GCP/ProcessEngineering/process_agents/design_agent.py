# process_agents/design_agent.py
from google.genai import types

import time
import logging
import random

from .utils import (
    persist_final_json,
    load_iteration_feedback,
    load_master_process_json,
    getProperty,
)

logger = logging.getLogger("ProcessArchitect.Design")

def log_design_metadata(process_name: str, goal_count: int):
    """Internal tool to track design progress."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Design Metadata - Process: {process_name}, Goals Identified: {goal_count}.")
    return f"Design started for {process_name} with {goal_count} identified objectives."

# -----------------------------
# DESIGN AGENT
# -----------------------------
from .agent_wrappers import ProcessLlmAgent
design_agent = ProcessLlmAgent(
    name="Design_Agent",
    description="Architects detailed business process workflows.",
    instruction_file="design_agent.txt",
    tools=[
        load_iteration_feedback,
        log_design_metadata,
        load_master_process_json,
        persist_final_json,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2
    ),
)
