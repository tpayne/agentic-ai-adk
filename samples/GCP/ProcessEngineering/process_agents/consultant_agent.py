# process_agents/consultant_agent.py
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

import time
import logging
import random

from .utils import (
    load_instruction,
    load_full_process_context,
    getProperty,
    review_messages
)

logger = logging.getLogger("ProcessArchitect.Consultant")

# -----------------------------
# CONSULTANT AGENT
# -----------------------------
# Agent for providing expert advice on process design
consultant_agent = LlmAgent(
    name="Consultant_Agent",
    description="Use this for questions about EXISTING processes. It cannot create new ones.",
    model=getProperty("MODEL"),
    instruction=load_instruction("consultant_agent.txt"),
    output_key="consultant_advice",
    tools=[load_full_process_context],
    before_model_callback=review_messages,
)