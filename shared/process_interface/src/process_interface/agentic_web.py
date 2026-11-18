"""ProcessEngineering's own Agent Discovery API interface.

Provides this project's own Agent Cards, Capability Discovery, Artifact Contracts, and
Workflow definitions for both ADK and NeuroSAN ProcessEngineering backends. Fully
switchable between in-process execution (PROCESS_TOOLKIT_MODE=local) and FastMCP remote
execution (PROCESS_TOOLKIT_MODE=mcp). Not an implementation of the external "Open Agentic
Web" standard (https://github.com/cognizant-ai-labs/agentic-web) -- see
`process_toolkit.agentic_web`'s own module docstrings for what that distinction means and
where this project's genuine alignment with that external spec actually lives
(`samples/Neurosan/ProcessEngineering/network_publishing.py`).
"""

from typing import Any, Dict, List, Optional

from process_toolkit.agentic_web import (
    AgentCard,
    AgentProvenance,
    AGENT_CARDS,
    ArtifactContract,
    ARTIFACT_CONTRACTS,
    WorkflowDefinition,
    WORKFLOW_DEFINITIONS,
)
from process_toolkit.agentic_web import agent_cards as _toolkit_cards
from process_toolkit.agentic_web import artifact_contracts as _toolkit_contracts
from process_toolkit.agentic_web import registry as _toolkit_registry
from process_toolkit.agentic_web import workflows as _toolkit_workflows

from process_interface import config, _transport

__all__ = [
    "AgentCard",
    "AgentProvenance",
    "AGENT_CARDS",
    "get_all_agent_cards",
    "get_agent_card",
    "list_agent_summaries",
    "ArtifactContract",
    "ARTIFACT_CONTRACTS",
    "get_artifact_contract",
    "list_all_artifact_contracts",
    "wrap_artifact_envelope",
    "WorkflowDefinition",
    "WORKFLOW_DEFINITIONS",
    "get_all_workflows",
    "get_workflow",
    "get_agent_manifest",
    "search_capabilities",
]


def get_agent_manifest(base_url: str = "") -> Dict[str, Any]:
    if config.is_mcp_mode():
        return _transport.call("get_agent_manifest", {"base_url": base_url})
    return _toolkit_registry.get_agent_manifest(base_url=base_url)


def get_all_agent_cards() -> List[Dict[str, Any]]:
    if config.is_mcp_mode():
        return _transport.call("list_agents", {})
    return _toolkit_cards.get_all_agent_cards()


def get_agent_card(name: str) -> Optional[Dict[str, Any]]:
    if config.is_mcp_mode():
        try:
            return _transport.call("get_agent_card", {"name": name})
        except Exception:
            return None
    return _toolkit_cards.get_agent_card(name)


def list_agent_summaries(
    category: Optional[str] = None,
    artifact: Optional[str] = None,
    agent_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if config.is_mcp_mode():
        cards = _transport.call(
            "list_agents",
            {"category": category, "artifact": artifact, "agent_type": agent_type},
        )
        return [
            {
                "name": c["name"],
                "description": c["description"],
                "category": c["category"],
                "agent_type": c["agent_type"],
                "artifacts": c["artifacts"],
                "version": c["version"],
            }
            for c in cards
        ]
    return _toolkit_cards.list_agent_summaries(
        category=category, artifact=artifact, agent_type=agent_type
    )


def search_capabilities(
    query: Optional[str] = None,
    category: Optional[str] = None,
    artifact: Optional[str] = None,
    agent_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if config.is_mcp_mode():
        return _transport.call(
            "list_agents",
            {
                "query": query,
                "category": category,
                "artifact": artifact,
                "agent_type": agent_type,
            },
        )
    return _toolkit_registry.search_capabilities(
        query=query,
        category=category,
        artifact=artifact,
        agent_type=agent_type,
    )


def get_all_workflows() -> List[Dict[str, Any]]:
    if config.is_mcp_mode():
        return _transport.call("list_workflows", {})
    return _toolkit_workflows.get_all_workflows()


def get_workflow(workflow_name: str) -> Optional[Dict[str, Any]]:
    if config.is_mcp_mode():
        try:
            return _transport.call("get_workflow", {"workflow_name": workflow_name})
        except Exception:
            return None
    return _toolkit_workflows.get_workflow(workflow_name)


def list_all_artifact_contracts() -> List[Dict[str, Any]]:
    if config.is_mcp_mode():
        return _transport.call("list_artifact_contracts", {})
    return _toolkit_contracts.list_all_artifact_contracts()


def get_artifact_contract(artifact_type: str) -> Optional[Dict[str, Any]]:
    if config.is_mcp_mode():
        try:
            return _transport.call("get_artifact_contract", {"artifact_type": artifact_type})
        except Exception:
            return None
    return _toolkit_contracts.get_artifact_contract(artifact_type)


def wrap_artifact_envelope(
    artifact_type: str,
    data: Any,
    producer: Optional[str] = None,
    artifact_id: Optional[str] = None,
    version: str = "1.0",
) -> Dict[str, Any]:
    return _toolkit_contracts.wrap_artifact_envelope(
        artifact_type=artifact_type,
        data=data,
        producer=producer,
        artifact_id=artifact_id,
        version=version,
    )
