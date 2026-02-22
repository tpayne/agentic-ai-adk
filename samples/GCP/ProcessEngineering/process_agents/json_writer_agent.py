# process_agents/json_writer_agent.py

import os
import re
import json
import logging
import traceback

from .utils import (
    load_master_process_json,
    load_iteration_feedback,
    persist_final_json,
)

import time
import random

logger = logging.getLogger("ProcessArchitect.JsonWriter")

# ---------------------------------------------------------------------
# AGENT DEFINITION (DETERMINISTIC UTILITY AGENT)
# ---------------------------------------------------------------------
from .agent_wrappers import ProcessAgent
json_writer_agent = ProcessAgent(
    name="JSON_Writer_Agent",
    description="Final persistence agent that writes approved JSON to the file system.",
    instruction_file="json_writer_agent.txt",
    tools=[
        persist_final_json,
        load_master_process_json,
        load_iteration_feedback,
    ],
)

