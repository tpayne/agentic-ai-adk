# finance_agents/__init__.py

# Import the main agent module
from . import agent

# Re-export the main agent object for easy package-level import
# Assuming the entry point agent is named 'root_agent' in agent.py
from .agent import root_agent 
__all__ = ["agent", "root_agent"] 

# If you need to re-export ALL agents and objects for some reason:
from .calculation_agent import calculation_agent
from .review_agent import review_agent
__all__ += ["calculation_agent", "review_agent"]