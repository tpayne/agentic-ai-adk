# process_agents/design_doc_hld_agent.py

import time
import logging
import random
from google.genai import types

from .utils import (
    log_design_metadata,
    load_master_process_json,
    load_iteration_feedback,
    load_process_template,
    validate_process_json,
    persist_final_json,
    getProperty,
)

logger = logging.getLogger("ProcessArchitect.DesignDocHLD")

# -----------------------------
# DESIGN DOC HLD AGENT
# -----------------------------
from .agent_wrappers import ProcessLlmAgent

design_doc_hld_agent = ProcessLlmAgent(
    name="Design_Doc_HLD_Agent",
    description="Generates and revises High-Level Architecture (HLD) specifications.",
    instruction_file="design_doc_hld_agent.txt",
    tools=[
        log_design_metadata,
        load_master_process_json,
        load_iteration_feedback,
        load_process_template,
        validate_process_json,
        persist_final_json,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
    ),
)