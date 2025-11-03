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
import numpy as np # Required for financial calculations (log returns, statistics)

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


def get_risk_free_rate(exchange_or_country: str) -> Dict[str, Any]:
    """
    Retrieves the current annualized risk-free rate (R_f), typically proxied by
    the yield on the relevant country's 10-Year Government Bond, for use
    in financial models like CAPM.

    Args:
        exchange_or_country: The country or major exchange to determine the
                             appropriate risk-free rate (e.g., 'US', 'UK', 'Japan', 'NYSE', 'LSE').

    Returns:
        A dictionary containing the rate as an annual decimal (e.g., 0.045 for 4.5%),
        its source symbol, or an error.
    """
    lookup = exchange_or_country.upper().strip()
    
    # Map exchange/country/market to a 10-Year government bond yield ticker (proxy)
    # NOTE: These indices return the yield as a percentage (e.g., 4.5)
    rate_proxies = {
        'US': '^TNX',       # CBOE 10 Year Treasury Note Yield (standard US proxy)
        'USA': '^TNX',
        'NASDAQ': '^TNX',
        'NYSE': '^TNX',
        # The UK proxy (^FTSE-GILT10) is often unreliable on yfinance. 
        # We temporarily set the UK risk-free rate to the US proxy (^TNX), 
        # which is a common practical substitute when local bond data fails.
        'UK': '^TNX', 
        'LSE': '^TNX', 
        'JAPAN': '^N225',   # Nikkei 225 Index - Market index context (less reliable as yield)
        'TOKYO': '^N225',
    }
    
    # Default to the most common risk-free rate proxy: US 10-Year Treasury Yield
    rate_ticker = rate_proxies.get(lookup, '^TNX') 

    try:
        ticker = yf.Ticker(rate_ticker)
        rate_info = ticker.info
        rate_percent = rate_info.get('regularMarketPrice')
        
        if rate_percent is None:
            rate_percent = rate_info.get('currentPrice')
            
        if rate_percent is None:
            raise ValueError(f"Could not retrieve a valid yield price for {rate_ticker}.")
        
        # The yield is typically given as a percentage (e.g., 4.5 for 4.5%).
        # We return it as a float decimal (0.045) for calculation purposes.
        return {
            'rate_decimal_annual': round(float(rate_percent) / 100.0, 6),
            'rate_symbol': rate_ticker,
            'note': 'This is an annualized yield used as a risk-free proxy for CAPM. It is returned as a decimal (e.g., 0.045).'
        }
    
    except Exception as e:
        return {'error': f"Failed to fetch risk-free rate proxy ({rate_ticker}) for {exchange_or_country}: {e}"}


def get_historical_market_return(index_symbol: str, period: str) -> Dict[str, Any]:
    """
    Calculates the historical annualized return of a major market index (E(R_m)). 
    This is used as a proxy for the Expected Market Return in CAPM.
    
    Args:
        index_symbol: The ticker symbol of the market index (e.g., '^GSPC' for S&P 500, '^FTSE' for FTSE 100).
        period: The data period for calculation (e.g., '1y', '5y', 'max').

    Returns:
        A dictionary with the annualized return as an annual decimal (e.g., 0.10 for 10%),
        or an error message.
    """
    try:
        # Fetch daily closing prices for the index.
        data_obj = yf.download(index_symbol, period=period, interval='1d', progress=False)['Close']
        
        # FIX: Check if the result is a DataFrame (which should have been a Series for single-symbol download)
        # The 'tolist' error is fixed by explicitly extracting the single Series if a DataFrame is returned.
        if isinstance(data_obj, pd.DataFrame):
            # Extract the Series from the DataFrame (assuming it's a single column)
            data_series = data_obj.iloc[:, 0]
        else:
            data_series = data_obj
            
        data_series = data_series.dropna()
        
        if data_series.empty or len(data_series) < 20: 
            return {'error': f"Insufficient data available for calculation for {index_symbol} over period {period}. Requires daily data."}

        # Convert the Series to a standard Python list of floats 
        # to prevent Pydantic serialization errors in the event of a trace/logging failure.
        index_prices = data_series.tolist()
        
        # Calculate total period return using standard list indexing
        total_return = (index_prices[-1] / index_prices[0]) - 1
        
        # Annualize the return based on the number of years in the period
        # Assumes approximately 252 trading days per year
        num_years = len(index_prices) / 252.0
        
        # Simple annualized return approximation
        if num_years > 0:
            annualized_return = ((1 + total_return) ** (1/num_years)) - 1
        else:
            annualized_return = 0

        # Note: The user asked for "real" return. This function calculates the 
        # NOMINAL return. The real return is (1 + Nominal) / (1 + Inflation Rate) - 1.
        return {
            'index_symbol': index_symbol,
            'period': period,
            'annualized_market_return_decimal': round(annualized_return, 6),
            'note': 'This is the historical **nominal** annualized return, commonly used as a proxy for the Expected Market Return (E(R_m)) in CAPM. To calculate the **real** return, you must subtract the expected inflation rate.'
        }

    except Exception as e:
        # The exception message is guaranteed to be serializable
        return {'error': f"Failed to calculate historical annualized market return for {index_symbol}: {e}"}


