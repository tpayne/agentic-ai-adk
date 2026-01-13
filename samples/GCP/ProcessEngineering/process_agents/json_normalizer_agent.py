from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

from .utils import (
    load_instruction,
    load_master_process_json,
    persist_final_json,
    load_iteration_feedback
)

import json
import logging
from typing import Any

import time
import random 

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

# -----------------------------
# JSON NORMALIZER AGENT
# -----------------------------
json_normalizer_agent = LlmAgent(
    name="JSON_Normalizer_Agent",
    model="gemini-2.0-flash-001",
    tools=[
        load_master_process_json,
        persist_final_json,
        load_iteration_feedback
    ],
    include_contents="default",
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction=load_instruction("json_normalizer_agent.txt"),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
        # max_output_tokens=8192,
    ),
    output_key="approved_json",
)