"""Builds or updates a TOGAF architecture artifact set from saved design or requirements JSON."""

from ..common.utils import (
    load_full_design_context,
    load_iteration_feedback,
    load_master_togaf_json,
    load_requirements_summary,
    persist_final_togaf_json,
)
from ..common.agent_wrappers import ProcessLlmAgent

togaf_agent = ProcessLlmAgent(
    name="TOGAF_Agent",
    description=(
        "Builds a new TOGAF architecture artifact set (Architecture Vision + Architecture "
        "Definition content) from the saved design document or, if none exists, the saved "
        "requirements summary, or applies explicit user-requested changes to an existing one, "
        "audited by TOGAF_Compliance_Agent before being finalized."
    ),
    instruction_file="common/togaf_agent.txt",
    tools=[
        load_master_togaf_json,
        load_requirements_summary,
        load_full_design_context,
        load_iteration_feedback,
        persist_final_togaf_json,
    ],
)
