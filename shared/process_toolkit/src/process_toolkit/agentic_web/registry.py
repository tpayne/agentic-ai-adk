"""Open Agentic Web capability registry & discovery engine.

Provides unified discovery descriptors, capability search, and .well-known agent manifest
generation for external AI agents, orchestrators, and platforms.
"""

from typing import Any, Dict, List, Optional
from process_toolkit.agentic_web.agent_cards import (
    AGENT_CARDS,
    get_all_agent_cards,
    get_agent_card,
    list_agent_summaries,
)
from process_toolkit.agentic_web.artifact_contracts import (
    ARTIFACT_CONTRACTS,
    list_all_artifact_contracts,
    get_artifact_contract,
    wrap_artifact_envelope,
)
from process_toolkit.agentic_web.workflows import (
    WORKFLOW_DEFINITIONS,
    get_all_workflows,
    get_workflow,
)


def get_agent_manifest(base_url: str = "") -> Dict[str, Any]:
    """Generates the Open Agentic Web standard manifest (served at
    /.well-known/agent.json or /agent-manifest.json)."""
    return {
        "schema_version": "1.0.0",
        "standard": "Open Agentic Web MVP Profile",
        "standard_url": "https://github.com/cognizant-ai-labs/agentic-web",
        "name": "ProcessEngineering Platform",
        "description": (
            "Enterprise-grade multi-agent platform for business process modeling, "
            "systems architecture, cloud diagrams, test specifications, agile backlogs, "
            "RFP proposals, and TOGAF enterprise architecture."
        ),
        "version": "1.0.0",
        "provider": {
            "name": "Cognizant AI Lab",
            "url": "https://github.com/cognizant-ai-labs",
            "license": "Apache-2.0",
        },
        "protocols": [
            "mcp/1.0",
            "fastmcp",
            "openai-tool-calling",
            "sse-streaming",
            "rest-json",
        ],
        "endpoints": {
            "chat": f"{base_url}/chat",
            "chat_stream": f"{base_url}/chat/stream",
            "agents": f"{base_url}/agents",
            "agent_detail": f"{base_url}/agents/{{agent_name}}",
            "capabilities": f"{base_url}/capabilities",
            "workflows": f"{base_url}/workflows",
            "workflow_detail": f"{base_url}/workflows/{{workflow_name}}",
            "artifacts": f"{base_url}/artifacts/{{name}}",
            "artifact_contracts": f"{base_url}/artifacts/contracts",
            "status": f"{base_url}/status",
        },
        "capabilities_count": len(AGENT_CARDS),
        "workflows_count": len(WORKFLOW_DEFINITIONS),
        "artifact_contracts_count": len(ARTIFACT_CONTRACTS),
        "agents": list_agent_summaries(),
    }


def search_capabilities(
    query: Optional[str] = None,
    category: Optional[str] = None,
    artifact: Optional[str] = None,
    agent_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Searchable capability catalog. Allows filtering by query keyword,
    category, produced/consumed artifact, and agent type."""
    normalized_query = (query or "").strip().lower()
    results = []

    for card in AGENT_CARDS.values():
        if category and card.category.lower() != category.lower():
            continue
        if agent_type and card.agent_type.lower() != agent_type.lower():
            continue
        if artifact and artifact.lower() not in [a.lower() for a in card.artifacts]:
            continue

        if normalized_query:
            searchable_text = f"{card.name} {card.description} {' '.join(card.tags)} {' '.join(card.artifacts)}".lower()
            if normalized_query not in searchable_text:
                continue

        results.append(card.to_dict())

    return results
