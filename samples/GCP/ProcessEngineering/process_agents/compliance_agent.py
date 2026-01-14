# process_agents/compliance_agent.py
from google.adk.agents import LlmAgent
from google.genai import types

import logging
import time
import random

logger = logging.getLogger("ProcessArchitect.Compliance")

from .utils import (
    load_instruction,
    load_master_process_json,
    save_iteration_feedback
)

def log_compliance_metadata(status: str):
    """Internal tool to report status."""
    time.sleep(1.75 + random.random() * 0.75)
    logger.info(f"Compliance Metadata - Status: {status},")
    return {}

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
        save_iteration_feedback,
        log_compliance_metadata,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
    output_key="compliance_report",
)
