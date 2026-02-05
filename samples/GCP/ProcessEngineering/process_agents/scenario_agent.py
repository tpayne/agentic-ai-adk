# process_agents/scenario_agent.py
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

import time
import logging
import random

from .utils import (
    load_instruction,
    load_full_process_context,
    getProperty,
    review_messages,
    review_outputs
)

logger = logging.getLogger("ProcessArchitect.ScenarioTester")

# -----------------------------
# DESIGN AGENT
# -----------------------------
# Agent for interactive scenario testing
scenario_tester_agent = LlmAgent(
    name="Scenario_Tester",
    model=getProperty("MODEL"),
    description="Use this agent to test and simulate scenarios on EXISTING processes. It cannot create new processes.",
    instruction=load_instruction("scenario_tester_agent.txt"),
    tools=[load_full_process_context],
    before_model_callback=review_messages,
    after_model_callback=review_outputs
)