def calculate_beta_and_volatility(stock_symbol: str, market_index_symbol: str, period: str) -> Dict[str, Any]:
    """
    Calculates the stock's Beta (a measure of systematic risk used in CAPM) relative 
    to a market index and its annualized volatility over a specified period.
    
    The market index symbol should typically be a major index (e.g., '^GSPC' for S&P 500, 
    '^FTSE' for FTSE 100, '^IXIC' for NASDAQ Composite).

    Args:
        stock_symbol: The ticker symbol of the stock (e.g., 'AAPL').
        market_index_symbol: The ticker symbol of the market index (e.g., '^GSPC').
        period: The data period for calculation (e.g., '1y', '5y', 'max'). Daily ('1d')
                interval is used for calculation regardless of the period length.

    Returns:
        A dictionary with Beta, Annualized Volatility (Stock), and Annualized Volatility (Market Index),
        or an error message.
    """
    try:
        # Fetch daily closing prices for both assets. This returns a DataFrame with columns for each symbol.
        data = yf.download([stock_symbol, market_index_symbol], period=period, interval='1d', progress=False)['Close']

        # Drop any rows with missing data
        data = data.dropna()
        
        if data.empty or len(data) < 20: # Require at least 20 data points for meaningful calculation
            return {'error': f"Insufficient data available for calculation for {stock_symbol} and {market_index_symbol} over period {period}."}

        # Calculate daily log returns
        stock_returns = np.log(data[stock_symbol] / data[stock_symbol].shift(1)).dropna()
        market_returns = np.log(data[market_index_symbol] / data[market_index_symbol].shift(1)).dropna()

        # Align the returns data (important for correlation)
        # We ensure they are the same length after the shift(1) operation
        min_len = min(len(stock_returns), len(market_returns))
        stock_returns = stock_returns[-min_len:]
        market_returns = market_returns[-min_len:]
        
        if min_len < 20:
             return {'error': f"Insufficient aligned data (only {min_len} days) available for calculation for {stock_symbol} and {market_index_symbol} over period {period}."}


        # 1. Calculate Beta
        # Using numpy's polyfit (linear regression) for OLS: y = alpha + beta*x
        # where y is stock returns and x is market returns
        # The result of np.polyfit is [beta, alpha_intercept]
        beta, _ = np.polyfit(market_returns, stock_returns, 1)

        # 2. Calculate Annualized Volatility (Standard Deviation of returns)
        # Assumes approximately 252 trading days per year
        annualization_factor = np.sqrt(252)
        stock_volatility = stock_returns.std() * annualization_factor
        market_volatility = market_returns.std() * annualization_factor
        
        # 3. Calculate Annualized Return (Optional but useful for context)
        # Calculate total period return
        stock_total_return = (data[stock_symbol].iloc[-1] / data[stock_symbol].iloc[0]) - 1
        
        # Annualize the return based on the number of years in the period
        num_years = len(data) / 252.0
        # Simple annualized return approximation
        stock_annualized_return = ((1 + stock_total_return) ** (1/num_years)) - 1 if num_years > 0 else 0

        return {
            'stock_symbol': stock_symbol,
            'market_index_symbol': market_index_symbol,
            'period': period,
            'beta': round(beta, 4),
            'stock_annualized_return': round(stock_annualized_return * 100, 2), # %
            'stock_annualized_volatility': round(stock_volatility * 100, 2), # %
            'market_annualized_volatility': round(market_volatility * 100, 2), # %
            'note': 'Beta > 1 indicates higher systematic risk than the market.'
        }

    except Exception as e:
        return {'error': f"Financial calculation failed for {stock_symbol} against {market_index_symbol}: {e}"}


