
# calculation_agent.py
# VERSION: 2025-12-06.2
"""
ADK Calculation Agent with safe refactors and backward-compatible outputs.
Key updates vs original:
- Guarded logging (no duplicate handlers; LOGLEVEL env respected)
- Consistent **decimal** units for returns/vol; kept percent mirror fields in beta/vol tool
- New tool: get_daily_returns() for diversification inputs
- Safer risk-free proxy with override (RISK_FREE_RATE_OVERRIDE)
- Minor numerical consistency (ddof=1) and clearer notes
"""

from google.adk.agents import LlmAgent
from typing import Dict, List, Any

import yfinance as yf
import requests_cache
import logging
import pandas as pd
import requests
import numpy as np
import os

# --- Logging ---------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    level = os.getenv('LOGLEVEL', 'WARNING').upper()
    if level not in {'DEBUG','INFO','WARNING','ERROR','CRITICAL'}:
        level = 'WARNING'
    logger.setLevel(level)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(h)
    return logger

logger = get_logger('calculation_agent')

# Cache HTTP where possible
requests_cache.install_cache(backend='memory', expire_after=60)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Symbol scrapers -------------------------------------------------------

def _get_sp500_symbols() -> List[str]:
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        tables = pd.read_html(r.text)
        for tbl in tables:
            for col in ['Symbol','Ticker','Security']:
                if col in tbl.columns:
                    return tbl[col].astype(str).tolist()
        logger.warning('S&P500 symbols: expected column not found.')
        return []
    except Exception as e:
        logger.error(f'S&P500 scrape failed: {e}', exc_info=True)
        return []

def _get_nasdaq100_symbols() -> List[str]:
    url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        tables = pd.read_html(r.text)
        for tbl in tables:
            for col in ['Ticker','Symbol','Security']:
                if col in tbl.columns:
                    return tbl[col].astype(str).tolist()
        logger.warning('NASDAQ100 symbols: expected column not found.')
        return []
    except Exception as e:
        logger.error(f'NASDAQ100 scrape failed: {e}', exc_info=True)
        return []

def _get_ftse100_symbols() -> List[str]:
    url = 'https://en.wikipedia.org/wiki/FTSE_100_Index'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        tables = pd.read_html(r.text)
        for tbl in tables:
            for col in ['Ticker','TIDM','Code']:
                if col in tbl.columns:
                    return [f"{t}.L" for t in tbl[col].astype(str).tolist()]
        logger.warning('FTSE100 symbols: expected column not found.')
        return []
    except Exception as e:
        logger.error(f'FTSE100 scrape failed: {e}', exc_info=True)
        return []

# --- Tools -----------------------------------------------------------------

def get_last_stock_price(symbol: str) -> Dict[str, Any]:
    try:
        ti = yf.Ticker(symbol).info
        price = ti.get('regularMarketPrice') or ti.get('currentPrice')
        ts = ti.get('regularMarketTime') or 0
        if price is None:
            raise ValueError('No price field available')
        return {'symbol': symbol, 'price': float(price), 'timestamp': int(ts)}
    except Exception as e:
        return {'error': f'Failed to fetch last price for {symbol}: {e}'}

def get_aggregated_stock_data(symbol: str, interval: str, start_date: str, end_date: str) -> Dict[str, Any]:
    try:
        hist = yf.Ticker(symbol).history(start=start_date, end=end_date, interval=interval)
        data = [{
            'date': idx.strftime('%Y-%m-%d %H:%M:%S'),
            'open': round(row['Open'], 4),
            'high': round(row['High'], 4),
            'low': round(row['Low'], 4),
            'close': round(row['Close'], 4),
            'volume': int(row['Volume'])
        } for idx, row in hist.iterrows()]
        return {'symbol': symbol, 'interval': interval, 'data': data}
    except Exception as e:
        return {'error': f'Failed to fetch aggregated data for {symbol}: {e}'}

