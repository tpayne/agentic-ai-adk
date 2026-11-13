"""Standalone, load-only agent for interactive what-if scenario testing against an EXISTING TOGAF architecture artifact set."""

from ..common.utils import load_full_togaf_context, load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

togaf_scenario_tester_agent = ProcessLlmAgent(
    name="TOGAF_Scenario_Tester",
    description=(
        "Use this agent to test and reason about what-if scenarios against an EXISTING TOGAF "
        "architecture artifact set, tracing its real traceability/dependency links. It cannot "
        "create new TOGAF artifacts."
    ),
    instruction_file="common/togaf_scenario_tester_agent.txt",
    tools=[load_full_togaf_context, load_requirements_summary],
)
