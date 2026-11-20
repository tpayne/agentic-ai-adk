"""Developed in tandem with samples/Neurosan/ProcessEngineering's own TOGAF_Consultant_Agent
(registries/togaf_consultant.hocon). Mirrors itsm/consultant_agent.py's own dual-mode (GENERAL vs
SPECIFIC) shape exactly -- built in from the start here, since TOGAF never had its own consultant
agent at all before this."""

from ..common.utils import load_full_togaf_context, load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

togaf_consultant_agent = ProcessLlmAgent(
    name="TOGAF_Consultant_Agent",
    description=(
        "Use this for questions about an EXISTING TOGAF architecture artifact set -- architecture "
        "vision, business/data/application/technology architecture, opportunities and solutions, "
        "migration planning, compliance -- or general TOGAF/enterprise-architecture questions that "
        "need no saved artifact set at all. It cannot create or modify a TOGAF artifact set."
    ),
    instruction_file="common/togaf_consultant_agent.txt",
    tools=[load_full_togaf_context, load_requirements_summary],
)
