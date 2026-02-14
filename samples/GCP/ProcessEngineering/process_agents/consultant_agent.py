# process_agents/consultant_agent.py
from google.adk.tools.tool_context import ToolContext

import time
import logging
import random

from .utils import (
    load_full_process_context,
)

logger = logging.getLogger("ProcessArchitect.Consultant")

# -----------------------------
# CONSULTANT AGENT
# -----------------------------
# Agent for providing expert advice on process design
from .agent_wrappers import ProcessLlmAgent
consultant_agent = ProcessLlmAgent(
    name="Consultant_Agent",
    description="Use this for questions about EXISTING processes. It cannot create new ones.",
    instruction_file="consultant_agent.txt",
    tools=[load_full_process_context],
)