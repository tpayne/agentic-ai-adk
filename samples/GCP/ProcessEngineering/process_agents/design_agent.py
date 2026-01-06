# process_agents/design_agent.py
from google.adk.agents import LlmAgent
from google.adk.tools.tool_context import ToolContext

import time
import logging
import random

from .utils import load_instruction

logger = logging.getLogger("ProcessArchitect.Design")

def exit_loop(tool_context: ToolContext):
    """
    Exit tool for the Design Agent:
    - Sets escalate to True to terminate the loop.
    - Logs the exit action for traceability.
    """
    time.sleep(0.5 + random.random() * 0.75)
    logger.info("Received ALL_APPROVED signal. Exiting design loop.")
    tool_context.actions.escalate = True
    return {}

# -----------------------------
# DESIGN AGENT
# -----------------------------
design_agent = LlmAgent(
    name="Design_Agent",
    model="gemini-2.0-flash-001",
    description="Architects detailed business process workflows.",
    instruction=load_instruction("design_agent.txt"),
    tools=[exit_loop],
    output_key="approved_json",
)
