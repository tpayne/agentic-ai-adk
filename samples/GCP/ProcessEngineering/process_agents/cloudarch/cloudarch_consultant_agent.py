# process_agents/cloudarch_consultant_agent.py

import logging

logger = logging.getLogger("ProcessArchitect.ConsultantCloudArch")

# -----------------------------
# CLOUDARCH CONSULTANT AGENT
# -----------------------------
# Agent for providing expert advice on an EXISTING cloud architecture diagram
# (the drawio/mxGraph XML persisted by CloudArch_Agent via save_drawio).
# Pinned to load_drawio rather than relying on conversation memory of a prior
# generation turn, since ADK's context-cache/compaction can summarize away
# the exact XML content in a long-running session -- same reasoning as why
# cloudarch_reviewer_agent.py always reloads it rather than trusting recall.
from ..common.utils import load_drawio, load_master_process_json, load_requirements_summary

from ..common.agent_wrappers import ProcessLlmAgent
consultant_cloudarch_agent = ProcessLlmAgent(
    name="CloudArch_Consultant_Agent",
    description="Use this for questions about an EXISTING cloud architecture diagram. It cannot create or modify one.",
    instruction_file="cloudarch/cloudarch_consultant_agent.txt",
    tools=[load_drawio, load_master_process_json, load_requirements_summary],
)
