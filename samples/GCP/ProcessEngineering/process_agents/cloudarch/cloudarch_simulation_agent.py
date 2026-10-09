# process_agents/cloudarch_simulation_agent.py
#
# CloudArch diagram simulation: structural resilience, scalability, and
# latency, derived purely from the diagram's own vertices/edges. Logic
# lives in process_toolkit.cloudarch.simulation (shared with the
# neuro-san port) -- this file is just the ADK agent wrapper.

from google.genai import types

from process_toolkit.cloudarch.simulation import simulate_cloudarch_architecture

from ..common.utils import load_drawio, load_master_process_json, load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

# ============================================================
# LLM AGENT: CLOUDARCH SIMULATION QUERY AGENT (ON-DEMAND, USER-FACING)
# ============================================================
# On-demand only, analogous to design_simulation_query_agent -- NOT wired
# as a pipeline-internal auto-revision gate. The user asked for the ability
# to run simulations against the diagram, not for generation to auto-block
# on results; adding a gate would be unrequested scope growth.
cloudarch_simulation_query_agent = ProcessLlmAgent(
    name="CloudArch_Simulation_Query_Agent",
    description=(
        "Runs a structural resilience (blast-radius Monte Carlo), scalability (fan-in bottleneck), and "
        "latency (dependency chain depth) simulation over an EXISTING cloud architecture diagram, in "
        "response to queries."
    ),
    tools=[
        load_drawio,
        load_master_process_json,
        load_requirements_summary,
        simulate_cloudarch_architecture,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
    instruction_file="cloudarch/cloudarch_simulation_query_agent.txt",
)
