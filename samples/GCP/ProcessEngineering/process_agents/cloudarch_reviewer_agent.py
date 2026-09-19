# process_agents/cloudarch_reviewer_agent.py
from google.genai import types

import logging
import time
import random

logger = logging.getLogger("ProcessArchitect.CloudArchReviewer")

from .utils import (
    load_master_process_json,
    load_drawio,
    getProperty,
    save_iteration_feedback,
)

def log_cloudarch_reviewer_metadata(status: str):
    """Internal tool to report status."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"CloudArch Reviewer Metadata - Status: {status},")
    return {}

# -----------------------------
# CLOUDARCH REVIEWER AGENT DEFINITION
# -----------------------------
from .agent_wrappers import ProcessLlmAgent
cloudarch_reviewer_agent = ProcessLlmAgent(
    name='CloudArch_Reviewer_Agent',
    description='Reviews a generated cloud architecture against security, cost, observability, and resiliency best practices, and returns feedback for the CloudArch Agent to apply.',
    instruction_file="cloudarch_reviewer_agent.txt",
    tools=[
        load_master_process_json,
        load_drawio,
        log_cloudarch_reviewer_metadata,
        save_iteration_feedback,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
)
