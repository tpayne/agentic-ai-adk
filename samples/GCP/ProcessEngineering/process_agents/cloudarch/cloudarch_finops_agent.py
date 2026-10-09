# process_agents/cloudarch_finops_agent.py
#
# CloudArch analogue of cloudarch_simulation_agent.py, but for cost rather
# than resilience/scalability/latency. Logic lives in
# process_toolkit.cloudarch.finops (shared with the neuro-san port) --
# this file is just the ADK agent wrapper.

from google.genai import types

from process_toolkit.cloudarch.finops import estimate_cloudarch_finops

from ..common.utils import load_drawio, load_master_process_json, load_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

# ============================================================
# LLM AGENT: CLOUDARCH FINOPS QUERY AGENT (ON-DEMAND, USER-FACING)
# ============================================================
# On-demand only, same reasoning as cloudarch_simulation_query_agent --
# NOT wired as a pipeline-internal auto-revision gate.
cloudarch_finops_query_agent = ProcessLlmAgent(
    name="CloudArch_FinOps_Agent",
    description=(
        "Estimates the monthly cost of an EXISTING cloud architecture diagram, per component and in "
        "total, grounds explicitly detailed resources in public provider catalogs when possible, "
        "and recommends concrete cost-optimization opportunities (rightsizing, autoscaling, "
        "reserved capacity, storage tiering, orphaned resources), in response to queries."
    ),
    tools=[
        load_drawio,
        load_master_process_json,
        load_requirements_summary,
        estimate_cloudarch_finops,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
    instruction_file="cloudarch/cloudarch_finops_agent.txt",
)
