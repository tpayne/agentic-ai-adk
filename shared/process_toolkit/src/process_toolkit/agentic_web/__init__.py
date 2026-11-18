"""ProcessEngineering's own Agent Discovery API module.

Provides:
- Machine-readable Agent Cards for all specialist networks.
- Capability discovery and search engine.
- This project's own Artifact Contracts and envelope wrapping.
- End-to-end engineering lifecycle workflow definitions.
- This project's own discovery manifest (served at /.well-known/agent.json).

This is a self-contained API for this project, not an implementation of the external
"Open Agentic Web" standard (https://github.com/cognizant-ai-labs/agentic-web) -- see each
submodule's own docstring for why, and `samples/Neurosan/ProcessEngineering/
network_publishing.py` for the part of this project that genuinely does align with that
external spec.
"""

from process_toolkit.agentic_web.agent_cards import (
    AgentCard,
    AgentProvenance,
    AGENT_CARDS,
    get_all_agent_cards,
    get_agent_card,
    list_agent_summaries,
)
from process_toolkit.agentic_web.artifact_contracts import (
    ArtifactContract,
    ARTIFACT_CONTRACTS,
    get_artifact_contract,
    list_all_artifact_contracts,
    wrap_artifact_envelope,
)
from process_toolkit.agentic_web.workflows import (
    WorkflowDefinition,
    WORKFLOW_DEFINITIONS,
    get_all_workflows,
    get_workflow,
)
from process_toolkit.agentic_web.registry import (
    get_agent_manifest,
    search_capabilities,
)

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
