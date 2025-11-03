# adk/agent.py
"""
ADK Agent equipped with custom financial tools using yfinance and Pandas for scraping.

This file defines the Agent and its tools using the standard Google ADK pattern.
The docstrings and type hints are critical for the LLM to understand and use these tools.
"""

# ADK and type imports
from google.adk.agents import LlmAgent
from typing import Dict, List, Any

# Third-party libraries
import yfinance as yf
import requests_cache
import logging
import pandas as pd # Explicitly imported for web scraping
import requests # Required for robust web scraping with custom headers

# Use in-memory cache for robustness in containerized environments
# Cache expiration set to 60 seconds to provide near real-time data
requests_cache.install_cache(backend="memory", expire_after=60)

# --- logging ---
logger = logging.getLogger("adk_yfinance_llm")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

# Global headers to prevent HTTP 403 errors from being blocked by servers like Wikipedia
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


# --- Internal Web Scraping Helpers ---

def _get_sp500_symbols() -> List[str]:
    """Scrapes S&P 500 symbols from Wikipedia using a robust column search."""
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    try:
        logger.debug(f"Attempting to fetch HTML from {url} with custom User-Agent.")
        
        # FIX: Use requests with a User-Agent to prevent 403 Forbidden errors
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status() # Check for HTTP errors like 403
        
        tables = pd.read_html(response.text) # Pass the content string to read_html
        
        # Define common column names that hold the ticker symbol
        TICKER_COLUMNS = ['Symbol', 'Ticker', 'Security']
        ticker_column = None

        for table in tables:
            # Check if any of the common ticker column names are present
            for col in TICKER_COLUMNS:
                if col in table.columns:
                    ticker_column = col
                    break
            
            if ticker_column:
                logger.debug(f"Found ticker column '{ticker_column}' for S&P 500.")
                # Use the found ticker column to extract symbols
                symbols = table[ticker_column].astype(str).tolist()
                return symbols
        
        # Fallback if the expected table isn't found
        logger.warning(f"Could not find a valid ticker column in tables scraped from {url} for S&P 500.")
        return []
    except Exception as e:
        logger.error(f"Error scraping S&P 500 symbols from {url}: {e}", exc_info=True)
        return []

def _get_nasdaq100_symbols() -> List[str]:
    """Scrapes NASDAQ-100 symbols from Wikipedia using a robust column search."""
    url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
    try:
        logger.debug(f"Attempting to fetch HTML from {url} with custom User-Agent.")
        
        # FIX: Use requests with a User-Agent to prevent 403 Forbidden errors
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status() # Check for HTTP errors like 403
        
        tables = pd.read_html(response.text) # Pass the content string to read_html
        
        # Define common column names that hold the ticker symbol
        TICKER_COLUMNS = ['Ticker', 'Symbol', 'Security']
        ticker_column = None
        
        for table in tables:
            # Check if any of the common ticker column names are present
            for col in TICKER_COLUMNS:
                if col in table.columns:
                    ticker_column = col
                    break
            
            if ticker_column:
                logger.debug(f"Found ticker column '{ticker_column}' for NASDAQ-100.")
                # Use the found ticker column to extract symbols
                symbols = table[ticker_column].astype(str).tolist()
                return symbols
        
        # Fallback if the expected table isn't found
        logger.warning(f"Could not find a valid ticker column in tables scraped from {url} for NASDAQ-100.")
        return []
    except Exception as e:
        logger.error(f"Error scraping NASDAQ-100 symbols from {url}: {e}", exc_info=True)
        return []

