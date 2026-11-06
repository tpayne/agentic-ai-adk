# process_agents/common/test_consultant_agent.py
#
# Narrative Q&A agent for an EXISTING saved test specification (written by
# Test_Specification_Agent via save_test_specification). Mirrors
# requirements_consultant_agent.py: a single-tool agent pinned to
# reloading its one source of truth every turn rather than trusting
# conversation memory.

import logging

logger = logging.getLogger("ProcessArchitect.ConsultantTestSpecification")

from ..common.utils import load_test_specification
from ..common.agent_wrappers import ProcessLlmAgent

test_consultant_agent = ProcessLlmAgent(
    name="Test_Consultant_Agent",
    description=(
        "Use this for questions about the saved/previous test specification -- its test "
        "cases, their traceability back to requirements/design/cloud-architecture "
        "components, coverage gaps, risks, and open questions. It cannot create or modify "
        "the requirements, design, cloud architecture, or the test specification itself."
    ),
    instruction_file="common/test_consultant_agent.txt",
    tools=[load_test_specification],
)
