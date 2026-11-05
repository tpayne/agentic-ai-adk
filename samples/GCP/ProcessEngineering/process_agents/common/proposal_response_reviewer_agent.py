# process_agents/proposal_response_reviewer_agent.py
#
# Audits the QUALITY of an EXISTING saved proposal response (written by
# Proposal_Response_Agent via save_proposal_response) -- on demand,
# standalone, same shape as Requirements_Reviewer_Agent. Also carries
# update_proposal_response so that, when the user's own request signals
# they want fixes applied (not just a report), it can apply targeted,
# well-grounded corrections and say exactly what changed -- see
# proposal_response_reviewer_agent.txt for the intent-gated rule.

import logging

logger = logging.getLogger("ProcessArchitect.ProposalResponseReviewer")

from ..common.utils import load_proposal_response, update_proposal_response
from ..common.agent_wrappers import ProcessLlmAgent

proposal_response_reviewer_agent = ProcessLlmAgent(
    name="Proposal_Response_Reviewer_Agent",
    description=(
        "Audits the QUALITY of the saved proposal response -- whether each compliance_matrix "
        "entry's claimed status matches the honesty of its own response text, whether sections "
        "are genuinely populated rather than thin placeholders, and whether anything reads as "
        "potentially fabricated (invented figures, certifications, or case studies). Flags "
        "issues with specific, actionable feedback. By default read-only; if explicitly asked to "
        "review AND fix, applies only mechanical, well-grounded corrections and reports what "
        "changed."
    ),
    instruction_file="common/proposal_response_reviewer_agent.txt",
    tools=[load_proposal_response, update_proposal_response],
)