def _get_ftse100_symbols() -> List[str]:
    """Scrapes FTSE 100 symbols from Wikipedia, appending '.L' for Yahoo Finance compatibility."""
    url = 'https://en.wikipedia.org/wiki/FTSE_100_Index'
    try:
        logger.debug(f"Attempting to fetch HTML from {url} with custom User-Agent.")

        # FIX: Use requests with a User-Agent to prevent 403 Forbidden errors
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status() # Check for HTTP errors like 403
        
        tables = pd.read_html(response.text) # Pass the content string to read_html
        
        # Define common column names that hold the ticker symbol on the FTSE page
        TICKER_COLUMNS = ['Ticker', 'TIDM', 'Code']
        ticker_column = None
        
        for table in tables:
            # Check if any of the common ticker column names are present
            for col in TICKER_COLUMNS:
                if col in table.columns:
                    ticker_column = col
                    break
            
            if ticker_column:
                logger.debug(f"Found ticker column '{ticker_column}' for FTSE 100. Applying '.L' suffix.")
                # Yahoo Finance uses a '.L' suffix for most London Stock Exchange symbols
                # We use the found ticker_column to extract symbols
                symbols = [f"{ticker}.L" for ticker in table[ticker_column].astype(str).tolist()]
                return symbols
                
        # Fallback if the expected table isn't found
        logger.warning(f"Could not find a valid ticker column in tables scraped from {url} for FTSE 100.")
        return []
    except Exception as e:
        logger.error(f"Error scraping FTSE 100 symbols from {url}: {e}", exc_info=True)
        return []

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


def get_major_index_symbols(index_name: str) -> Dict[str, Any]:
    """
    Retrieves the actual, current list of stock symbols for a specified major index 
    by scraping public data sources like Wikipedia.

    Args:
        index_name: The name of the index ('FTSE100', 'NASDAQ100', 'SP500', 'DOWJONES').
                    Case-insensitive.

    Returns:
        A dictionary containing the index name and a list of symbols, or an 
        'error' message if the index name is not recognized or scraping fails.
    """
    index_name_upper = index_name.upper().replace(' ', '').replace('-', '').replace('_', '')
    
    # Map index names to scraping functions
    scraper_map = {
        'SP500': _get_sp500_symbols,
        'NASDAQ100': _get_nasdaq100_symbols,
        'FTSE100': _get_ftse100_symbols,
        # Dow Jones Industrial Average is only 30 stocks, so we use a reliable, small list.
        'DOWJONES': lambda: ['AAPL', 'AMGN', 'AXP', 'BA', 'CAT', 'CRM', 'CSCO', 'CVX', 'DIS', 'GS', 'HD', 'HON', 'IBM', 'INTC', 'JNJ', 'JPM', 'KO', 'MCD', 'MMM', 'MRK', 'MSFT', 'NKE', 'PG', 'TRV', 'UNH', 'V', 'VZ', 'WBA', 'WMT', 'DOW'], 
    }
    
    if index_name_upper in scraper_map:
        symbols = scraper_map[index_name_upper]()
        
        if symbols:
            return {
                'index_name': index_name_upper,
                'symbols': symbols,
                'count': len(symbols),
                'source': 'Wikipedia via pandas_read_html'
            }
        else:
            return {
                'index_name': index_name_upper,
                'symbols': [],
                'error': f"Failed to scrape symbols for {index_name_upper}. The source structure may have changed."
            }
    else:
        # Fallback for unrecognized index
        return {
            'index_name': 'Unknown',
            'symbols': [],
            'error': f"Index '{index_name}' not recognized. Supported indices are: {', '.join(scraper_map.keys())}"
        }

# --- ADK Agent Definition ---

# The root_agent is the entry point for the ADK application.
root_agent = LlmAgent(
    name="Financial_Analysis_Agent",
    model="gemini-2.5-flash",
    description="A specialist financial assistant that uses market data tools to answer questions about stock prices, historical performance, and index constituents.",
    instruction="You are a helpful and professional financial analyst. Use the provided tools (get_last_stock_price, get_aggregated_stock_data, and get_major_index_symbols) to answer any user queries about stock information. Use the get_major_index_symbols tool when the user asks for a list of symbols in a major index like FTSE 100, NASDAQ 100, or S&P 500.",
    tools=[
        get_last_stock_price,
        get_aggregated_stock_data,
        get_major_index_symbols,
    ],
)
