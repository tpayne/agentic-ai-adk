# process_agents/requirements_simulation_agent.py
#
# Named to match the existing *_Simulation_Query_Agent family
# (CloudArch_Simulation_Query_Agent, Design_Architecture_Simulation_Query_Agent,
# Simulation_Optimization_Query_Agent), but unlike those, has no deterministic
# coded algorithm to wrap -- "missing requirements" has no graph/Monte-Carlo
# analog, so this is structured LLM reasoning against the saved requirements
# summary's own context plus a fixed category checklist, the same way the
# summary's own "coverage_gaps" field is itself produced. On demand,
# standalone, same shape as Requirements_Consultant_Agent (single tool, no
# save/creation tool, no loop_control/iteration_feedback machinery).

import logging

logger = logging.getLogger("ProcessArchitect.RequirementsSimulationQuery")

from ..common.utils import load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

requirements_simulation_query_agent = ProcessLlmAgent(
    name="Requirements_Simulation_Query_Agent",
    description=(
        "Runs a FRESH completeness/gap analysis against the saved requirements summary, looking "
        "for requirements that appear to be missing entirely -- reasoning about the summary's own "
        "industry sector, stakeholders, assumptions, and risks against standard requirement "
        "categories, and reconciling with (not restating) whatever coverage_gaps/"
        "inferred_requirements extraction already flagged. Cannot modify the requirements itself."
    ),
    instruction_file="common/requirements_simulation_query_agent.txt",
    tools=[load_requirements_summary],
)
