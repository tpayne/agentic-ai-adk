# adk/agent.py
"""
ADK Agent equipped with custom financial tools using yfinance.

This file defines the Agent and its tools using the standard Google ADK pattern.
The docstrings and type hints are critical for the LLM to understand and use these tools.
"""

# ADK and type imports
from google.adk.agents import LlmAgent
from typing import Dict, List, Any

# Third-party library for financial data (required: pip install yfinance)
import yfinance as yf
import requests_cache

# Use in-memory cache for robustness in containerized environments
# Cache expiration set to 60 seconds to provide near real-time data
requests_cache.install_cache(backend="memory", expire_after=60)


# --- ADK Function Tools ---

def get_last_stock_price(symbol: str) -> Dict[str, Any]:
    """
    Retrieves the last known stock price and the timestamp of that price for a specified stock symbol.

    Args:
        symbol: The stock ticker symbol (e.g., 'BP.L', 'TSLA', 'GOOGL').

    Returns:
        A dictionary containing the symbol, price, and timestamp (in Unix seconds),
        or an 'error' message if the data cannot be retrieved.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Check for common market data fields
        price = info.get('regularMarketPrice')
        timestamp_seconds = info.get('regularMarketTime')
        
        if price is None or timestamp_seconds is None:
            # Attempt to find alternative fields if market is closed or specific data is missing
            price = info.get('currentPrice')
            
            if price is None:
                 raise ValueError(f"Could not retrieve a current price for {symbol}.")

            # Use a sentinel value if timestamp is missing, though yfinance usually provides one
            timestamp_seconds = timestamp_seconds if timestamp_seconds is not None else 0 

        return {
            'symbol': symbol,
            'price': float(price),
            'timestamp': int(timestamp_seconds)
        }
        
    except Exception as e:
        return {'error': f"Failed to fetch last price for {symbol}: {e}"}


def get_aggregated_stock_data(symbol: str, interval: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Retrieves aggregated Open-High-Low-Close-Volume (OHLCV) stock market data 
    for a given symbol over a specified time period.

    Args:
        symbol: The stock ticker symbol (e.g., 'AAPL', 'MSFT').
        interval: The aggregation period (e.g., '1h', '1d', '1wk'). Supported intervals 
                  include: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo.
        start_date: The starting date for the data period in 'YYYY-MM-DD' format.
        end_date: The ending date for the data period in 'YYYY-MM-DD' format.

    Returns:
        A dictionary containing the symbol, interval, and an array of OHLCV data points,
        or an 'error' message if the data cannot be retrieved.
    """
    try:
        ticker = yf.Ticker(symbol)
        
        history_df = ticker.history(
            start=start_date, 
            end=end_date, 
            interval=interval,
            # Ensure data frame is filtered to just the time window requested
        )
        
        historical_data = []
        for index, row in history_df.iterrows():
            historical_data.append({
                'date': index.strftime('%Y-%m-%d %H:%M:%S'), 
                'open': round(row['Open'], 4),
                'high': round(row['High'], 4),
                'low': round(row['Low'], 4),
                'close': round(row['Close'], 4),
                'volume': int(row['Volume'])
            })

        return {
            'symbol': symbol,
            'interval': interval,
            'data': historical_data
        }
        
    except Exception as e:
        return {'error': f"Failed to fetch aggregated data for {symbol}: {e}"}


# --- ADK Agent Definition ---

# The root_agent is the entry point for the ADK application.
root_agent = LlmAgent(
    name="Financial_Analysis_Agent",
    model="gemini-2.5-flash",
    description="A specialist financial assistant that uses market data tools to answer questions about stock prices and historical performance.",
    instruction="You are a helpful and professional financial analyst. Use the provided tools (get_last_stock_price and get_aggregated_stock_data) to answer any user queries about stock information. If the user asks for a current price, use the get_last_stock_price tool. If the user asks about historical trends, use the get_aggregated_stock_data tool.",
    tools=[
        get_last_stock_price,
        get_aggregated_stock_data,
    ],
)

# Note: The custom CLI and other non-ADK-standard logic (like example_llm_call, 
# ADKToolError, retry, and process_file_lines) from the original file have been 
# removed, as they are typically replaced by the ADK Runner when deploying or 
# running the agent with `adk web` or `adk run`.
