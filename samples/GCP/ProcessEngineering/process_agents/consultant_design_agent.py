# process_agents/consultant_design_agent.py
from google.adk.tools.tool_context import ToolContext

import time
import logging
import random

from .utils import (
    load_full_design_context,
)

logger = logging.getLogger("ProcessArchitect.ConsultantDesign")

# -----------------------------
# DESIGN CONSULTANT AGENT
# -----------------------------
# Agent for providing expert advice on an EXISTING architectural design
# document (HLD/LLD/Combined). Pinned to the design schema via
# load_full_design_context (schema_type="design") rather than the
# auto-detecting load_full_process_context, since auto-detection prefers
# "process" whenever both a process_data.json and a design_data.json
# happen to exist on disk at the same time -- this agent must never
# silently answer from the wrong document.
from .agent_wrappers import ProcessLlmAgent
consultant_design_agent = ProcessLlmAgent(
    name="Design_Consultant_Agent",
    description="Use this for questions about an EXISTING architectural design document (HLD/LLD/Combined). It cannot create new ones.",
    instruction_file="consultant_design_agent.txt",
    tools=[load_full_design_context],
)
