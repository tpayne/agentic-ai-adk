# process_agents/itsm/consultant_agent.py

from ..common.utils import (
    load_full_itsm_context,
    load_requirements_summary,
)
from ..common.agent_wrappers import ProcessLlmAgent

itsm_consultant_agent = ProcessLlmAgent(
    name="ITSM_Consultant_Agent",
    description=(
        "Use this for questions about an EXISTING ITSM process document -- incident/problem/change "
        "procedures, SLAs, the CMDB, RACI assignments, tooling. It cannot create or modify one."
    ),
    instruction_file="itsm/consultant_agent.txt",
    tools=[load_full_itsm_context, load_requirements_summary],
)
