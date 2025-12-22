# process_agents/__init__.py

# Import the main agent module
from . import agent

# Re-export the main agent object for easy package-level import
# Point to the root_agent
from .agent import root_agent 

__all__ = ["agent", "root_agent"] 

# Re-export sub-agents for accessibility:
from .analysis_agent import analysis_agent
from .design_agent import design_agent
from .compliance_agent import compliance_agent
from .doc_gen_agent import doc_gen_agent

__all__ += ["analysis_agent", "design_agent", "compliance_agent", "doc_gen_agent"]
