# process_agents/scenario_agent.py

import time
import logging
import random

from ..common.utils import (
    load_full_process_context,
)

logger = logging.getLogger("ProcessArchitect.ScenarioTester")

# -----------------------------
# DESIGN AGENT
# -----------------------------
# Agent for interactive scenario testing
from ..common.agent_wrappers import ProcessLlmAgent
scenario_tester_agent = ProcessLlmAgent(
    name="Scenario_Tester",
    description="Use this agent to test and simulate scenarios on EXISTING processes. It cannot create new processes.",
    instruction_file="process/scenario_tester_agent.txt",
    tools=[load_full_process_context],
)