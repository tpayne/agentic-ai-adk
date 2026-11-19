# process_agents/itsm/scenario_agent.py
#
# Standalone, load-only agent for interactive what-if scenario testing
# against an EXISTING ITSM process document. Mirrors
# togaf_scenario_tester_agent.py's own shape exactly: no save/persist tool
# exists anywhere on this agent -- a structural guarantee against
# mutation, not a convention enforced by instructions.

from ..common.utils import load_full_itsm_context, load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

itsm_scenario_tester_agent = ProcessLlmAgent(
    name="ITSM_Scenario_Tester",
    description=(
        "Use this agent to test and reason about what-if scenarios against an EXISTING ITSM process "
        "document, tracing its real RACI/escalation/CI dependency links. It cannot create or modify "
        "an ITSM process document."
    ),
    instruction_file="itsm/scenario_tester_agent.txt",
    tools=[load_full_itsm_context, load_requirements_summary],
)
