# process_agents/json_review_agent.py
from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

from .utils import (
    load_instruction,
    load_master_process_json,
    save_iteration_feedback,
)

import json
import logging
import time
import random

logger = logging.getLogger("ProcessArchitect.JsonReview")

def exit_loop(tool_context: ToolContext):
    """Signals that the JSON has been reviewed and approved."""
    logger.info("JSON Review Approved. Terminating normalization loop.")
    tool_context.actions.escalate = True
    return "Normalization loop terminated."

# -----------------------------
# JSON REVIEW AGENT
# -----------------------------
json_review_agent = LlmAgent(
    name='Json_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Review JSON for validity, compliance, and best practices.',
    include_contents="default",
    output_key="approved_json",
    tools=[
        exit_loop,
        load_master_process_json,
        save_iteration_feedback
    ],
    instruction=load_instruction("json_review_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
)
