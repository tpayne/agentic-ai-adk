# process_agents/requirements_consultant_agent.py
#
# Narrative Q&A agent for an EXISTING saved requirements summary (written by
# Requirements_Summary_Agent via save_requirements_summary). Mirrors
# consultant_agent.py (process) / cloudarch_consultant_agent.py (diagram):
# a single-tool agent pinned to reloading its one source of truth every turn
# rather than trusting conversation memory, since ADK's context-cache/
# compaction can summarize away the exact JSON content in a long session.

import logging

logger = logging.getLogger("ProcessArchitect.ConsultantRequirements")

from ..common.utils import load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

requirements_consultant_agent = ProcessLlmAgent(
    name="Requirements_Consultant_Agent",
    description=(
        "Use this for questions about the saved/previous requirements summary "
        "(from file-based requirements extraction) -- including any flagged "
        "conflicting requirements, requirements needing clarification, or "
        "requirement priorities. It cannot create or modify a process, "
        "design document, or cloud architecture."
    ),
    instruction_file="common/requirements_consultant_agent.txt",
    tools=[load_requirements_summary],
)
