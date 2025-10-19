# adk/__init__.py
# Make the package importable and re-export the agent module.
from . import agent

# If your agent module exposes a top-level symbol (Agent or create_agent),
# uncomment the following lines to re-export it for discovery.
# from .agent import Agent, create_agent
# __all__ = ["agent", "Agent", "create_agent"]
