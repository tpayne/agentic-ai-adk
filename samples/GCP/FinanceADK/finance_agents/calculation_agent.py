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
import os

# Use in-memory cache for robustness in containerized environments
# Cache expiration set to 60 seconds to provide near real-time data
requests_cache.install_cache(backend="memory", expire_after=60)

# --- logging ---
logger = logging.getLogger("calculation_agent")
logging.basicConfig(level=logging.WARNING)
# Get log level from environment variable, default to WARNING
LOGLEVEL = os.getenv("LOGLEVEL", "WARNING").upper()
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
    if logger: logger.setLevel(LOGLEVEL)
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


# --- New Technical Indicator Tools ---
def get_technical_indicators(
    symbol: str, 
    period: str, 
    short_window: int = 12, 
    long_window: int = 26, 
    signal_window: int = 9, 
    ma_window: int = 20
) -> Dict[str, Any]:
    """
    Calculates key technical indicators: Simple Moving Average (SMA), Relative Strength Index (RSI), 
    and Moving Average Convergence Divergence (MACD) for a given stock symbol.

    Args:
        symbol: The stock symbol (e.g., 'AAPL', 'TSLA').
        period: The period over which to retrieve data (e.g., '1y', '6mo').
        short_window: The period for the fast EMA in MACD (default 12).
        long_window: The period for the slow EMA in MACD (default 26).
        signal_window: The period for the signal line in MACD (default 9).
        ma_window: The period for the Simple Moving Average (default 20).

    Returns:
        A dictionary containing the latest calculated values for all indicators.
    """
    try:
        # Fetch daily data
        data = yf.download(symbol, period=period, interval='1d', progress=False)
        data['Close'] = data['Close'].ffill() # Forward fill any NaN prices
        
        if data.empty:
            return {"error": f"No data found for {symbol} over the period {period}."}
        
        # --- 1. Simple Moving Average (SMA) ---
        data['SMA'] = data['Close'].rolling(window=ma_window).mean()

        # --- 2. Moving Average Convergence Divergence (MACD) ---
        data['EMA_Short'] = data['Close'].ewm(span=short_window, adjust=False).mean()
        data['EMA_Long'] = data['Close'].ewm(span=long_window, adjust=False).mean()
        data['MACD_Line'] = data['EMA_Short'] - data['EMA_Long']
        data['Signal_Line'] = data['MACD_Line'].ewm(span=signal_window, adjust=False).mean()
        data['MACD_Histogram'] = data['MACD_Line'] - data['Signal_Line']

        # --- 3. Relative Strength Index (RSI) ---
        delta = data['Close'].diff(1)
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.ewm(com=14 - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=14 - 1, adjust=False).mean()

        rs = avg_gain / avg_loss
        data['RSI'] = 100 - (100 / (1 + rs))

        # --- Final Data Preparation ---
        # Ensure we only consider rows where all indicators have been calculated
        data.dropna(inplace=True)

        if data.empty:
            # Handle case where there isn't enough data (e.g., period is too short)
            return {
                "symbol": symbol,
                "error": f"Insufficient trading days (less than {max(long_window, 14)} days) to calculate technical indicators for {symbol} over {period}."
            }

        # --- FIX: Extract latest values as native Python types using .item() ---
        try:
            latest_close_price = data['Close'].iloc[-1].item() 
            latest_sma = data['SMA'].iloc[-1].item()
            latest_rsi = data['RSI'].iloc[-1].item()
            latest_macd_line = data['MACD_Line'].iloc[-1].item()
            latest_macd_signal = data['Signal_Line'].iloc[-1].item()
            latest_macd_histogram = data['MACD_Histogram'].iloc[-1].item()
        except Exception as e:
            return {'error': f"Failed to extract final indicator values due to a data type issue: {e}"}

        # Return a dictionary containing only standard Python types
        return {
            "symbol": symbol.upper(),
            "period": period,
            "latest_close_price": round(latest_close_price, 2),
            "latest_sma": round(latest_sma, 2),
            "latest_rsi": round(latest_rsi, 2),
            "latest_macd_line": round(latest_macd_line, 4),
            "latest_macd_signal": round(latest_macd_signal, 4),
            "latest_macd_histogram": round(latest_macd_histogram, 4),
            "note": "RSI above 70 is overbought, below 30 is oversold. A positive MACD Histogram (MACD Line > Signal Line) suggests upward momentum."
        }

    except Exception as e:
        return {"error": f"Failed to calculate technical indicators for {symbol}: {e}"}

