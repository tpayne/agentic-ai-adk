from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

from .utils import (
    load_instruction,
    load_master_process_json,
    persist_final_json,
    load_iteration_feedback,
    getProperty,
    review_messages,
    review_outputs
)

import json
import logging
from typing import Any

import time
import random 

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

def log_normalization_metadata(goal_count: int):
    """Internal tool to track extraction progress and CLEAN environment."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Normalization Metadata - Goals Identified: {goal_count}.")
    return f"JSON Normalization started with {goal_count} identified objectives."

# -----------------------------
# JSON NORMALIZER AGENT
# -----------------------------
json_normalizer_agent = LlmAgent(
    name="JSON_Normalizer_Agent",
    model=getProperty("MODEL"),
    tools=[
        load_master_process_json,
        persist_final_json,
        load_iteration_feedback,
        log_normalization_metadata
    ],
    include_contents="default",
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction=load_instruction("json_normalizer_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
    before_model_callback=review_messages,
    after_model_callback=review_outputs
)