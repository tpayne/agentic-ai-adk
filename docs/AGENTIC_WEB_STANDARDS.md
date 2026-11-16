# Open Agentic Web Standards Compliance Guide

## 1. Executive Summary

This document specifies the Open Agentic Web standard compliance implementation for the **ProcessEngineering** multi-agent platform across both the Google Cloud ADK (`samples/GCP/ProcessEngineering`) and NeuroSAN (`samples/Neurosan/ProcessEngineering`) backends.

The platform aligns with the [Open Agentic Web](https://github.com/cognizant-ai-labs/agentic-web) standard profile, providing:
- **Capability Discovery & Agent Manifests** (`/.well-known/agent.json`)
- **Machine-Readable Agent Cards** with inputs, outputs, dependencies, provenance, and semantic versioning
- **Searchable Capability Catalog** (`GET /capabilities`, `GET /agents`)
- **Standardized Artifact Contracts & Envelopes** (`GET /artifacts/contracts`)
- **Engineering Lifecycle Workflow Publication** (`GET /workflows`)
- **Standardized Event Streaming** for real-time orchestration transparency
- **Seamless External Agent Invocation** for Claude, Cursor, VS Code, OpenAI Agent SDK, and MCP clients.

---

## 2. Architecture & Shared Infrastructure

Both backends share core compliance infrastructure in `shared/process_toolkit/src/process_toolkit/agentic_web/`:

```
shared/process_toolkit/src/process_toolkit/agentic_web/
├── __init__.py               # Re-exports of all capabilities, cards, and workflows
├── agent_cards.py            # 32 machine-readable AgentCard definitions
├── artifact_contracts.py     # 13 ArtifactContract specifications & envelope wrapper
├── workflows.py              # 6 Engineering Lifecycle Workflow definitions
└── registry.py               # Manifest generator and capability search engine
```

The compliance interface is cleanly exposed via `shared/process_interface/src/process_interface/agentic_web.py`, ensuring 100% parity and zero code duplication between the ADK and NeuroSAN runtimes.

---

## 3. Phase 1: Machine-Readable Agent Cards

Every specialist network and pipeline exposes an `AgentCard` describing its purpose, category, agent type, version, inputs, outputs, artifacts, tools, and provenance:

```yaml
name: design_simulation_query
description: Simulates architecture resilience, scalability, security and latency.
category: design
agent_type: simulator
inputs:
  - design_document
outputs:
  - simulation_report
artifacts:
  - design_document
  - simulation_report
version: 1.0.0
provenance:
  owner: Cognizant AI Lab / Agentic-AI-ADK
  license: Apache-2.0
```

### Registered Specialist Agents (32 Total):
1. **Orchestration**: `process_architect`
2. **Requirements**: `requirements_summary`, `requirements_consultant`, `requirements_reviewer`, `requirements_simulation_query`, `requirements_doc_pipeline`
3. **Business Process**: `process`, `process_update`, `process_consultant`, `process_simulation_query`, `process_scenario_tester`
4. **Systems Architecture**: `design`, `design_update`, `design_consultant`, `design_simulation_query`, `design_scenario_tester`
5. **Cloud Architecture & FinOps**: `cloudarch`, `cloudarch_consultant`, `cloudarch_simulation_query`, `cloudarch_attack_simulation_query`, `cloudarch_finops`, `cloudarch_iac`
6. **Quality & Test Assurance**: `test_specification`, `test_consultant`, `test_reviewer`
7. **Agile Portfolio Management**: `portfolio_backlog`
8. **Commercial RFP/Bid Management**: `proposal_response_pipeline`, `proposal_response_consultant`, `proposal_response_reviewer`
9. **Enterprise Architecture (TOGAF)**: `togaf`, `togaf_scenario_tester`
10. **Document Rendering Utilities**: `regenerate_document`

---

## 4. Phase 2: Capability Discovery Endpoints

Both `samples/Neurosan/ProcessEngineering/cli.py` and `samples/GCP/ProcessEngineering/process_agents/common/agent.py` expose identical REST discovery endpoints.

Discovery routes bypass authentication and rate-limiting to allow external orchestrators and spiders to inspect agent capabilities without prior credentials.

### Discovery Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/.well-known/agent.json` | `GET` | Open Agentic Web standard discovery manifest |
| `/agent-manifest.json` | `GET` | Discovery manifest alias |
| `/agents` | `GET` | Capability registry of all agent cards |
| `/agents/<name>` | `GET` | Detailed Agent Card for a specific agent |
| `/capabilities` | `GET` | Searchable capability catalog with filtering |

### Query Parameters for `/agents` and `/capabilities`:
- `?category=<category>`: Filter by domain (`process`, `design`, `cloudarch`, `requirements`, `testing`, `portfolio`, `proposal`, `governance`)
- `?artifact=<artifact>`: Filter by consumed/produced artifact (`high_level_design`, `drawio_xml`, `simulation_report`, etc.)
- `?type=<type>`: Filter by agent type (`pipeline`, `consultant`, `reviewer`, `simulator`, `generator`)
- `?query=<text>`: Substring search across name, description, tags, and artifacts
- `?full=true`: Return full Agent Cards instead of concise summaries
- `?wrapped=true`: Wrap results in a `{"status": "ok", "count": N, "agents": [...]}` envelope

---

## 5. Phase 3: Standard Artifact Registry & Contracts

Outputs across all pipelines conform to standardized `ArtifactContract` schemas.

### Registered Artifact Types (13 Total)

| Artifact Type | Format | Producer | Canonical Output File |
|---|---|---|---|
| `requirements_summary` | JSON | `requirements_summary` | `requirements_summary.json` |
| `process_definition` | JSON | `process` | `process_data.json` |
| `high_level_design` | JSON | `design` | `design_data.json` |
| `low_level_design` | JSON | `design` | `design_data.json` |
| `cloud_architecture` | XML/JSON | `cloudarch` | `cloudarch_drawio.xml` |
| `drawio_xml` | XML | `cloudarch` | `cloudarch_drawio.xml` |
| `simulation_report` | JSON | `design_simulation_query` | `iteration_feedback_simulation.json` |
| `finops_report` | JSON | `cloudarch_finops` | `iteration_feedback.json` |
| `iac_package` | ZIP | `cloudarch_iac` | `cloudarch_iac.zip` |
| `test_specification` | JSON | `test_specification` | `test_specification.json` |
| `portfolio_backlog` | JSON | `portfolio_backlog` | `portfolio_backlog.json` |
| `togaf_artifacts` | JSON | `togaf` | `togaf_data.json` |
| `proposal_response` | JSON | `proposal_response_pipeline` | `proposal_response.json` |

### Contract Discovery Endpoints

- `GET /artifacts/contracts`: Lists all artifact contracts
- `GET /artifacts/contracts/<artifact_type>`: Returns full schema fields, mime type, and producer details for a specific artifact type.

### Standard Output Envelope
Raw artifact data can be packaged inside the standard Open Agentic Web envelope using `wrap_artifact_envelope()`:

```json
{
  "artifact_id": "DES-20261116-a1b2c3",
  "artifact_type": "high_level_design",
  "version": "1.0",
  "producer": "design",
  "created": "2026-11-16T21:30:00Z",
  "contract_version": "1.0",
  "data": { ... }
}
```

---

## 6. Phase 4: Lifecycle Workflow Publication

The platform publishes machine-readable engineering lifecycle workflows representing multi-agent orchestration flows.

### Published Workflows
1. **`architecture_lifecycle`**:
   `requirements_summary` -> `design` -> `design_simulation_query` -> `cloudarch` -> `cloudarch_simulation_query` -> `cloudarch_finops` -> `cloudarch_iac`
2. **`process_engineering_lifecycle`**:
   `requirements_summary` -> `process` -> `process_simulation_query` -> `process_scenario_tester` -> `regenerate_document`
3. **`enterprise_architecture_togaf_lifecycle`**:
   `requirements_summary` -> `togaf` -> `togaf_scenario_tester` -> `design` -> `cloudarch` -> `regenerate_document`
4. **`test_assurance_lifecycle`**:
   `requirements_summary` -> `test_specification` -> `test_reviewer` -> `test_consultant` -> `regenerate_document`
5. **`portfolio_planning_lifecycle`**:
   `requirements_summary` -> `portfolio_backlog` -> `design` -> `cloudarch_finops`
6. **`bid_proposal_lifecycle`**:
   `requirements_summary` -> `proposal_response_pipeline` -> `proposal_response_reviewer` -> `proposal_response_consultant` -> `regenerate_document`

### Workflow Endpoints
- `GET /workflows`: Lists all available lifecycle workflows
- `GET /workflows/<workflow_name>`: Returns step ordering, stage transitions, and produced artifacts for a specific workflow.

---

## 7. External Agent Invocation & Interoperability

External agents (Claude Code, Cursor, VS Code Copilot, OpenAI Agent SDK, LangChain, AutoGen) can interact with ProcessEngineering via three compliant transport modes:

### A. FastMCP / Model Context Protocol
Start the server in MCP mode:
```bash
PROCESS_TOOLKIT_MODE=mcp python -m process_interface.server
```
Add to your `claude_desktop_config.json` or `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "process_engineering": {
      "command": "python",
      "args": ["-m", "process_interface.server"],
      "env": {
        "PROCESS_TOOLKIT_MODE": "mcp"
      }
    }
  }
}
```

### B. Standard Agentic Web Discovery
External agents discover capabilities via HTTP:
```python
import httpx

# 1. Discover capabilities
manifest = httpx.get("http://localhost:5000/.well-known/agent.json").json()

# 2. Find design agents
agents = httpx.get("http://localhost:5000/agents?category=design").json()

# 3. Inspect artifact contracts
contract = httpx.get("http://localhost:5000/artifacts/contracts/high_level_design").json()
```

### C. OpenAI Agent SDK & Tool Calling
Invoke the agent network directly via the standard REST chat endpoint:
```python
import httpx

response = httpx.post(
    "http://localhost:5000/chat",
    json={
        "query": "Create an architecture design for an event-driven order processing system."
    },
    headers={"Authorization": "Bearer <API_KEY>"},
    timeout=120.0,
)
result = response.json()
print(result["response"])
```
