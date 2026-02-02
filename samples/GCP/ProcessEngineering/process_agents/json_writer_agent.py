# process_agents/json_writer_agent.py

import os
import re
import json
import logging
import traceback

from google.adk.agents import Agent

from .utils import (
    load_instruction,
    load_master_process_json,
    load_iteration_feedback,
    persist_final_json,
    review_messages
)

import time
import random

logger = logging.getLogger("ProcessArchitect.JsonWriter")

# ---------------------------------------------------------------------
# AGENT DEFINITION (DETERMINISTIC UTILITY AGENT)
# ---------------------------------------------------------------------

json_writer_agent = Agent(
    name="JSON_Writer_Agent",
    description="Final persistence agent that writes approved JSON to the file system.",
    instruction=load_instruction("json_writer_agent.txt"),
    tools=[
        persist_final_json,
        load_master_process_json,
        load_iteration_feedback,
    ],
    before_model_callback=review_messages,
)

