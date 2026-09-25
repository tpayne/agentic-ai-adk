# process_agents/design_doc_lld_agent.py

import time
import logging
import random
from google.genai import types

from ..common.utils import (
    log_design_metadata,
    load_master_design_json,
    load_iteration_feedback,
    load_design_template,
    validate_design_json,
    persist_final_design_json,
    getProperty,
)

logger = logging.getLogger("ProcessArchitect.DesignDocLLD")

# -----------------------------
# DESIGN DOC LLD AGENT
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent

design_doc_lld_agent = ProcessLlmAgent(
    name="Design_Doc_LLD_Agent",
    description="Elaborates High-Level Architectures into granular Low-Level Design (LLD) specifications.",
    instruction_file="design/design_doc_lld_agent.txt",
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