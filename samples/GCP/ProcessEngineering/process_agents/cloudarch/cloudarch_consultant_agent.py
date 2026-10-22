# process_agents/cloudarch_consultant_agent.py

import logging
from typing import Optional, Union

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
from ..common.utils_agent import claim_cloudarch_drawio_readonly


def load_cloudarch_context(schema_type: Optional[str] = None) -> Union[dict, None]:
    """Loads supporting narrative context for the cloud architecture diagram
    (what it was generated from, if anything) -- the diagram's own XML
    remains the source of truth for what actually exists in it.

    schema_type: pass "process" ONLY if the user's own question explicitly
    names the business process rather than the architecture/design. Omit
    it (the normal case) to get the design document -- NOT "whichever of
    process_data.json/design_data.json was modified most recently" (the
    underlying load_master_process_json's own schema_type=None behavior):
    that silently grounds an answer in an unrelated process document
    whenever one happens to exist and was touched more recently, confirmed
    directly against a real session where it was.
    """
    return load_master_process_json(schema_type=schema_type or "design")


from ..common.agent_wrappers import ProcessLlmAgent
consultant_cloudarch_agent = ProcessLlmAgent(
    name="CloudArch_Consultant_Agent",
    description="Use this for questions about an EXISTING cloud architecture diagram. It cannot create or modify one.",
    instruction_file="cloudarch/cloudarch_consultant_agent.txt",
    tools=[load_drawio, load_cloudarch_context, load_requirements_summary],
    before_agent_callback=claim_cloudarch_drawio_readonly,
)
