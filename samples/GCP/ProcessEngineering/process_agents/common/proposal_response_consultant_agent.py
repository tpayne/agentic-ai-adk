# process_agents/proposal_response_consultant_agent.py
#
# Narrative Q&A agent for an EXISTING saved proposal response (written by
# Proposal_Response_Agent via save_proposal_response). Mirrors
# requirements_consultant_agent.py exactly: a single-tool agent pinned to
# reloading its one source of truth every turn rather than trusting
# conversation memory.

import logging

logger = logging.getLogger("ProcessArchitect.ConsultantProposalResponse")

from ..common.utils import load_proposal_response
from ..common.agent_wrappers import ProcessLlmAgent

proposal_response_consultant_agent = ProcessLlmAgent(
    name="Proposal_Response_Consultant_Agent",
    description=(
        "Use this for questions about the saved/previous proposal response -- its compliance "
        "matrix, pricing, delivery approach, case studies, or any other section. It cannot "
        "create or modify a proposal response, process, design document, or cloud architecture."
    ),
    instruction_file="common/proposal_response_consultant_agent.txt",
    tools=[load_proposal_response],
)
