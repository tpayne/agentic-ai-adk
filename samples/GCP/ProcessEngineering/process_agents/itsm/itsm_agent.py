# process_agents/itsm/itsm_agent.py
#
# Builds or revises the ITSM process document JSON from extracted
# requirements and any review feedback -- structurally matching
# itsm_data.json's own schema. Mirrors togaf_agent.py's zero-custom-tool
# shape (no log_design_metadata-style helper needed).

from google.genai import types

from ..common.utils import (
    load_iteration_feedback,
    load_master_itsm_json,
    validate_itsm_json,
    persist_final_itsm_json,
)
from ..common.agent_wrappers import ProcessLlmAgent

itsm_agent = ProcessLlmAgent(
    name="ITSM_Agent",
    description=(
        "Builds a production-ready ITSM process document (service catalog, incident/problem/change "
        "management, request fulfillment, service level management, a light CMDB, and RACI "
        "governance) from extracted requirements, or applies review feedback on a revision pass."
    ),
    instruction_file="itsm/itsm_agent.txt",
    tools=[
        load_master_itsm_json,
        load_iteration_feedback,
        validate_itsm_json,
        persist_final_itsm_json,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2
    ),
)