def get_major_index_symbols(index_name: str) -> Dict[str, Any]:
    idx = index_name.upper().replace(' ','').replace('-','').replace('_','')
    m = {'SP500': _get_sp500_symbols, 'NASDAQ100': _get_nasdaq100_symbols, 'FTSE100': _get_ftse100_symbols,
         'DOWJONES': lambda: ['AAPL','AMGN','AXP','BA','CAT','CRM','CSCO','CVX','DIS','GS','HD','HON','IBM','INTC','JNJ','JPM','KO','MCD','MMM','MRK','MSFT','NKE','PG','TRV','UNH','V','VZ','WBA','WMT','DOW']}
    if idx in m:
        syms = midx
        return {'index_name': idx, 'symbols': syms, 'count': len(syms), 'source': 'Wikipedia via pandas_read_html'} if syms else \
               {'index_name': idx, 'symbols': [], 'error': f'Failed to scrape symbols for {idx}.'}
    return {'index_name': 'Unknown', 'symbols': [], 'error': f"Index '{index_name}' not recognized. Supported: {', '.join(m.keys())}"}

def get_risk_free_rate(exchange_or_country: str) -> Dict[str, Any]:
    override = os.getenv('RISK_FREE_RATE_OVERRIDE')
    if override is not None:
        try:
            return {'rate_decimal_annual': round(float(override), 6), 'rate_symbol': 'override', 'note': 'Provided via env override.'}
        except Exception:
            pass
    proxy_map = {'US':'^TNX','USA':'^TNX','NASDAQ':'^TNX','NYSE':'^TNX','UK':'^TNX','LSE':'^TNX','JAPAN':'^TNX','TOKYO':'^TNX'}
    tick = proxy_map.get(exchange_or_country.upper().strip(), '^TNX')
    try:
        info = yf.Ticker(tick).info
        y = info.get('regularMarketPrice') or info.get('currentPrice')
        if y is None:
            raise ValueError('yield not available')
        return {'rate_decimal_annual': round(float(y)/100.0, 6), 'rate_symbol': tick, 'note': '10Y yield proxy; use override for non-US.'}
    except Exception as e:
        return {'error': f'Failed to fetch risk-free proxy ({tick}) for {exchange_or_country}: {e}'}

def get_historical_market_return(index_symbol: str, period: str) -> Dict[str, Any]:
    try:
        s = yf.download(index_symbol, period=period, interval='1d', progress=False)['Close']
        s = s.iloc[:,0] if isinstance(s, pd.DataFrame) else s
        s = s.dropna()
        if len(s) < 20:
            return {'error': f'Insufficient data for {index_symbol} over {period}.'}
        tr = (s.iloc[-1]/s.iloc[0]) - 1
        years = len(s)/252.0
        ann = ((1+tr)**(1/years))-1 if years>0 else 0.0
        return {'index_symbol': index_symbol, 'period': period, 'annualized_market_return_decimal': round(float(ann), 6), 'note': 'Nominal return.'}
    except Exception as e:
        return {'error': f'Failed to calculate market return for {index_symbol}: {e}'}

def calculate_beta_and_volatility(stock_symbol: str, market_index_symbol: str, period: str) -> Dict[str, Any]:
    try:
        data = yf.download([stock_symbol, market_index_symbol], period=period, interval='1d', progress=False)['Close'].dropna()
        if data.empty or len(data) < 20:
            return {'error': f'Insufficient data for {stock_symbol}/{market_index_symbol} over {period}.'}
        rs = np.log(data[stock_symbol]/data[stock_symbol].shift(1)).dropna()
        rm = np.log(data[market_index_symbol]/data[market_index_symbol].shift(1)).dropna()
        n = min(len(rs), len(rm))
        rs, rm = rs[-n:], rm[-n:]
        if n < 20:
            return {'error': f'Insufficient aligned data ({n} days).'}
        beta, _ = np.polyfit(rm, rs, 1)
        af = np.sqrt(252)
        sv = rs.std(ddof=1)*af
        mv = rm.std(ddof=1)*af
        tr = (data[stock_symbol].iloc[-1]/data[stock_symbol].iloc[0]) - 1
        years = len(data)/252.0
        ar = ((1+tr)**(1/years))-1 if years>0 else 0.0
        return {
            'stock_symbol': stock_symbol,
            'market_index_symbol': market_index_symbol,
            'period': period,
            'beta': round(float(beta),4),
            'stock_annualized_return': round(float(ar),6),
            'stock_annualized_volatility': round(float(sv),6),
            'market_annualized_volatility': round(float(mv),6),
            # backward-compatible mirror fields (percent)
            'stock_annualized_return_percent': round(float(ar)*100,2),
            'stock_annualized_volatility_percent': round(float(sv)*100,2),
            'market_annualized_volatility_percent': round(float(mv)*100,2),
            'note': 'Decimals + percent mirrors for backward compatibility.'
        }
    except Exception as e:
        return {'error': f'Financial calculation failed: {e}'}

