# process_agents/ensure_requirements_summary_agent.py
#
# First stage of Proposal_Response_Pipeline: makes sure a requirements
# summary is saved before Proposal_Response_Agent tries to draft against
# one. SequentialAgent stages can't conditionally skip themselves, so
# this stage's own instructions do the branching instead: if a summary
# is already saved, it silently no-ops (same OUTPUT CONTRACT convention
# as requirements_synthesis_agent.py); if not, and the user's request
# already named a directory of RFP/proposal files, it reads and
# extracts one itself (reusing Requirements_Summary_Agent's own
# grounded-extraction discipline) instead of making the user run a
# separate request first; if neither, it asks for one and stops.

from google.adk.tools import AgentTool

from ..common.utils import load_directory_context, save_requirements_summary, load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent
from ..common.requirements_chunk_extractor_agent import requirements_chunk_extractor_agent

ensure_requirements_summary_agent = ProcessLlmAgent(
    name="Ensure_Requirements_Summary_Agent",
    description=(
        "Internal pipeline stage: ensures a requirements summary is saved before "
        "Proposal_Response_Agent drafts against one, reading the RFP/proposal's own files "
        "itself if the request already named a directory and none is saved yet."
    ),
    instruction_file="common/ensure_requirements_summary_agent.txt",
    tools=[
        load_requirements_summary,
        load_directory_context,
        save_requirements_summary,
        AgentTool(requirements_chunk_extractor_agent),
    ],
)
