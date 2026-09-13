# process_agents/design_doc_lld_agent.py

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

logger = logging.getLogger("ProcessArchitect.DesignDocLLD")

# -----------------------------
# DESIGN DOC LLD AGENT
# -----------------------------
from .agent_wrappers import ProcessLlmAgent

design_doc_lld_agent = ProcessLlmAgent(
    name="Design_Doc_LLD_Agent",
    description="Elaborates High-Level Architectures into granular Low-Level Design (LLD) specifications.",
    instruction_file="design_doc_lld_agent.txt",
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