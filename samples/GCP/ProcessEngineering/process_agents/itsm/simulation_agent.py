# process_agents/itsm/simulation_agent.py
#
# Wraps the shared structural risk/coverage analysis
# (process_interface.itsm.simulation.simulate_itsm_risk_and_coverage --
# role-concentration bottlenecks, missing escalation paths, missing SLA
# measurement fields, outsized CI blast radius, RACI coverage gaps) in two
# LLM agents: ITSM_Simulation_Agent, the loop-internal gate wired into
# Full_ITSM_Pipeline/Update_ITSM_Pipeline (mirrors
# simulation_agent.py's own Simulation_Optimization_Agent /
# design_simulation_agent.py's own Design_Architecture_Simulation_Agent),
# and ITSM_Simulation_Query_Agent, the standalone on-demand narrative
# agent (mirrors design_simulation_query_agent/requirements_simulation_
# query_agent). Deliberately NOT a Monte Carlo timing simulation --
# the ITSM schema has no duration/date fields to model one from, so all
# the actual analysis logic lives once, shared with the neuro-san port,
# in process_interface/process_toolkit; these two agents are just the
# ADK-side gate/narrator around it.

from google.genai import types

from ..common.utils import (
    load_full_itsm_context,
    load_requirements_summary,
    save_iteration_feedback,
    simulate_itsm_risk_and_coverage,
)
from ..common.agent_wrappers import ProcessLlmAgent


def simulate_itsm_risk() -> dict:
    """Runs the structural risk/coverage analysis over the current ITSM
    process document. Takes no meaningful arguments -- it loads the
    baseline itself (never a caller-supplied JSON blob -- see
    design_simulation_agent.py's own _resolve_input_data docstring for why
    that argument shape is avoided: a real document is easily large enough
    that asking the model to retype it verbatim as a tool argument risks
    silent truncation)."""
    return simulate_itsm_risk_and_coverage(None)


itsm_simulation_agent = ProcessLlmAgent(
    name="ITSM_Simulation_Agent",
    description=(
        "Runs the structural risk/coverage analysis against the ITSM process document being built "
        "and decides whether it requires revision before it can proceed."
    ),
    tools=[
        simulate_itsm_risk,
        save_iteration_feedback,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        top_p=1,
    ),
    instruction_file="itsm/simulation_agent.txt",
)

itsm_simulation_query_agent = ProcessLlmAgent(
    name="ITSM_Simulation_Query_Agent",
    description=(
        "Runs the structural risk/coverage analysis over an EXISTING ITSM process document and "
        "explains bottlenecks, coverage gaps, and blast-radius risk in plain business language. Not "
        "a timing/cost simulation -- the schema has no duration/date fields to model one from."
    ),
    tools=[
        load_full_itsm_context,
        load_requirements_summary,
        simulate_itsm_risk,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
    instruction_file="itsm/simulation_query_agent.txt",
)
