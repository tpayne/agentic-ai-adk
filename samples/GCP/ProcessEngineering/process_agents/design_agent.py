# process_agents/design_agent.py
from google.adk.agents import LlmAgent
import time
import logging

from .utils import load_instruction

logger = logging.getLogger("ProcessArchitect.Design")

# -----------------------------
# DESIGN AGENT
# -----------------------------
design_agent = LlmAgent(
    name="Design_Agent",
    model="gemini-2.0-flash-001",
    description="Architects detailed business process workflows.",
    instruction=load_instruction("design_agent.txt"),
)
