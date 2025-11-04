# ADK Yahoo Finance LLM Agent

A lightweight ADK LLM agent exposing Yahoo Finance tools via a root LLM agent.

## Features

- **Tools:**  
    - `get_last_stock_price`  
    - `get_aggregated_stock_data`  
    - `get_major_index_symbols`
    - `calculate_beta_and_volatility`
    - `compare_key_metrics`
    - `generate_time_series_chart_data`
    - `get_risk_free_rate`
    - `get_historical_market_return`   
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

Sample runs in ADK
![Sample run](Images/sample001.png)

Sample flow
![Sample run](Images/sample002.png)

Sample CAPM flow calculation
![Sample run](Images/sample003.png)

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

## Sample Prompts

- "What are the RSI and MACD values for Tesla (TSLA) based on the last 6 months of data?"
- "Can you provide the latest 20-day Simple Moving Average (SMA) for the FTSE 100 (^FTSE) over the past year?"
- "I need the complete technical indicator data, including the MACD, RSI, and SMA, for Microsoft (MSFT) for the 3-month period."
- "What is the current On-Balance Volume (OBV) reading for Amazon (AMZN) using the last 2 years of trading data?"
- "Calculate the OBV for JPMorgan Chase (JPM) for the 1-year period."
- "Please check the On-Balance Volume for Alphabet (GOOGL) over the past 3 months."
- "What is the CAPM of CTSH when compared to the FTSE100 for the last 5 years"
- "get the stock price for BP from FTSE100"
