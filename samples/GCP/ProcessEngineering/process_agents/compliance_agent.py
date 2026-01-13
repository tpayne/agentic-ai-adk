# process_agents/compliance_agent.py
from google.adk.agents import LlmAgent
from google.genai import types

import logging

logger = logging.getLogger("ProcessArchitect.Compliance")

from .utils import (
    load_instruction,
    load_master_process_json,
    save_iteration_feedback
)

# -----------------------------
# COMPLIANCE AGENT DEFINITION
# -----------------------------
compliance_agent = LlmAgent(
    name='Compliance_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Audits processes against sector best practices.',
    instruction=load_instruction("compliance_agent.txt"),
    tools=[
        load_master_process_json,
        save_iteration_feedback
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
    output_key="compliance_report",
)
