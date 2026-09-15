# process_agents/design_doc_agent.py

import time
import logging
import random
from google.genai import types

from .utils import (
    log_design_metadata,
    load_master_design_json,
    load_iteration_feedback,
    load_design_template,
    validate_design_json,
    persist_final_design_json,
    getProperty,
)

logger = logging.getLogger("ProcessArchitect.DesignDoc")

# -----------------------------
# DESIGN DOC AGENT (COMBINED)
# -----------------------------
from .agent_wrappers import ProcessLlmAgent

design_doc_agent = ProcessLlmAgent(
    name="Design_Doc_Agent",
    description="Generates complete, end-to-end unified (HLD + LLD) Architectural Design Documents.",
    instruction_file="design_doc_agent.txt",
    tools=[
        log_design_metadata,
        load_master_design_json,
        load_iteration_feedback,
        load_design_template,
        validate_design_json,
        persist_final_design_json,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
    ),
)