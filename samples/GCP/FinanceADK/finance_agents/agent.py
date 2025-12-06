
# agent.py (root portfolio agent)
# VERSION: 2025-12-06.2

from google.adk.agents import LlmAgent
from typing import Dict, List, Any
import logging, os
import pandas as pd

# --- logging ---------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    lvl = os.getenv('LOGLEVEL','WARNING').upper()
    if lvl not in {'DEBUG','INFO','WARNING','ERROR','CRITICAL'}:
        lvl = 'WARNING'
    logger.setLevel(lvl)
    if not logger.handlers:
        h = logging.StreamHandler(); h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(h)
    return logger

logger = get_logger('portfolio_root')

# sub-agents
from .calculation_agent import calculation_agent as calc_agent
from .review_agent import review_agent as qa_agent

calc_instance = LlmAgent(
    name=calc_agent.name + '_Root_Instance',
    model=calc_agent.model,
    description=calc_agent.description,
    instruction=calc_agent.instruction,
    tools=calc_agent.tools,
)

review_instance = LlmAgent(
    name=qa_agent.name + '_Root_Instance',
    model=qa_agent.model,
    description=qa_agent.description,
    instruction=qa_agent.instruction,
    tools=qa_agent.tools,
)

# --- internal tool ---------------------------------------------------------

def generate_recommended_portfolio(
    exchange_name: str,
    stock_data_results: Dict[str, Any],
    stock_daily_returns: Dict[str, List[float]]
) -> Dict[str, Any]:
    """Builds a 20-stock portfolio split 10/10 by risk, with diversification heuristic.
    All returns/volatility fields should be **decimals**.
    Env: BETA_HIGH_MIN (1.2), BETA_LOW_MAX (1.0), MAX_AVG_CORR (0.4)
    """
    df = pd.DataFrame.from_dict(stock_data_results, orient='index')
    required = ['beta','annualized_return','sharpe_ratio','sortino_ratio','treynor_ratio','pe_ratio','piotroski_f_score']
    df = df.dropna(subset=[c for c in required if c in df.columns])

    if 'sortino_ratio' in df:
        df['sortino_ratio'] = df['sortino_ratio'].fillna(df.get('sharpe_ratio',0)).fillna(0)
    if 'treynor_ratio' in df:
        df['treynor_ratio'] = df['treynor_ratio'].fillna(df.get('sortino_ratio',0)).fillna(df.get('sharpe_ratio',0)).fillna(0)

    df = df[(df['sortino_ratio']>0.0) & (df['treynor_ratio']>0.0) & (df['sharpe_ratio']>0.0)]

    hi = float(os.getenv('BETA_HIGH_MIN','1.2'))
    lo = float(os.getenv('BETA_LOW_MAX','1.0'))

    high = df[(df['beta']>hi) & (df['sortino_ratio']>df['sortino_ratio'].median()) & (df['treynor_ratio']>df['treynor_ratio'].median())]
    high = high.sort_values(by=['sortino_ratio','treynor_ratio','annualized_return'], ascending=False)

    low = df[(df['beta']<lo) & (df['sortino_ratio']>df['sortino_ratio'].quantile(0.75)) & (df['pe_ratio']<30) & (df['piotroski_f_score']>=7)]
    low = low.sort_values(by=['sortino_ratio','piotroski_f_score','annualized_return'], ascending=False)

    candidates = list(high.index[:15]) + list(low.index[:15])
    try:
        corr_df = pd.DataFrame({s: stock_daily_returns[s] for s in candidates if s in stock_daily_returns}).dropna()
        if corr_df.shape[1]>1 and len(corr_df)>10:
            C = corr_df.corr().abs()
            max_avg = float(os.getenv('MAX_AVG_CORR','0.4'))
            def pick(cdf, k, existing):
                chosen = []
                for s in cdf.index:
                    if len(chosen)>=k: break
                    if s in existing or s not in C.index: continue
                    base = [x for x in (chosen+existing) if x in C.index]
                    avg = C.loc[s, base].mean() if base else 0.0
                    if avg <= max_avg:
                        chosen.append(s)
                if len(chosen)<k:
                    remain = [s for s in cdf.index if s not in chosen and s not in existing]
                    remain.sort(key=lambda s: (-cdf.loc[s,'sortino_ratio'], -cdf.loc[s,'treynor_ratio'], -cdf.loc[s,'annualized_return']))
                    for s in remain:
                        if len(chosen)>=k: break
                        chosen.append(s)
                return chosen
            high_final = pick(high, 10, [])
            low_final = pick(low, 10, high_final)
        else:
            high_final = list(high.index[:10]); low_final = list(low.index[:10])
    except Exception as e:
        logger.warning(f'Correlation fallback: {e}')
        high_final = list(high.index[:10]); low_final = list(low.index[:10])

    def backfill(cdf, cur, k):
        for s in cdf.index:
            if len(cur)>=k: break
            if s not in cur: cur.append(s)
        return cur

    high_final = backfill(high, high_final, 10)
    low_final  = backfill(low,  low_final,  10)

    def pack(symbols, data):
        out = []
        for s in symbols:
            if s in data.index:
                out.append({
                    'symbol': s,
                    'annualized_return': data.loc[s,'annualized_return'],
                    'annualized_volatility': data.loc[s,'annualized_volatility'] if 'annualized_volatility' in data.columns else None,
                    'beta': data.loc[s,'beta'],
                    'sharpe_ratio': data.loc[s,'sharpe_ratio'],
                    'sortino_ratio': data.loc[s,'sortino_ratio'],
                    'treynor_ratio': data.loc[s,'treynor_ratio'],
                    'pe_ratio': data.loc[s,'pe_ratio'],
                    'piotroski_f_score': data.loc[s,'piotroski_f_score'],
                })
        return out

    portfolio = {
        'high_performer_high_risk': pack(high_final, df),
        'stable_performer_low_mid_risk': pack(low_final, df),
    }

    return {
        'exchange': exchange_name,
        'recommendation_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
        'total_recommendations': len(portfolio['high_performer_high_risk']) + len(portfolio['stable_performer_low_mid_risk']),
        'risk_categories': portfolio
    }

# Agent definition
root_agent = LlmAgent(
    name='Portfolio_Generation_Agent',
    model='gemini-2.5-flash',
    description='Root agent orchestrating calculation (data) and review (QA).',
    instruction='Delegate data to Calculation_Agent; compile with generate_recommended_portfolio; always send the result to Portfolio_Review_Agent for QA; fix warnings then finalize.',
    sub_agents=[calc_instance, review_instance]
)
