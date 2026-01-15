# process_agents/json_writer_agent.py

import os
import re
import json
import logging
import traceback

from google.adk.agents import LlmAgent
from google.genai import types

from .utils import (
    load_instruction,
    load_master_process_json,
    load_iteration_feedback,
    persist_final_json
)

import time
import random  

logger = logging.getLogger("ProcessArchitect.JsonWriter")

# ---------------------------------------------------------------------
# AGENT DEFINITION (SINGLE TOOL, ATOMIC BEHAVIOR)
# ---------------------------------------------------------------------

json_writer_agent = LlmAgent(
    name="JSON_Writer_Agent",
    model="gemini-2.0-flash-001",
    description="Final persistence agent that writes approved JSON to the file system.",
    instruction=load_instruction("json_writer_agent.txt"),
    tools=[
        persist_final_json,
        load_master_process_json,
        load_iteration_feedback,
    ],  # Use the exposed tool only
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
