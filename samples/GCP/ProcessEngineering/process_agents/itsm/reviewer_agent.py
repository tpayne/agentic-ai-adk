# process_agents/itsm/reviewer_agent.py
#
# Audits the QUALITY of an EXISTING saved ITSM process document (vague
# RACI entries, missing SLA targets, unverifiable escalation paths,
# incomplete process steps) -- on demand, standalone, same shape as
# requirements_reviewer_agent.py (single audit tool plus persist -- see
# itsm_reviewer_agent.txt for the intent-gated rule on when it's actually
# allowed to call persist_final_itsm_json rather than only report
# findings). Deliberately NOT ITSM_Compliance_Agent's pipeline-internal
# auto-revision gate -- this is invoked only on the user's own explicit
# request to have the saved document itself audited (and, optionally,
# corrected).

from ..common.utils import (
    load_master_itsm_json,
    validate_itsm_json,
    persist_final_itsm_json,
)
from ..common.agent_wrappers import ProcessLlmAgent

itsm_reviewer_agent = ProcessLlmAgent(
    name="ITSM_Reviewer_Agent",
    description=(
        "Audits the QUALITY of the saved ITSM process document -- vague RACI entries, missing SLA "
        "targets, unverifiable escalation paths, incomplete process steps, missing change approval "
        "paths. By default read-only; if explicitly asked to review AND fix, applies only "
        "mechanical, well-grounded corrections and reports what changed."
    ),
    instruction_file="itsm/reviewer_agent.txt",
    tools=[load_master_itsm_json, validate_itsm_json, persist_final_itsm_json],
)