def get_on_balance_volume(symbol: str, period: str) -> Dict[str, Any]:
    """
    Calculates the On-Balance Volume (OBV) for a given stock symbol and time period.

    Args:
        symbol: The stock symbol (e.g., 'AAPL', 'MSFT').
        period: The period over which to retrieve data (e.g., '1y', '6mo').

    Returns:
        A dictionary containing the latest calculated On-Balance Volume value.
    """
    try:
        # Fetch daily data
        data = yf.download(symbol, period=period, interval='1d', progress=False)
        
        # 1. Robust Data Preparation: Select only necessary columns and drop rows with any missing data
        # Explicitly select 'Close' and 'Volume' and drop rows where either is NaN.
        data = data[['Close', 'Volume']].dropna()

        if data.empty or len(data) < 2:
            return {"error": f"Insufficient data (less than 2 valid days of Close/Volume) to calculate OBV for {symbol} over {period}. Data check failed."}

        # 2. Calculate the price change direction: 1, -1, or 0
        # The .diff() creates NaN on the first row. .fillna(0) correctly initializes the OBV starting point.
        price_direction = np.sign(data['Close'].diff()).fillna(0)
        
        # 3. Calculate the daily volume contribution (Volume * Direction)
        # We explicitly convert Volume to a 64-bit integer (np.int64) for maximum robustness against volume type errors.
        data['Volume_Contribution'] = data['Volume'].astype(np.int64) * price_direction
        
        # 4. Calculate On-Balance Volume (OBV) as the cumulative sum
        data['OBV'] = data['Volume_Contribution'].cumsum()
        
        # 5. Final Extraction and Type Safety
        latest_obv_scalar = data['OBV'].iloc[-1]
        
        if pd.isna(latest_obv_scalar):
             return {"error": "Latest OBV value is NaN. Calculation produced an invalid result."}

        # FIX: Use .item() to ensure serialization, and explicitly cast to int for the final return
        latest_obv = int(latest_obv_scalar.item())

        return {
            "symbol": symbol.upper(),
            "period": period,
            "latest_on_balance_volume": latest_obv,
            "note": "OBV confirms price trends. If price rises but OBV falls, it suggests a weak move."
        }

    except Exception as e:
        # Return a descriptive error message including the internal exception type and message
        return {"error": f"Failed to calculate On-Balance Volume for {symbol}. Internal error: {type(e).__name__}: {str(e)}"}    

def calculate_ebitda(symbol: str) -> Dict[str, Any]:
    """
    Calculates the most recent annual EBITDA (Earnings Before Interest, Taxes,
    Depreciation, and Amortization) for a specified stock symbol.

    Args:
        symbol: The stock ticker symbol (e.g., 'AAPL', 'MSFT').

    Returns:
        A dictionary containing the symbol and the calculated EBITDA value (as a float),
        or an 'error' message if the data cannot be retrieved.
    """
    try:
        ticker = yf.Ticker(symbol)
        
        # 1. Attempt to get explicit EBITDA from .info (quickest method)
        info = ticker.info
        ebitda_value = info.get('ebitda')
        
        if ebitda_value is not None and ebitda_value != 0:
            return {
                'symbol': symbol.upper(),
                'ebitda': float(ebitda_value),
                'source': 'info'
            }

        # 2. Fallback: Calculate from annual financial statements using the add-back method
        # Financials DataFrame contains annual income statement data
        financials = ticker.financials
        
        if financials.empty:
            return {'error': f"Failed to retrieve financial statements for {symbol}. Cannot calculate EBITDA."}

        # Get the most recent annual column (the first one)
        latest_financials = financials.iloc[:, 0]
        
        # Keys for the add-back method: Net Income + Interest + Taxes + D&A
        net_income = latest_financials.get('Net Income')
        interest_expense = latest_financials.get('Interest Expense') or latest_financials.get('Interest Expense Non Operating') or 0
        tax_provision = latest_financials.get('Tax Provision')
        depreciation_amortization = latest_financials.get('Depreciation And Amortization')

        # Check for mandatory components
        if net_income is None or tax_provision is None or depreciation_amortization is None:
            # Report missing data
            missing_components = [
                k for k, v in {
                    'Net Income': net_income, 
                    'Tax Provision': tax_provision, 
                    'Depreciation And Amortization': depreciation_amortization
                }.items() if v is None
            ]
            return {'error': f"Failed to calculate EBITDA for {symbol}. Missing key financial components: {', '.join(missing_components)}."}

        # Calculate EBITDA: Net Income + Interest Expense + Tax Provision + D&A
        calculated_ebitda = net_income + interest_expense + tax_provision + depreciation_amortization
        
        return {
            'symbol': symbol.upper(),
            'ebitda': float(calculated_ebitda),
            'source': 'calculated_from_NetIncome_addback'
        }

    except Exception as e:
        logger.error(f"Error calculating EBITDA for {symbol}: {e}")
        return {'error': f"Failed to calculate EBITDA for {symbol}. Internal error: {type(e).__name__}: {str(e)}"}

