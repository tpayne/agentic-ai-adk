# process_agents/compliance_agent.py
from google.genai import types

import logging
import time
import random
import os

logger = logging.getLogger("ProcessArchitect.CloudArch")

from .utils import (
    load_master_process_json,
    getProperty,
    save_drawio
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def log_cloudarch_metadata(status: str):
    """Internal tool to report status."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"CloudArch Metadata - Status: {status},")
    return {}

# -----------------------------
# CLOUDARCH AGENT DEFINITION
# -----------------------------
from .agent_wrappers import ProcessLlmAgent
cloudarch_agent = ProcessLlmAgent(
    name='CloudArch_Agent',
    description='Audits processes against sector best practices.',
    instruction_file="cloudarch_agent.txt",
    tools=[
        load_master_process_json,
        log_cloudarch_metadata,
        save_drawio
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