def compare_key_metrics(symbols: List[str], period: str) -> Dict[str, Any]:
    out = {}
    try:
        data = yf.download(symbols, period=period, interval='1d', progress=False)['Close']
        if isinstance(data, pd.Series):
            data = data.to_frame()
        data = data.dropna(axis=1, how='all')
        if data.empty:
            return {'error': f'No sufficient data over {period}.'}
        for sym in symbols:
            if sym not in data.columns:
                out[sym] = {'error': 'No data'}; continue
            px = data[sym].dropna()
            if len(px) < 20:
                out[sym] = {'error': f'Only {len(px)} days'}; continue
            r = np.log(px/px.shift(1)).dropna()
            tr = (px.iloc[-1]/px.iloc[0]) - 1
            ann_vol = r.std(ddof=1)*np.sqrt(252)
            years = len(px)/252.0
            ann = ((1+tr)**(1/years))-1 if years>0 else 0.0
            out[sym] = {'total_return_percent': round(tr*100,2), 'annualized_return_percent': round(ann*100,2), 'annualized_volatility_percent': round(ann_vol*100,2)}
        return {'comparison_period': period, 'results': out}
    except Exception as e:
        return {'error': f'Comparison failed: {e}'}

def generate_time_series_chart_data(symbol: str, period: str, metric: str) -> Dict[str, Any]:
    if metric not in ['Close','Open','High','Low','Volume']:
        return {'error': f"Invalid metric '{metric}'."}
    try:
        df = yf.download(symbol, period=period, interval='1d', progress=False)
        if df.empty or metric not in df.columns:
            return {'error': f'No {metric} data for {symbol} over {period}'}
        pts = []
        for idx, row in df.iterrows():
            val = int(row[metric]) if metric=='Volume' else round(float(row[metric]),4)
            pts.append({'date': idx.strftime('%Y-%m-%d'), 'value': val})
        return {'symbol': symbol, 'metric': metric, 'period': period, 'title': f'{symbol} {metric} over {period}', 'data_points': pts}
    except Exception as e:
        return {'error': f'Chart data failed: {e}'}

