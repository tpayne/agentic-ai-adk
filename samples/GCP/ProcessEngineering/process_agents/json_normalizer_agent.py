from google.genai import types

from .utils import (
    load_master_process_json,
    persist_final_json,
    load_iteration_feedback,
    getProperty,
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
from .agent_wrappers import ProcessLlmAgent
json_normalizer_agent = ProcessLlmAgent(
    name="JSON_Normalizer_Agent",
    tools=[
        load_master_process_json,
        persist_final_json,
        load_iteration_feedback,
        log_normalization_metadata
    ],
    include_contents="default",
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction_file="json_normalizer_agent.txt",
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)