def compare_key_metrics(symbols: List[str], period: str) -> Dict[str, Any]:
    """
    Compares key historical performance metrics (Total Return and Annualized Volatility) 
    for a list of stocks over a specified period.

    Args:
        symbols: A list of stock ticker symbols (e.g., ['AAPL', 'MSFT', 'GOOGL']).
        period: The data period for calculation (e.g., '1y', '3y', 'max').

    Returns:
        A dictionary containing the comparison results for all symbols, or an error.
    """
    results = {}
    
    try:
        # Fetch daily closing prices for all assets
        data = yf.download(symbols, period=period, interval='1d', progress=False)['Close']
        
        # If only one symbol is requested, the output is a Series, not a DataFrame
        if isinstance(data, pd.Series):
            data = data.to_frame()
        
        data = data.dropna(axis=1, how='all') # Drop columns where all values are NaN
        
        if data.empty:
            return {'error': f"No sufficient data available for any of the symbols over period {period}."}

        for symbol in symbols:
            if symbol not in data.columns:
                 results[symbol] = {'error': f"Failed to retrieve data for {symbol}."}
                 continue

            stock_prices = data[symbol].dropna()

            if len(stock_prices) < 20:
                results[symbol] = {'error': f"Insufficient data (only {len(stock_prices)} days) for calculation."}
                continue

            # Calculate daily log returns
            stock_returns = np.log(stock_prices / stock_prices.shift(1)).dropna()

            # 1. Total Return
            total_return = (stock_prices.iloc[-1] / stock_prices.iloc[0]) - 1

            # 2. Annualized Volatility (Standard Deviation of returns)
            annualization_factor = np.sqrt(252) # Assumes 252 trading days
            annualized_volatility = stock_returns.std() * annualization_factor

            # 3. Annualized Return
            num_years = len(stock_prices) / 252.0
            annualized_return = ((1 + total_return) ** (1/num_years)) - 1 if num_years > 0 else 0

            results[symbol] = {
                'total_return_percent': round(total_return * 100, 2),
                'annualized_return_percent': round(annualized_return * 100, 2),
                'annualized_volatility_percent': round(annualized_volatility * 100, 2),
            }

    except Exception as e:
        return {'error': f"Comparison failed: {e}"}
        
    return {'comparison_period': period, 'results': results}


def generate_time_series_chart_data(symbol: str, period: str, metric: str) -> Dict[str, Any]:
    """
    Retrieves time-series data for a specified stock and metric, formatted for visualization.
    This function outputs the raw data points that can be used by a frontend application
    to generate line charts or time-series plots.

    Args:
        symbol: The stock ticker symbol (e.g., 'TSLA').
        period: The data period (e.g., '1mo', '6mo', '1y', '5y').
        metric: The data point to plot ('Close', 'Open', 'High', 'Low', 'Volume').

    Returns:
        A dictionary containing chart metadata and the time-series data array, or an error.
    """
    valid_metrics = ['Close', 'Open', 'High', 'Low', 'Volume']
    if metric not in valid_metrics:
        return {'error': f"Invalid metric '{metric}'. Must be one of: {', '.join(valid_metrics)}"}
    
    try:
        # Fetch daily data for the specified period
        data = yf.download(symbol, period=period, interval='1d', progress=False)
        
        if data.empty:
            return {'error': f"No data found for {symbol} over the period {period}."}

        if metric not in data.columns:
            return {'error': f"Metric '{metric}' not available in the fetched data for {symbol}."}

        # Format data points for plotting: [{date: ..., value: ...}, ...]
        chart_data = []
        for index, row in data.iterrows():
            # Convert timestamp to ISO format string
            date_str = index.strftime('%Y-%m-%d')
            value = row[metric]
            
            # Round financial values but keep Volume as integer
            if metric == 'Volume':
                value = int(value)
            else:
                value = round(value, 4)

            chart_data.append({
                'date': date_str,
                'value': value
            })

        return {
            'symbol': symbol,
            'metric': metric,
            'period': period,
            'title': f"{symbol} {metric} Price over {period}",
            'data_points': chart_data
        }

    except Exception as e:
        return {'error': f"Failed to generate chart data for {symbol}: {e}"}


# --- ADK Agent Definition ---

# The root_agent is the entry point for the ADK application.
root_agent = LlmAgent(
    name="Financial_Analysis_Agent",
    model="gemini-2.5-flash",
    description="A specialist financial assistant that uses market data tools to answer questions about stock prices, historical performance, risk metrics (Beta), index constituents, time-series data for visualization, risk-free rate, and historical market returns (E(R_m)).",
    instruction="You are a helpful and professional financial analyst. Use the provided tools (get_last_stock_price, get_aggregated_stock_data, get_major_index_symbols, calculate_beta_and_volatility, compare_key_metrics, generate_time_series_chart_data, get_risk_free_rate, and get_historical_market_return) to answer any user queries about stock information and financial metrics, including CAPM calculations.",
    tools=[
        get_last_stock_price,
        get_aggregated_stock_data,
        get_major_index_symbols,
        calculate_beta_and_volatility,
        compare_key_metrics,
        generate_time_series_chart_data,
        get_risk_free_rate, 
        get_historical_market_return, 
    ],
)
