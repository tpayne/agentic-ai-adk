# process_agents/json_review_agent.py

from google.genai import types
from google.adk.tools.tool_context import ToolContext

from .utils import (
    load_master_process_json,
    load_iteration_feedback,
    save_iteration_feedback,
    getProperty
)

import json
import logging
import time
import random

logger = logging.getLogger("ProcessArchitect.JsonReview")

def log_review_metadata(goal_count: int):
    """Internal tool to track extraction progress and CLEAN environment."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Review Metadata - Goals Identified: {goal_count}.")
    return f"JSON Review started with {goal_count} identified objectives."

def exit_loop(tool_context: ToolContext):
    """Signals that the JSON has been reviewed and approved."""
    logger.debug("JSON Review Approved. Terminating normalization loop.")
    tool_context.actions.escalate = True
    return "Normalization loop terminated."

# -----------------------------
# JSON REVIEW AGENT
# -----------------------------
from .agent_wrappers import ProcessLlmAgent
json_review_agent = ProcessLlmAgent(
    name='Json_Review_Agent',
    description='Review JSON for validity, compliance, and best practices.',
    include_contents="default",
    tools=[
        exit_loop,
        load_iteration_feedback,
        load_master_process_json,
        save_iteration_feedback,
        log_review_metadata
    ],
    instruction_file="json_review_agent.txt",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
