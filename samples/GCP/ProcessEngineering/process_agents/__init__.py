# process_agents/__init__.py

# Import the main agent module (root pipeline)
from . import agent

# Re-export the root agent for ADK discovery
from .agent import root_agent

__all__ = ["agent", "root_agent"]

# Re-export sub-agents for accessibility
from .analysis_agent import analysis_agent
from .design_agent import design_agent
from .compliance_agent import compliance_agent
from .json_normalizer_agent import json_normalizer_agent
from .doc_generation_agent import doc_generation_agent

__all__ += [
    "analysis_agent",
    "design_agent",
    "compliance_agent",
    "json_normalizer_agent",
    "doc_generation_agent",
]
