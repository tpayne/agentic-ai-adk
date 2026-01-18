# Changelog

All notable changes to the **Agentic AI ADK** project will be documented in this file. This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