def get_pe_ratio(symbol: str) -> Dict[str, Any]:
    """
    Retrieves the Price-to-Earnings (P/E) ratio for a given stock symbol.
    The P/E Ratio is a key valuation metric.

    Args:
        symbol: The stock ticker symbol (e.g., 'AAPL', 'MSFT').

    Returns:
        A dictionary containing the P/E ratio or an error message.
    """
    try:
        ticker = yf.Ticker(symbol)
        # Attempt to get the trailing P/E ratio directly from info, which is a common source of error.
        pe_ratio = ticker.info.get('trailingPE')
        
        if pe_ratio is not None and pe_ratio > 0:
            return {
                "symbol": symbol,
                "price_to_earnings_ratio": pe_ratio,
                "note": "P/E ratio successfully retrieved from fundamental data."
            }
        else:
            # Fallback for missing/bad data
            return {
                "symbol": symbol,
                "error": "P/E Ratio data is missing or zero/negative. Cannot be calculated.",
                "note": "The data endpoint for fundamental data may be unstable or the P/E ratio is not applicable/missing."
            }

    except Exception as e:
        return {"error": f"Failed to get P/E ratio for {symbol}. Internal error: {type(e).__name__}: {str(e)}"}

def calculate_sharpe_ratio(
    symbol: str,
    risk_free_rate: float,
    period: str = "5y",
    interval: str = "1d",
    trading_days: int = 252,
    auto_adjust: bool = True
) -> Dict[str, Any]:
    """
    Calculates the Annualized Sharpe Ratio for a stock over a given period.

    Args:
        symbol: The stock ticker (e.g., 'MSFT').
        risk_free_rate: The annual risk-free rate (as a percentage, e.g., 4.5 for 4.5%).
        period: The time frame for historical data (e.g., '1y', '5y').
        interval: Data interval (default '1d').
        trading_days: Number of trading days per year for annualization (default 252).
        auto_adjust: Pass explicitly to yf.download to control adjusted prices (default True).

    Returns:
        A dictionary with symbol, period, risk_free_rate_percent, sharpe_ratio,
        annualized_return, annualized_volatility, or an error entry.
    """
    try:
        rf_rate_decimal = float(risk_free_rate) / 100.0

        # Explicitly pass auto_adjust to avoid FutureWarning from yfinance
        data = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=auto_adjust
        )

        if data is None or data.empty:
            return {"symbol": symbol, "error": f"Could not retrieve historical data for {symbol} over {period}."}

        # Choose price column:
        # - if auto_adjust is True, yfinance returns adjusted prices in the 'Close' column;
        # - if auto_adjust is False, prefer 'Adj Close' when present, otherwise 'Close'.
        if auto_adjust:
            price_col = "Close"
        else:
            price_col = "Adj Close" if "Adj Close" in data.columns else "Close"

        if price_col not in data.columns:
            return {"symbol": symbol, "error": f"No Close or Adj Close column found for {symbol}."}

        prices = data[price_col].astype(float).dropna()
        if prices.size < 2:
            return {"symbol": symbol, "error": f"Insufficient price data for {symbol} to compute returns."}

        # Log returns
        returns = np.log(prices / prices.shift(1)).dropna()
        if returns.size < 2:
            return {"symbol": symbol, "error": f"Insufficient non-NaN return data for {symbol}."}

        # Compute scalars safely using .item() to avoid FutureWarning about float(Series)
        mean_return_scalar = returns.mean()
        std_dev_scalar = returns.std(ddof=1)

        # mean_return_scalar and std_dev_scalar should be scalar numpy types; extract safely
        mean_return = float(mean_return_scalar.item()) * trading_days
        std_dev = float(std_dev_scalar.item()) * np.sqrt(trading_days)

        if np.isnan(std_dev) or std_dev <= 1e-12:
            return {"symbol": symbol, "error": f"Annualized volatility is zero or NaN for {symbol}."}

        sharpe_ratio = (mean_return - rf_rate_decimal) / std_dev

        return {
            "symbol": symbol,
            "period": period,
            "risk_free_rate_percent": float(risk_free_rate),
            "sharpe_ratio": round(float(sharpe_ratio), 6),
            "annualized_return": round(float(mean_return), 6),
            "annualized_volatility": round(float(std_dev), 6)
        }

    except Exception as e:
        return {"symbol": symbol, "error": f"Internal error: {type(e).__name__}: {str(e)}"}
 
