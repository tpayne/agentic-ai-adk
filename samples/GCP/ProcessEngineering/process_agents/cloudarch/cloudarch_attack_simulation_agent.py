# process_agents/cloudarch_attack_simulation_agent.py
#
# CloudArch diagram adversarial attack-path simulation: unauthenticated
# access, lateral movement, privilege escalation, data exfiltration, and
# credential compromise, derived purely from the diagram's own vertices/
# edges and each component's shape/label vocabulary. Logic lives in
# process_toolkit.cloudarch.attack_simulation (shared with the neuro-san
# port) -- this file is just the ADK agent wrapper.

from google.genai import types

from process_toolkit.cloudarch.attack_simulation import simulate_cloudarch_attack

from ..common.utils import load_drawio, load_requirements_summary
from ..common.utils_agent import claim_cloudarch_drawio_readonly
from ..common.agent_wrappers import ProcessLlmAgent

# ============================================================
# LLM AGENT: CLOUDARCH ATTACK SIMULATION QUERY AGENT (ON-DEMAND, USER-FACING)
# ============================================================
# On-demand only, sibling to cloudarch_simulation_query_agent -- a
# deliberately separate standalone agent (not folded into the resilience
# simulation agent or the Consultant agent) because adversarial attack-path
# analysis is a genuinely distinct agentic function with its own output
# shape, not a close-enough overlap with either existing agent's job.
cloudarch_attack_simulation_query_agent = ProcessLlmAgent(
    name="CloudArch_Attack_Simulation_Query_Agent",
    description=(
        "Runs an adversarial attack-path simulation (unauthenticated access, lateral movement, "
        "privilege escalation, data exfiltration, credential compromise) against an EXISTING cloud "
        "architecture diagram from a hacker's perspective, and explains what an attacker could reach "
        "and what controls are missing, in response to queries. Analysis only -- does not modify the "
        "diagram."
    ),
    tools=[
        load_drawio,
        load_requirements_summary,
        simulate_cloudarch_attack,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
    instruction_file="cloudarch/cloudarch_attack_simulation_query_agent.txt",
    before_agent_callback=claim_cloudarch_drawio_readonly,
)
