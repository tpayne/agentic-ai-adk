"""Audits the current TOGAF architecture artifact set for traceability, groundedness, and naming hygiene."""

from ..common.utils import load_master_togaf_json, save_iteration_feedback
from ..common.agent_wrappers import ProcessLlmAgent

togaf_compliance_agent = ProcessLlmAgent(
    name="TOGAF_Compliance_Agent",
    description=(
        "Audits the current TOGAF architecture artifact set for traceability-chain integrity, "
        "grounded gaps, migration-planning anti-fabrication, and document-metadata naming hygiene."
    ),
    instruction_file="common/togaf_compliance_agent.txt",
    tools=[
        load_master_togaf_json,
        save_iteration_feedback,
    ],
)
