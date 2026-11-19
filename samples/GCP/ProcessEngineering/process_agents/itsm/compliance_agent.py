# process_agents/itsm/compliance_agent.py
#
# Audits the current ITSM process document for naming hygiene,
# anti-fabrication, RACI coverage, and structural completeness. Mirrors
# togaf_compliance_agent.py's own minimal shape.

from ..common.utils import load_master_itsm_json, save_iteration_feedback
from ..common.agent_wrappers import ProcessLlmAgent

itsm_compliance_agent = ProcessLlmAgent(
    name="ITSM_Compliance_Agent",
    description=(
        "Audits the current ITSM process document for naming hygiene, anti-fabrication, RACI "
        "coverage, and structural completeness."
    ),
    instruction_file="itsm/compliance_agent.txt",
    tools=[
        load_master_itsm_json,
        save_iteration_feedback,
    ],
)
