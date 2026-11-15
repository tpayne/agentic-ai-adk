# Changelog

All notable changes to the **Agentic AI ADK** project will be documented in this file. This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.4.0] - 2026-11-15
### Added
* **`process_interface` Compliance Chokepoint**: Introduced `shared/process_interface`, a new package mirroring `shared/process_toolkit`'s module layout 1:1 that both the Neuro-San and GCP/ADK ProcessEngineering ports now import exclusively — neither port's production code (`coded_tools/`, `process_agents/`) references `process_toolkit` directly anymore. Each switchable call resolves per-request, via `PROCESS_TOOLKIT_MODE`/`PROCESS_TOOLKIT_MCP_URL`/`PROCESS_TOOLKIT_MCP_TIMEOUT` environment variables, to either in-process execution or a real call to the `ProcessToolkitServer` MCP server. Session-local control state (`run_lock`, `loop_control`, `session_purge`, `paths`, `filenames`) always stays local regardless of mode.
* **Expanded `ProcessToolkitServer` MCP tool catalog**: Added 13 new tools (drawio load/reset, cloud architecture simulation/attack-simulation/FinOps estimation, IaC save, master/subprocess JSON load/save, and the full feedback-channel set) so the MCP server now has full parity with the local toolkit, not just document generation.
* **Compliance guard tests**: Added regex-based tests to both ports' own suites asserting no direct `process_toolkit` import lines exist outside test fixtures.
* **`gcp_processengineering_tests` CI job**: GCP/ADK's ProcessEngineering sample previously had no dedicated pytest job in CI at all; its full suite now runs on every push alongside the existing Neuro-San and MCP server jobs.
* **Structural validation for six TOGAF document sections** (`business_architecture`, `data_architecture`, `application_architecture`, `technology_architecture`, `opportunities_and_solutions`, `migration_planning`, `architecture_compliance_assessment`) that `validate_togaf_json` previously left entirely unchecked.

### Fixed
* **TOGAF document generation crash**: `_togaf_has_real_definition_content` raised `AttributeError: 'int' object has no attribute 'get'` when agent-generated content placed a non-object entry (e.g. a bare integer) in a definition-list field such as `business_architecture.capabilities` — a case `(value or {})` guarded against falsy values but not truthy non-dicts. Replaced with a proper type-checking helper across all 14 affected call sites.
* **MCP server `persist_json` validation asymmetry**: the requirements/proposal_response/test_specification domains were validated more strictly over MCP than in local mode, which could silently reject data local mode would accept. All three now use their native, zero-validation `save_*` contract, matching local mode exactly.
* **Missing `shared/process_interface` in Docker images**: all four affected Dockerfiles (GCP's standard and Ollama variants, Neuro-San's standard and Ollama variants) were missing the `COPY` step for the new package, which would have broken every container build.
* **Case-sensitivity bug in GCP's own test suite**: `test_doc_creation_agent_schema_pinning.py` asserted a capitalized generated diagram filename (`Checkout_Service_flow.png`) against code that always lowercases it (`checkout_service_flow.png`) before sanitizing. This passed unnoticed on case-insensitive filesystems (macOS/APFS) but failed deterministically the first time it ran against the new `gcp_processengineering_tests` CI job on Linux.
* **Neuro-San router domain-disambiguation bug**: documented and reinforced the `Process_Architect_Orchestrator`'s Rule 10 after a live run showed a what-if question with no domain-identifying word being silently routed to whichever artifact set the immediately preceding turn concerned, instead of asking for clarification when two active artifact sets (a design document and a TOGAF artifact set) both matched.

---

## [1.3.0] - 2026-01-12
### Added
* **Gemini 3 Flash Support**: Integrated `gemini-3-flash` as the default inference engine for optimized cost and latency in Root Agents.
* **Interactions API**: Migrated core orchestration to the new Interactions API for enhanced state management and long-running background tasks.
* **Deep Research Template**: Added a sample agent implementation leveraging the Gemini Deep Research capabilities via the A2A protocol.

### Fixed
* Resolved race conditions in parallel sub-agent execution during complex tool-calling sequences.

---

## [1.2.0] - 2025-12-05
### Added
* **Model Context Protocol (MCP)**: Added `MCPToolset` support, allowing agents to connect directly to external data sources using the standardized MCP schema.
* **Cost-Aware Routing**: New logic in `RouterAgent` to dynamically switch between Flash and Pro models based on task complexity.
* **Telemetry Dashboard**: Enhanced local development UI to track token consumption and agent reasoning steps in real-time.

### Changed
* **Code Execution**: Updated to the `BuiltInCodeExecutor` package for improved security sandboxing in Python-based tools.

---

## [1.1.0] - 2025-10-20
### Added
* **BCS Presentation Demo**: Included finalized assets and documentation for the "GenAI & Custom Assistants" session at the BCS (The Chartered Institute for IT).
* **A2A Protocol v0.2**: Implemented the latest Agent-to-Agent communication standards for multi-agent handoffs.
* **Vector Search Integration**: Pre-configured `SearchAgent` template for Vertex AI Vector Search.

### Fixed
* Fixed authentication persistence issues when deploying to Google Cloud Run.

---

## [1.0.0] - 2025-05-25
### Added
* **Initial Production Release**: Stable implementation following the Google Agent Development Kit (ADK) v1.0.0 specification.
* **Core Orchestration Patterns**: Support for Sequential, Parallel, and Loop workflow architectures.
* **Architectural Guidance**: Comprehensive documentation for UK-based cloud architects on "Agentic Service Computing."

---

## [0.5.0] - 2025-02-15
### Added
* **Early Access ADK**: Initial experiments with the Google ADK beta framework.
* **Basic Tooling**: Prototype implementations for function calling (Weather, Currency, and Search).
