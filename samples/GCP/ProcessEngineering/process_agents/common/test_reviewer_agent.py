# process_agents/common/test_reviewer_agent.py
#
# Audits the QUALITY of an EXISTING saved test specification (written by
# Test_Specification_Agent via save_test_specification) against classic
# test-case-quality criteria (ISO/IEC/IEEE 29119-style: clear
# preconditions, concrete steps, a specific verifiable expected result,
# genuine traceability, no duplication, honest coverage claims) -- on
# demand, standalone, same shape as Requirements_Reviewer_Agent (single
# load/update tool pair, no loop_control/iteration_feedback machinery).
# Deliberately NOT the CloudArch_Reviewer_Agent/Compliance_Agent pattern --
# this is not a pipeline-internal auto-revision gate, it is invoked only
# on the user's own explicit request to have the test specification
# itself audited (and, optionally, corrected).

import logging

logger = logging.getLogger("ProcessArchitect.TestReviewer")

from ..common.utils import load_test_specification, update_test_specification
from ..common.agent_wrappers import ProcessLlmAgent

test_reviewer_agent = ProcessLlmAgent(
    name="Test_Reviewer_Agent",
    description=(
        "Audits the QUALITY of the saved test specification -- not what it covers, but "
        "whether each test case is well-written: has concrete preconditions and steps, a "
        "specific verifiable expected result, and genuine traceability back to a real "
        "requirement/component. Flags vague, unverifiable, duplicate, or untraced test "
        "cases, and coverage claims that don't match the actual test cases, with specific "
        "feedback. By default read-only; if explicitly asked to review AND fix, applies "
        "only mechanical, well-grounded corrections and reports what changed."
    ),
    instruction_file="common/test_reviewer_agent.txt",
    tools=[load_test_specification, update_test_specification],
)