def get_technical_indicators(symbol: str, period: str, short_window: int = 12, long_window: int = 26, signal_window: int = 9, ma_window: int = 20) -> Dict[str, Any]:
    try:
        df = yf.download(symbol, period=period, interval='1d', progress=False)
        if df.empty:
            return {'error': f'No data for {symbol} over {period}'}
        df['Close'] = df['Close'].ffill()
        df['SMA'] = df['Close'].rolling(window=ma_window).mean()
        df['EMA_Short'] = df['Close'].ewm(span=short_window, adjust=False).mean()
        df['EMA_Long'] = df['Close'].ewm(span=long_window, adjust=False).mean()
        df['MACD_Line'] = df['EMA_Short'] - df['EMA_Long']
        df['Signal_Line'] = df['MACD_Line'].ewm(span=signal_window, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD_Line'] - df['Signal_Line']
        delta = df['Close'].diff(1)
        gain = delta.where(delta>0, 0)
        loss = -delta.where(delta<0, 0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain/avg_loss
        df['RSI'] = 100 - (100/(1+rs))
        df.dropna(inplace=True)
        last = df.iloc[-1]
        return {
            'symbol': symbol.upper(), 'period': period,
            'latest_close_price': round(float(last['Close']),2),
            'latest_sma': round(float(last['SMA']),2),
            'latest_rsi': round(float(last['RSI']),2),
            'latest_macd_line': round(float(last['MACD_Line']),4),
            'latest_macd_signal': round(float(last['Signal_Line']),4),
            'latest_macd_histogram': round(float(last['MACD_Histogram']),4),
            'note': 'RSI>70 overbought, <30 oversold.'
        }
    except Exception as e:
        return {'error': f'Indicators failed: {e}'}

def get_on_balance_volume(symbol: str, period: str) -> Dict[str, Any]:
    try:
        df = yf.download(symbol, period=period, interval='1d', progress=False)[['Close','Volume']].dropna()
        if df.empty or len(df)<2:
            return {'error': f'Insufficient data for OBV ({symbol})'}
        direction = np.sign(df['Close'].diff()).fillna(0)
        df['OBV'] = (df['Volume'].astype(np.int64) * direction).cumsum()
        last = df['OBV'].iloc[-1]
        if pd.isna(last):
            return {'error': 'OBV NaN'}
        return {'symbol': symbol.upper(), 'period': period, 'latest_on_balance_volume': int(last)}
    except Exception as e:
        return {'error': f'OBV failed: {e}'}

def calculate_ebitda(symbol: str) -> Dict[str, Any]:
    try:
        t = yf.Ticker(symbol)
        info = t.info
        e = info.get('ebitda')
        if e:
            return {'symbol': symbol.upper(), 'ebitda': float(e), 'source': 'info'}
        fin = t.financials
        if fin.empty:
            return {'error': f'No financials for {symbol}'}
        latest = fin.iloc[:,0]
        ebit = latest.get('Ebit') or latest.get('Operating Income')
        da = latest.get('Depreciation And Amortization')
        if ebit is not None and da is not None:
            return {'symbol': symbol.upper(), 'ebitda': float(ebit+da), 'source': 'ebit_plus_da'}
        ni = latest.get('Net Income')
        ie = latest.get('Interest Expense') or latest.get('Interest Expense Non Operating') or 0
        tax = latest.get('Tax Provision')
        if ni is None or tax is None or da is None:
            return {'error': 'Missing components for EBITDA add-back'}
        return {'symbol': symbol.upper(), 'ebitda': float(ni+ie+tax+da), 'source': 'net_income_addback'}
    except Exception as e:
        logger.error(f'EBITDA failed: {e}')
        return {'error': f'EBITDA failed: {e}'}

def get_pe_ratio(symbol: str) -> Dict[str, Any]:
    try:
        pe = yf.Ticker(symbol).info.get('trailingPE')
        if pe and pe>0:
            return {'symbol': symbol, 'price_to_earnings_ratio': float(pe), 'note': 'Trailing P/E'}
        return {'symbol': symbol, 'error': 'P/E missing or non-positive'}
    except Exception as e:
        return {'error': f'PE failed: {e}'}

def calculate_sharpe_ratio(symbol: str, risk_free_rate: float, period: str = '5y', interval: str = '1d', trading_days: int = 252, auto_adjust: bool = True) -> Dict[str, Any]:
    try:
        rf = float(risk_free_rate)/100.0
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=auto_adjust)
        if df is None or df.empty:
            return {'symbol': symbol, 'error': 'No data'}
        col = 'Close' if auto_adjust else ('Adj Close' if 'Adj Close' in df.columns else 'Close')
        px = df[col].astype(float).dropna()
        if px.size < 2:
            return {'symbol': symbol, 'error': 'Insufficient prices'}
        r = np.log(px/px.shift(1)).dropna()
        mu = float(r.mean().item())*trading_days
        sigma = float(r.std(ddof=1).item())*np.sqrt(trading_days)
        if sigma <= 1e-12 or np.isnan(sigma):
            return {'symbol': symbol, 'error': 'Zero/NaN volatility'}
        sr = (mu - rf)/sigma
        return {'symbol': symbol, 'period': period, 'risk_free_rate_percent': float(risk_free_rate), 'sharpe_ratio': round(sr,6), 'annualized_return': round(mu,6), 'annualized_volatility': round(sigma,6)}
    except Exception as e:
        return {'symbol': symbol, 'error': f'Internal error: {e}'}

def calculate_sortino_ratio(symbol: str, risk_free_rate: float, period: str = '5y') -> Dict[str, Any]:
    try:
        rf = float(risk_free_rate)/100.0
        df = yf.download(symbol, period=period, interval='1d', progress=False, auto_adjust=True)
        if df is None or df.empty:
            return {'symbol': symbol, 'error': 'No data'}
        px = df['Close'].astype(float).dropna()
        if px.size < 2:
            return {'symbol': symbol, 'error': 'Insufficient prices'}
        r = px.pct_change().dropna()
        td = 252
        mar_d = (1+rf)**(1/td) - 1
        dd = np.minimum(0.0, r - mar_d)
        dd_var = np.nanmean(np.square(dd))
        if np.isnan(dd_var) or dd_var <= 0.0:
            return {'symbol': symbol, 'error': 'No downside variance'}
        dstd = np.sqrt(dd_var)*np.sqrt(td)
        mean_ann = float(r.mean().item())*td
        srt = (mean_ann - rf)/dstd
        return {'symbol': symbol, 'period': period, 'risk_free_rate_percent': float(risk_free_rate), 'sortino_ratio': round(srt,6), 'annualized_return': round(mean_ann,6), 'annualized_downside_volatility': round(dstd,6)}
    except Exception as e:
        return {'symbol': symbol, 'error': f'Sortino failed: {e}'}

def calculate_correlation_matrix(symbols: List[str], period: str = '5y') -> Dict[str, Any]:
    if len(symbols) < 2:
        return {'error': 'Requires at least two symbols'}
    try:
        raw = yf.download(symbols, period=period, interval='1d', progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            return {'error': 'No data'}
        if isinstance(raw, pd.DataFrame) and 'Close' in raw.columns and raw.columns.nlevels == 2:
            data = raw['Close'].copy()
        elif isinstance(raw, pd.DataFrame) and 'Close' in raw.columns and raw.columns.nlevels == 1:
            data = raw[['Close']].copy() if len(symbols)==1 else raw['Close'] if 'Close' in raw else raw
            if isinstance(data, pd.Series):
                data = data.to_frame(name=symbols[0])
        else:
            data = raw['Adj Close'].copy() if 'Adj Close' in raw.columns else raw.copy()
        if isinstance(data, pd.Series):
            data = data.to_frame(name=symbols[0])
        data.dropna(axis=1, how='all', inplace=True)
        if data.shape[1] < 2:
            return {'error': 'Less than two valid symbols'}
        lr = np.log(data/data.shift(1)).dropna(how='all')
        if lr.empty or lr.shape[1] < 2:
            return {'error': 'Insufficient common return data'}
        cm = lr.corr()
        return {'period': period, 'symbols': list(cm.columns), 'correlation_matrix_json': cm.to_json(orient='index')}
    except Exception as e:
        return {'error': f'Correlation failed: {e}'}

def calculate_treynor_ratio(symbol: str, risk_free_rate: float, annualized_return: float, beta: float) -> Dict[str, Any]:
    try:
        rf = float(risk_free_rate)/100.0
        ar = float(annualized_return)
        b = float(beta)
        if abs(b) < 1e-12:
            return {'symbol': symbol, 'treynor_ratio': None, 'annualized_return': ar, 'beta': b, 'risk_free_rate_percent': float(risk_free_rate), 'error': 'Beta too close to zero'}
        tr = (ar - rf)/b
        return {'symbol': symbol, 'treynor_ratio': float(tr), 'annualized_return': float(ar), 'beta': float(b), 'risk_free_rate_percent': float(risk_free_rate)}
    except Exception as e:
        logger.error(f'Treynor failed: {e}')
        return {'symbol': symbol, 'error': f'Treynor failed: {e}'}

def calculate_piotroski_f_score(symbol: str) -> Dict[str, Any]:
    def safe_get(df, row, col_idx):
        try:
            if df is None or df.empty or col_idx<0 or col_idx>=df.shape[1]:
                return np.nan
            col = df.columns[col_idx]
            val = df.at[row, col] if row in df.index else np.nan
            return float(val) if pd.notna(val) else np.nan
        except Exception:
            return np.nan
    f = 0; details = {}
    try:
        t = yf.Ticker(symbol)
        inc, bs, cf = getattr(t,'financials',None), getattr(t,'balance_sheet',None), getattr(t,'cashflow',None)
        if inc is None or bs is None or cf is None or inc.shape[1]<2 or bs.shape[1]<2 or cf.shape[1]<2:
            return {'symbol': symbol, 'piotroski_f_score': np.nan, 'error': 'Missing/insufficient financial tables'}
        T, Tm1 = 0, 1
        niT = safe_get(inc,'Net Income',T); taT = safe_get(bs,'Total Assets',T)
        niTm1 = safe_get(inc,'Net Income',Tm1); taTm1 = safe_get(bs,'Total Assets',Tm1)
        roaT = niT/taT if pd.notna(niT) and pd.notna(taT) and taT!=0 else np.nan
        roaTm1 = niTm1/taTm1 if pd.notna(niTm1) and pd.notna(taTm1) and taTm1!=0 else np.nan
        details['P1_ROA_Positive'] = pd.notna(roaT) and roaT>0; f += int(details['P1_ROA_Positive'])
        cfoT = safe_get(cf,'Total Cash From Operating Activities',T)
        details['P2_CFO_Positive'] = pd.notna(cfoT) and cfoT>0; f += int(details['P2_CFO_Positive'])
        details['P3_ROA_Improvement'] = pd.notna(roaT) and pd.notna(roaTm1) and roaT>roaTm1; f += int(details['P3_ROA_Improvement'])
        details['P4_CFO_vs_NetIncome'] = pd.notna(cfoT) and pd.notna(niT) and cfoT>niT; f += int(details['P4_CFO_vs_NetIncome'])
        ltdT = safe_get(bs,'Long Term Debt',T); ltdTm1 = safe_get(bs,'Long Term Debt',Tm1)
        details['L1_Debt_Decrease'] = pd.notna(ltdT) and pd.notna(ltdTm1) and ltdT<=ltdTm1; f += int(details['L1_Debt_Decrease'])
        caT = safe_get(bs,'Current Assets',T); clT = safe_get(bs,'Current Liabilities',T)
        caTm1 = safe_get(bs,'Current Assets',Tm1); clTm1 = safe_get(bs,'Current Liabilities',Tm1)
        crT = caT/clT if pd.notna(caT) and pd.notna(clT) and clT!=0 else np.nan
        crTm1 = caTm1/clTm1 if pd.notna(caTm1) and pd.notna(clTm1) and clTm1!=0 else np.nan
        details['L2_Current_Ratio_Improvement'] = pd.notna(crT) and pd.notna(crTm1) and crT>crTm1; f += int(details['L2_Current_Ratio_Improvement'])
        csT = safe_get(bs,'Common Stock',T); csTm1 = safe_get(bs,'Common Stock',Tm1)
        details['L3_No_New_Shares'] = pd.notna(csT) and pd.notna(csTm1) and csT<=csTm1; f += int(details['L3_No_New_Shares'])
        gpT = safe_get(inc,'Gross Profit',T); revT = safe_get(inc,'Total Revenue',T)
        gpTm1 = safe_get(inc,'Gross Profit',Tm1); revTm1 = safe_get(inc,'Total Revenue',Tm1)
        gmT = gpT/revT if pd.notna(gpT) and pd.notna(revT) and revT!=0 else np.nan
        gmTm1 = gpTm1/revTm1 if pd.notna(gpTm1) and pd.notna(revTm1) and revTm1!=0 else np.nan
        details['O1_Gross_Margin_Improvement'] = pd.notna(gmT) and pd.notna(gmTm1) and gmT>gmTm1; f += int(details['O1_Gross_Margin_Improvement'])
        atT = revT/taT if pd.notna(revT) and pd.notna(taT) and taT!=0 else np.nan
        atTm1 = revTm1/taTm1 if pd.notna(revTm1) and pd.notna(taTm1) and taTm1!=0 else np.nan
        details['O2_Asset_Turnover_Improvement'] = pd.notna(atT) and pd.notna(atTm1) and atT>atTm1; f += int(details['O2_Asset_Turnover_Improvement'])
        if any(pd.isna(x) for x in [roaT,roaTm1,cfoT,crT,crTm1,gmT,gmTm1,atT,atTm1]):
            return {'symbol': symbol, 'piotroski_f_score': int(f), 'breakdown': details, 'warning': 'Partial input (NaN) encountered.'}
        return {'symbol': symbol, 'piotroski_f_score': int(f), 'breakdown': details}
    except Exception as e:
        logger.error(f'Piotroski failed: {e}')
        return {'symbol': symbol, 'piotroski_f_score': np.nan, 'error': f'Piotroski failed: {e}'}

def calculate_jensens_alpha(symbol: str, risk_free_rate: float, annualized_return: float, beta: float, market_return: float) -> Dict[str, Any]:
    try:
        rf = float(risk_free_rate)/100.0
        ar = float(annualized_return)
        mr = float(market_return)
        b = float(beta)
        exp = rf + b*(mr - rf)
        alpha = ar - exp
        return {'symbol': symbol, 'jensens_alpha': float(alpha), 'expected_return_capm': float(exp), 'inputs': {'risk_free_rate_percent': float(risk_free_rate), 'annualized_return': ar, 'beta': b, 'market_return': mr}}
    except Exception as e:
        logger.error(f"Jensen's alpha failed: {e}")
        return {'symbol': symbol, 'error': f"Jensen's alpha failed: {e}"}

def calculate_peg_ratio(symbol: str) -> Dict[str, Any]:
    try:
        info = getattr(yf.Ticker(symbol), 'info', {}) or {}
        pe = info.get('trailingPE') or info.get('peRatio') or info.get('trailing_pe')
        try:
            pe = float(pe) if pe is not None else None
        except Exception:
            pe = None
        growth = None
        for k in ['earningsGrowth','forwardEpsGrowth','earningsQuarterlyGrowth']:
            v = info.get(k)
            if v is None: continue
            try: growth = float(v); break
            except Exception: continue
        if pe is None or growth is None or growth<=0 or growth>2.0:
            return {'symbol': symbol, 'peg_ratio': np.nan, 'error': 'Missing/implausible inputs'}
        return {'symbol': symbol, 'peg_ratio': float(pe/(growth*100.0)), 'pe_ratio': float(pe), 'annual_eps_growth_percent': float(growth*100.0), 'raw_growth_input': float(growth)}
    except Exception as e:
        logger.error(f'PEG failed: {e}')
        return {'symbol': symbol, 'peg_ratio': np.nan, 'error': f'PEG failed: {e}'}

# New utility used by portfolio diversification

def get_daily_returns(symbols: List[str], period: str = '5y') -> Dict[str, Any]:
    try:
        close = yf.download(symbols, period=period, interval='1d', progress=False, auto_adjust=True)['Close']
        if isinstance(close, pd.Series):
            close = close.to_frame(symbols[0])
        close = close.dropna(how='all')
        if close.shape[1] < 1 or close.shape[0] < 2:
            return {'error': 'Insufficient price data to compute returns.'}
        ret = close.pct_change().dropna()
        return {'period': period, 'daily_returns': {c: ret[c].astype(float).tolist() for c in ret.columns}}
    except Exception as e:
        return {'error': f'Daily returns failed: {e}'}

# --- Agent -----------------------------------------------------------------
calculation_agent = LlmAgent(
    name='Financial_Calculation_Agent',
    model='gemini-2.5-flash',
    description='Specialist financial assistant with market data & calculation tools.',
    instruction='Use the tools to fetch data and compute the requested financial metrics. Prefer decimal units for returns/volatility.',
    tools=[
        calculate_beta_and_volatility,
        calculate_correlation_matrix,
        calculate_ebitda,
        calculate_jensens_alpha,
        calculate_peg_ratio,
        calculate_piotroski_f_score,
        calculate_sharpe_ratio,
        calculate_sortino_ratio,
        calculate_treynor_ratio,
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
        get_daily_returns,
    ],
)
