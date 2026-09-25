# process_agents/design_doc_hld_agent.py

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

logger = logging.getLogger("ProcessArchitect.DesignDocHLD")

# -----------------------------
# DESIGN DOC HLD AGENT
# -----------------------------
from ..common.agent_wrappers import ProcessLlmAgent

design_doc_hld_agent = ProcessLlmAgent(
    name="Design_Doc_HLD_Agent",
    description="Generates and revises High-Level Architecture (HLD) specifications.",
    instruction_file="design/design_doc_hld_agent.txt",
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