def calculate_sortino_ratio(symbol: str, risk_free_rate: float, period: str = "5y") -> Dict[str, Any]:
    """
    Calculates the Annualized Sortino Ratio for a stock over a given period, focusing only on downside volatility.
    """
    try:
        rf_rate_decimal = float(risk_free_rate) / 100.0
        # explicitly set auto_adjust to avoid yfinance FutureWarning and to return adjusted prices
        data = yf.download(symbol, period=period, interval="1d", progress=False, auto_adjust=True)

        if data is None or data.empty:
            return {"symbol": symbol, "error": f"Sortino Ratio failed: Could not retrieve historical data for {symbol}."}

        # With auto_adjust=True, 'Close' is already adjusted; otherwise prefer 'Adj Close'
        price_col = "Close" if "Close" in data.columns else ("Adj Close" if "Adj Close" in data.columns else None)
        if price_col is None:
            return {"symbol": symbol, "error": f"Sortino Ratio failed: No Close/Adj Close column for {symbol}."}

        prices = data[price_col].astype(float).dropna()
        if prices.size < 2:
            return {"symbol": symbol, "error": f"Sortino Ratio failed: Insufficient price data for {symbol}."}

        # use simple arithmetic returns for Sortino
        returns = prices.pct_change().dropna()
        if returns.size < 2:
            return {"symbol": symbol, "error": f"Sortino Ratio failed: Insufficient return data for {symbol}."}

        trading_days = 252

        # Minimum acceptable return (daily)
        mar_daily = (1 + rf_rate_decimal) ** (1 / trading_days) - 1

        # downside deviations: only values below MAR, measured as (min(0, r - MAR))
        downside_diff = np.minimum(0.0, returns - mar_daily)
        # downside variance = mean(square(downside_diff)); use population mean (ddof=0)
        downside_var_daily = np.nanmean(np.square(downside_diff))
        # if no downside observations, downside_var_daily will be 0.0 (or NaN if all NaN)
        if np.isnan(downside_var_daily) or downside_var_daily <= 0.0:
            return {"symbol": symbol, "error": f"Sortino Ratio failed: No downside returns or zero downside variance for {symbol}."}

        # annualize downside deviation
        downside_std = np.sqrt(downside_var_daily) * np.sqrt(trading_days)

        if np.isnan(downside_std) or downside_std <= 1e-12:
            return {"symbol": symbol, "error": f"Sortino Ratio failed: Annualized Downside Volatility is zero or NaN for {symbol}."}

        # annualized mean return (arithmetic)
        mean_return = float(returns.mean().item()) * trading_days

        # final Sortino: (annual_return - annual_rf) / annualized_downside_std
        sortino_ratio = (mean_return - rf_rate_decimal) / downside_std

        return {
            "symbol": symbol,
            "period": period,
            "risk_free_rate_percent": float(risk_free_rate),
            "sortino_ratio": round(float(sortino_ratio), 6),
            "annualized_return": round(float(mean_return), 6),
            "annualized_downside_volatility": round(float(downside_std), 6)
        }

    except Exception as e:
        return {"symbol": symbol, "error": f"Failed to calculate Sortino Ratio for {symbol}. Internal error: {type(e).__name__}: {str(e)}"}

