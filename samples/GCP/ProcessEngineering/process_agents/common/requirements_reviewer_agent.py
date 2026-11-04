# process_agents/requirements_reviewer_agent.py
#
# Audits the QUALITY of an EXISTING saved requirements summary (written by
# Requirements_Summary_Agent via save_requirements_summary) against classic
# SRS/ISO-29148 "good requirement" criteria -- on demand, standalone, same
# shape as Requirements_Consultant_Agent (single audit tool plus
# update_requirements_summary -- see requirements_reviewer_agent.txt for
# the intent-gated rule on when it's actually allowed to call it rather
# than only report findings). Deliberately NOT the CloudArch_Reviewer_
# Agent/Compliance_Agent pattern -- this is not a pipeline-internal
# auto-revision gate, it is invoked only on the user's own explicit
# request to have the requirements themselves audited (and, optionally,
# corrected).

import logging

logger = logging.getLogger("ProcessArchitect.RequirementsReviewer")

from ..common.utils import load_requirements_summary, update_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

requirements_reviewer_agent = ProcessLlmAgent(
    name="Requirements_Reviewer_Agent",
    description=(
        "Audits the QUALITY of the saved requirements summary -- not what it says, but whether "
        "each requirement is well-written: necessary, unambiguous, complete, singular, feasible, "
        "verifiable, and consistent (ISO/IEC/IEEE 29148). Flags vague, compound, untestable, "
        "duplicate, or conflicting requirements with specific feedback. By default read-only; if "
        "explicitly asked to review AND fix, applies only mechanical, well-grounded corrections "
        "and reports what changed."
    ),
    instruction_file="common/requirements_reviewer_agent.txt",
    tools=[load_requirements_summary, update_requirements_summary],
)
