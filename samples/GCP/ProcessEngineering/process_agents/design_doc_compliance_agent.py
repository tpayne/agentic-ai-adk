# process_agents/design_doc_compliance_agent.py

import logging
import time
import random
from google.genai import types

from .utils import (
    load_master_design_json,
    save_iteration_feedback,
    getProperty,
)

logger = logging.getLogger("ProcessArchitect.DesignDocCompliance")

def log_compliance_metadata(status: str):
    """Internal tool to report status."""
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    logger.debug(f"Compliance Metadata - Status: {status}")
    return {}

# -----------------------------
# DESIGN DOC COMPLIANCE AGENT
# -----------------------------
from .agent_wrappers import ProcessLlmAgent

design_doc_compliance_agent = ProcessLlmAgent(
    name="Design_Doc_Compliance_Agent",
    description="Audits architectural design documents against ISO, C4/arc42, and security standards.",
    instruction_file="design_doc_compliance_agent.txt",
    tools=[
        load_master_design_json,
        save_iteration_feedback,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1.0,
    ),
)