def calculate_correlation_matrix(symbols: List[str], period: str = "5y") -> Dict[str, Any]:
    """
    Downloads historical data for multiple stocks and calculates the correlation matrix of their log returns.
    """
    if len(symbols) < 2:
        return {"error": "Correlation matrix requires at least two symbols."}

    try:
        # Explicitly set auto_adjust=True so Close is adjusted (avoids warning and accounts for dividends/splits)
        raw = yf.download(symbols, period=period, interval="1d", progress=False, auto_adjust=True)

        if raw is None or raw.empty:
            return {"error": f"Correlation matrix failed: could not retrieve data for symbols over {period}."}

        # If multiple tickers, yf.download returns a DataFrame; for multi-ticker it may be a panel-like DataFrame.
        # After auto_adjust=True, 'Close' should be present and adjusted; prefer 'Close' if present.
        if isinstance(raw, pd.DataFrame) and "Close" in raw.columns and raw.columns.nlevels == 2:
            # Multi-column with (field, symbol) structure: select Close field across symbols
            data = raw["Close"].copy()
        elif isinstance(raw, pd.DataFrame) and "Close" in raw.columns and raw.columns.nlevels == 1:
            # Single-level columns (when yfinance returns single ticker frame)
            data = raw[["Close"]].copy() if len(symbols) == 1 else raw["Close"] if "Close" in raw else raw
            # If selection yields a Series (single ticker), convert to DataFrame
            if isinstance(data, pd.Series):
                data = data.to_frame(name=symbols[0])
        else:
            # Fallback: try 'Adj Close' or assume raw is already a prices DataFrame
            if "Adj Close" in raw.columns:
                data = raw["Adj Close"].copy()
            else:
                # assume raw is already the price DataFrame
                data = raw.copy()

        # If data is a Series (single symbol), convert to DataFrame
        if isinstance(data, pd.Series):
            data = data.to_frame(name=symbols[0])

        # Drop symbols that failed entirely
        data.dropna(axis=1, how='all', inplace=True)

        # Need at least two columns after dropping
        if data.shape[1] < 2:
            return {"error": f"Correlation matrix failed: less than two symbols with valid data over {period}."}

        # Compute log returns aligned on common dates, then drop NaNs
        log_returns = np.log(data / data.shift(1)).dropna(how='all')

        if log_returns.empty or log_returns.shape[1] < 2:
            return {"error": f"Correlation matrix failed: Insufficient common return data for the provided symbols over {period}."}

        correlation_matrix = log_returns.corr()

        matrix_json = correlation_matrix.to_json(orient="index")

        return {
            "period": period,
            "symbols": list(correlation_matrix.columns),
            "correlation_matrix_json": matrix_json
        }

    except Exception as e:
        return {"error": f"Failed to calculate Correlation Matrix. Internal error: {type(e).__name__}: {str(e)}"}
    
# --- ADK Agent Definition ---

# The root_agent is the entry point for the ADK application.
calculation_agent = LlmAgent(
    name="calculation_agent",
    model="gemini-2.5-flash",
    description="A specialist financial assistant that uses market data tools to answer questions about stock prices, historical performance, risk metrics (Beta), index constituents, time-series data for visualization, risk-free rate, historical market returns (E(R_m)), and financial statement analysis (like EBITDA).",
    instruction="You are a helpful and professional financial analyst. Use the provided tools (get_last_stock_price, " \
    "get_aggregated_stock_data, get_major_index_symbols, calculate_beta_and_volatility, compare_key_metrics, " \
    "generate_time_series_chart_data, get_risk_free_rate, get_historical_market_return, get_technical_indicators, " \
    "get_on_balance_volume, calculate_sharpe_ratio, get_pe_ratio, calculate_sortino_ratio, calculate_correlation_matrix " \
    " and calculate_ebitda) to answer any user queries about stock information and financial metrics, " \
    "including CAPM calculations and technical analysis.",
    tools=[
        calculate_beta_and_volatility,
        calculate_ebitda,
        calculate_sharpe_ratio,
        calculate_sortino_ratio,
        calculate_correlation_matrix,     
        compare_key_metrics,
        generate_time_series_chart_data,
        get_aggregated_stock_data,
        get_historical_market_return, 
        get_last_stock_price,
        get_major_index_symbols,
        get_on_balance_volume,
        get_pe_ratio,      
        get_risk_free_rate, 
        get_technical_indicators,

    ],
)