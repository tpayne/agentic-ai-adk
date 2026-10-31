# process_agents/proposal_response_agent.py
#
# Drafts a formal Response to Proposal against an ALREADY-saved
# requirements summary (an RFP/proposal's own analyzed requirements
# register, produced by a prior, separate Requirements_Summary_Agent
# run) plus the user's own description of their organization's
# solution/offering. This is Proposal_Response_Pipeline's own first
# stage -- its own save feeds directly into the pipeline's second stage
# (doc rendering), so this agent's visible output stays silent (see its
# own instruction file's OUTPUT CONTRACT), same as
# requirements_synthesis_agent.py within Requirements_Doc_Pipeline.

import logging

logger = logging.getLogger("ProcessArchitect.ProposalResponse")

from ..common.utils import load_requirements_summary, save_proposal_response
from ..common.agent_wrappers import ProcessLlmAgent

proposal_response_agent = ProcessLlmAgent(
    name="Proposal_Response_Agent",
    description=(
        "Drafts a formal Response to Proposal against an already-saved requirements summary "
        "(an RFP/proposal's own analyzed requirements register) plus a description of the "
        "responding organization's solution/offering, and saves it for the pipeline's own next "
        "stage to render as a document."
    ),
    instruction_file="common/proposal_response_agent.txt",
    tools=[load_requirements_summary, save_proposal_response],
)
