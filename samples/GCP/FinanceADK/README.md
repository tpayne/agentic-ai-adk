# ADK Yahoo Finance LLM Agent

A lightweight ADK LLM agent exposing Yahoo Finance tools via a root LLM agent.

## Features

- **Tools:**  
    - `get_last_stock_price`  
    - `get_aggregated_stock_data`  
    *(yfinance-backed)*

- Root `LlmAgent` accepts natural-language queries, parses LLM-style JSON decisions, and invokes tools.
- In-memory requests-cache to avoid filesystem permission issues in containers.

---

## Repository Layout

```
adk/
    __init__.py
    agent.py          # main merged module (ADK root, tools, LlmAgent, CLI)
    requirements.txt
    Dockerfile
```

---

## Requirements

Minimal Python packages required by the agent:

- yfinance
- requests-cache
- pandas
- numpy
- lxml

See `requirements.txt` for version constraints used in your environment.

---

## Running Locally (Python)

Create a virtual environment and install requirements:

```bash
## Setup and Test Agent

To setup and test the agent, you can do the following.

This will allow the agent to run as a simple invocable script and not use a REST API to drive it.

```bash
    rm -r .venv
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    export GOOGLE_API_KEY=<YourKey>
```

## Test Deployment Emulation

To check that the agent is working correctly in the GCP ADK environment, you can use the web service.

```bash
    .venv/bin/python -m pip install --force-reinstall --no-cache-dir google-adk
    .venv/bin/adk web
```

---

## Docker Usage

**Build:**

```bash
docker build . -t adkfinance
```

**Interactive run:**

```bash
docker run --rm -it adkfinance
```


**Notes:**

- The Docker image runs the module `adk.agent` as the container ENTRYPOINT. Arguments passed to `docker run` are forwarded to the module.

---

## License

This repository contains sample code. Apply your preferred license. No license is included by default.
