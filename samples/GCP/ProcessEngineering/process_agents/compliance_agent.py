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
    load_iteration_feedback,
    save_iteration_feedback,
    getProperty,
    review_messages
)

def log_compliance_metadata(status: str):
    """Internal tool to report status."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Compliance Metadata - Status: {status},")
    return {}

# -----------------------------
# COMPLIANCE AGENT DEFINITION
# -----------------------------
compliance_agent = LlmAgent(
    name='Compliance_Review_Agent',
    model=getProperty("MODEL"),
    description='Audits processes against sector best practices.',
    instruction=load_instruction("compliance_agent.txt"),
    tools=[
        load_master_process_json,
        save_iteration_feedback,
        load_iteration_feedback,
        log_compliance_metadata,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
    before_model_callback=review_messages,
)
