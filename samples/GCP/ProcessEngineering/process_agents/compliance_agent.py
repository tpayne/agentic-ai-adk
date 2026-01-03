# process_agents/compliance_agent.py
from google.adk.agents import LlmAgent
import logging

logger = logging.getLogger("ProcessArchitect.Compliance")

from .utils import load_instruction

compliance_agent = LlmAgent(
    name='Compliance_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Audits processes against sector best practices.',
    instruction=load_instruction("compliance_agent.txt"),
)
