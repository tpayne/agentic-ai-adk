# ADK Yahoo Finance LLM Agent

A lightweight ADK-style agent exposing Yahoo Finance tools via a root LLM agent.

## Features

- **Tools:**  
    - `get_last_stock_price`  
    - `get_aggregated_stock_data`  
    *(yfinance-backed)*

- Root ADK tool registry + dispatcher with schema validation and timeouts.
- Root `LlmAgent` accepts natural-language queries, parses LLM-style JSON decisions, and invokes tools.
- In-memory requests-cache to avoid filesystem permission issues in containers.
- CLI interactive mode and batch mode: pass `-f <file>` to run commands from a file (one command per line).
- Minimal rule-based example LLM for local testing; designed to be replaced by a real LLM call.

---

## Repository Layout

```
adk/
    __init__.py
    agent.py          # main merged module (ADK root, tools, LlmAgent, CLI)
    requirements.txt
    Dockerfile
    sample.txt        # (optional) sample batch commands (one per line)
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
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the interactive CLI:

```bash
python -m adk.agent
```

**Example prompts:**

- What's the last price for TSLA?
- Show historical OHLC for AAPL 2023-01-01 to 2023-02-01

Run in batch mode (file contains one query per non-empty line):

```bash
python -m adk.agent -f sample.txt
```

Use `--no-json` to print human-friendly output instead of compact JSON per line:

```bash
python -m adk.agent -f sample.txt --no-json
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

**Batch run (mount your sample file into the container):**

```bash
docker run --rm -it -v "$(pwd)/sample.txt":/app/sample.txt adkfinance -f sample.txt
```

**Batch run with friendly output:**

```bash
docker run --rm -it -v "$(pwd)/sample.txt":/app/sample.txt adkfinance -f sample.txt --no-json
```

**Notes:**

- The Docker image runs the module `adk.agent` as the container ENTRYPOINT. Arguments passed to `docker run` are forwarded to the module.
- The agent uses an in-memory requests-cache by default to avoid file permission problems inside the container. If you require persistent cache, change the cache backend in `adk/agent.py` and ensure the cache directory is writable.

---

## Batch File Format

- Plain text file with one command per line.
- Blank lines and lines beginning with `#` are ignored.

**Example `sample.txt`:**

```
What's the last price for BP
Get historical OHLC for AAPL 2023-01-01 to 2023-02-01
```

---

## Replacing the Example LLM

The module ships with a rule-based `example_llm_call(prompt: str) -> str` to produce the JSON structure that `LlmAgent` expects:

```json
{"tool": "get_last_stock_price", "params": {"symbol": "TSLA"}, "explain": "Fetching last price for TSLA"}
```

Replace `example_llm_call` with your actual LLM integration. `LlmAgent` expects the LLM to return a string containing a JSON object with at least the `tool` and `params` fields.

**Recommended improvements:**

- Use the model's structured/function-calling API where possible to avoid JSON extraction heuristics.
- Validate and sanitize params returned by the model before invoking tools.

---

## Extending Tools

- Add new tool functions in `adk/agent.py` (or create separate modules and import).
- Register tools with `ADKRootAgent.register_tool(name, fn, schema=..., description=..., timeout_seconds=...)`.
- Provide a JSON schema in `schema` to enable lightweight validation.

---

## Troubleshooting

- **sqlite/requests-cache permission errors in container:**  
    This project uses `requests_cache.install_cache(backend="memory", ...)` so the issue should not occur. If you change to a file-backed cache, ensure the cache directory is writable by the runtime user in the container.

- **If `python -m adk.agent` raises import errors:**  
    - Confirm an `__init__.py` exists under `adk/`.
    - Confirm `adk/agent.py` is present and syntactically valid.

- **If the LLM picks an invalid symbol (e.g., the literal "JSON"):**  
    The agent contains a fallback that extracts ticker-like tokens from the user's text. For stronger behavior, improve the LLM prompt to return only structured JSON or use function-calling.

---

## Development Notes

- The agent validates ticker formats with a conservative regex: `^[A-Z]{1,5}(?:\.[A-Z]{1,3})?$`. Adjust if you need to support other exchange suffix formats.
- Tools run in a small thread pool (configurable via `ADKRootAgent(max_workers=...)`).
- Error shape returned by `ADKRootAgent.invoke_tool` is:

    ```json
    {"error": {"message": "...", "code": "..."}}
    ```

- Successful invocation returns:

    ```json
    {"result": {...}}
    ```

---

## License

This repository contains sample code. Apply your preferred license. No license is included by default.

---

## Contact / Next Steps

- Replace the example LLM with your production LLM client and test prompt-output formats.
- Add metrics, logging hooks, and RBAC if you plan to operate this in production.
- If you want, I can generate a stricter JSON schema for tool parameters or produce a FastAPI wrapper to expose the agent over HTTP.