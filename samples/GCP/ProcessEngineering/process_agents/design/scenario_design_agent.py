# process_agents/scenario_design_agent.py

import time
import logging
import random

from ..common.utils import (
    load_full_design_context,
)

logger = logging.getLogger("ProcessArchitect.DesignScenarioTester")

# -----------------------------
# DESIGN SCENARIO TESTER AGENT
# -----------------------------
# Agent for interactive what-if scenario testing against an EXISTING
# architectural design document (HLD/LLD/Combined). Mirrors
# scenario_agent.py's process-side Scenario_Tester exactly, pinned to the
# design schema via load_full_design_context instead of the
# auto-detecting load_full_process_context (same reasoning as
# consultant_design_agent.py).
from ..common.agent_wrappers import ProcessLlmAgent
design_scenario_tester_agent = ProcessLlmAgent(
    name="Design_Scenario_Tester",
    description="Use this agent to test and reason about what-if scenarios against an EXISTING architectural design document (HLD/LLD/Combined). It cannot create new designs.",
    instruction_file="design/design_scenario_tester_agent.txt",
    tools=[load_full_design_context],
)
