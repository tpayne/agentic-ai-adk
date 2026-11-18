"""ProcessEngineering's own capability registry & discovery engine.

Provides this project's own unified discovery descriptors, capability search, and
`/.well-known/agent.json` manifest generation for external AI agents, orchestrators, and
MCP-style clients (Claude, Cursor, VS Code, OpenAI Agent SDK). This is a self-contained
discovery API for this project, not an implementation of the external "Open Agentic Web"
standard (https://github.com/cognizant-ai-labs/agentic-web) -- see
`samples/Neurosan/ProcessEngineering/network_publishing.py` for the piece of this project
that genuinely does publish data per that external spec (resolved Neuro-San HOCON agent
networks as `agent-manifest.json` + `<network>.network.json`).
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
    """Generates this project's own discovery manifest, served at
    /.well-known/agent.json. This is a self-contained convention for this project's own
    Agent Discovery API -- distinct from (and not served at) the path and schema the
    external "Open Agentic Web" standard specifies for its own agent-manifest.json (see
    this module's own docstring)."""
    return {
        "schema_version": "1.0.0",
        "name": "ProcessEngineering Platform",
        "description": (
            "Enterprise-grade multi-agent platform for business process modeling, "
            "systems architecture, cloud diagrams, test specifications, agile backlogs, "
            "RFP proposals, and TOGAF enterprise architecture. This manifest describes "
            "this project's own Agent Discovery API; it is not a conformance claim "
            "against any external agent-interoperability standard."
        ),
        "version": "1.0.0",
        "provider": {
            "name": "Agentic-AI-ADK",
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
