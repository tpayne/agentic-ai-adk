# Agentic ADK Samples
Sample code for ADK

# Status
[![Build and Test Docker Images](https://github.com/tpayne/agentic-ai-adk/actions/workflows/testbuild.yml/badge.svg)](https://github.com/tpayne/agentic-ai-adk/actions/workflows/testbuild.yml)
[![CodeQL Scan](https://github.com/tpayne/agentic-ai-adk/actions/workflows/codescanner.yaml/badge.svg)](https://github.com/tpayne/agentic-ai-adk/actions/workflows/codescanner.yaml)

# Samples

| Platform | Sample | What it does | README |
|---|---|---|---|
| **Claude** (Google ADK + Claude models via LiteLLM) | FinanceADK | Google ADK agent wired to Claude models that exposes Yahoo Finance tools (prices, beta/volatility, risk-free rate, time series) through a conversational root agent. | [README](samples/Claude/FinanceADK/README.md) |
| **GCP** (Google Agent Development Kit) | EmailProcessing | ADK agents that read, triage, and respond to emails (e.g. Gmail) using AI, demonstrating automated inbox processing. | [README](samples/GCP/EmailProcessing/README.md) |
| **GCP** (Google Agent Development Kit) | FinanceADK | ADK agent exposing Yahoo Finance tools via a root LLM agent, running on Google's own models. | [README](samples/GCP/FinanceADK/README.md) |
| **GCP** (Google Agent Development Kit) | FinanceProcessing | An alternate ADK-style Yahoo Finance agent with its own tool registry/dispatcher, schema validation, and CLI interactive/batch modes. | [README](samples/GCP/FinanceProcessing/README.md) |
| **GCP** (Google Agent Development Kit) | ProcessEngineering | Multi-agent Business Process Architect: takes a rough prompt and designs, tests, and documents a full business process or architecture design (HLD/LLD), including diagrams. | [README](samples/GCP/ProcessEngineering/README.md) |
| **Neurosan** ([neuro-san](https://github.com/cognizant-ai-lab/neuro-san) framework) | ProcessEngineering | The same Business Process Architect capability, ported to neuro-san's declarative HOCON agent networks and Python `CodedTool`s, provider-agnostic (Gemini, Anthropic, OpenAI, Bedrock, Azure OpenAI). | [README](samples/Neurosan/ProcessEngineering/README.md) |
| **WebClient** (backend-agnostic browser UI) | ProcessEngineering | A static, no-build chat UI that talks to either ProcessEngineering backend (GCP ADK or neuro-san) over their shared REST API. | [README](samples/WebClient/ProcessEngineering/README.md) |
