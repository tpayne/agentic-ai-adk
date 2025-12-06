
# agent.py (root portfolio agent)
# VERSION: 2025-12-06.3
"""
Root ADK agent orchestrating:
- Calculation Agent (data & metrics)
- Review Agent (QA)

**Minimal functional additions (documented for diffing):**
- Deterministic selection helper with average-correlation threshold and stable tie-break.
- Backfill step to guarantee 10 high-risk + 10 low/mid-risk selections (10/10) even if correlation filters out.
- Guarded logging.

All public names and agent configurations are preserved:
- `root_agent`
- sub_agents include cloned instances of Calculation and Review agents.
"""

from google.adk.agents import LlmAgent
from typing import Dict, List, Any
import logging
import os
import pandas as pd

# -----------------------------------------------------------------------------
# Logging — guard duplicate handlers and honor LOGLEVEL.
# -----------------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    lvl = os.getenv('LOGLEVEL', 'WARNING').upper()
    if lvl not in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}:
        lvl = 'WARNING'
    logger.setLevel(lvl)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
    return logger

logger = get_logger('portfolio_root')

# -----------------------------------------------------------------------------
# Sub-agent imports — unchanged public names from your original layout.
# -----------------------------------------------------------------------------
from .calculation_agent import calculation_agent as calc_agent
from .review_agent import review_agent as qa_agent

# Clone instances (fresh runtime state, tools preserved)
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

# -----------------------------------------------------------------------------
# Internal tool — generate_recommended_portfolio (comments restored & expanded).
# -----------------------------------------------------------------------------
def generate_recommended_portfolio(
    exchange_name: str,
    stock_data_results: Dict[str, Any],
    stock_daily_returns: Dict[str, List[float]]
) -> Dict[str, Any]:
    """
    Compile a 20-stock portfolio split into:
      - 'high_performer_high_risk' (10 symbols)
      - 'stable_performer_low_mid_risk' (10 symbols)

    Inputs:
      - exchange_name: label for the recommendation.
      - stock_data_results: per-symbol metrics (DECIMALS for returns/volatility).
      - stock_daily_returns: per-symbol daily arithmetic returns (for correlation).

    Filtering logic (unchanged thresholds, documented):
      - High risk: beta > BETA_HIGH_MIN (default 1.2), above-median Sortino and Treynor.
      - Low/mid risk: beta < BETA_LOW_MAX (default 1.0), Sortino > 75th percentile, pe_ratio < 30, piotroski_f_score >= 7.

    Diversification:
      - If correlation matrix is available: select diversified picks via average absolute correlation threshold (MAX_AVG_CORR, default 0.4).
      - Deterministic backfill (Sortino -> Treynor -> Annualized Return) ensures 10 picks if correlation is too strict.

    Returns:
      Dict with keys: 'exchange', 'recommendation_date', 'total_recommendations', 'risk_categories'
    """
    # 1) PREP DATA (keep original columns; clarify required fields)
    df = pd.DataFrame.from_dict(stock_data_results, orient='index')
    required = ['beta', 'annualized_return', 'sharpe_ratio', 'sortino_ratio',
                'treynor_ratio', 'pe_ratio', 'piotroski_f_score']
    df = df.dropna(subset=[c for c in required if c in df.columns])

    # Fallbacks — keep your original approach and comments
    if 'sortino_ratio' in df:
        df['sortino_ratio'] = df['sortino_ratio'].fillna(df.get('sharpe_ratio', 0)).fillna(0)
    if 'treynor_ratio' in df:
        df['treynor_ratio'] = df['treynor_ratio'].fillna(df.get('sortino_ratio', 0)).fillna(df.get('sharpe_ratio', 0)).fillna(0)

    # Validity: require positive risk-adjusted performance metrics
    df = df[(df['sortino_ratio'] > 0.0) & (df['treynor_ratio'] > 0.0) & (df['sharpe_ratio'] > 0.0)]

    # 2) FILTER & SORT (thresholds configurable via env)
    hi = float(os.getenv('BETA_HIGH_MIN', '1.2'))
    lo = float(os.getenv('BETA_LOW_MAX', '1.0'))

    high = df[(df['beta'] > hi) &
              (df['sortino_ratio'] > df['sortino_ratio'].median()) &
              (df['treynor_ratio'] > df['treynor_ratio'].median())] \
             .sort_values(by=['sortino_ratio', 'treynor_ratio', 'annualized_return'], ascending=False)

    low = df[(df['beta'] < lo) &
             (df['sortino_ratio'] > df['sortino_ratio'].quantile(0.75)) &
             (df['pe_ratio'] < 30) &
             (df['piotroski_f_score'] >= 7)] \
            .sort_values(by=['sortino_ratio', 'piotroski_f_score', 'annualized_return'], ascending=False)

    # 3) CORRELATION & DIVERSIFICATION (deterministic selection + backfill)
    candidates = list(high.index[:15]) + list(low.index[:15])
    try:
        # Build aligned daily returns DF from provided dict (no live fetch here)
        corr_df = pd.DataFrame({s: stock_daily_returns[s] for s in candidates if s in stock_daily_returns}).dropna()
        if corr_df.shape[1] > 1 and len(corr_df) > 10:
            C = corr_df.corr().abs()
            max_avg = float(os.getenv('MAX_AVG_CORR', '0.4'))

            def pick(cdf, k, existing):
                """
                Deterministic diversified selection:
                - Add if average correlation to already-chosen + existing is <= threshold.
                - Then backfill deterministically to reach k picks.
                """
                chosen = []
                for s in cdf.index:
                    if len(chosen) >= k:
                        break
                    if s in existing or s not in C.index:
                        continue
                    base = [x for x in (chosen + existing) if x in C.index]
                    avg = C.loc[s, base].mean() if base else 0.0
                    if avg <= max_avg:
                        chosen.append(s)
                # Backfill (Sortino -> Treynor -> Annualized Return)
                if len(chosen) < k:
                    remain = [s for s in cdf.index if s not in chosen and s not in existing]
                    remain.sort(key=lambda s: (
                        -cdf.loc[s, 'sortino_ratio'],
                        -cdf.loc[s, 'treynor_ratio'],
                        -cdf.loc[s, 'annualized_return']
                    ))
                    for s in remain:
                        if len(chosen) >= k:
                            break
                        chosen.append(s)
                return chosen

            high_final = pick(high, 10, [])
            low_final = pick(low, 10, high_final)
        else:
            # Fallback to ranking-only if insufficient correlation data
            high_final = list(high.index[:10])
            low_final = list(low.index[:10])
            logger.warning('Data insufficient for correlation; falling back to simple sorting.')
    except Exception as e:
        logger.warning(f'Correlation fallback: {e}')
        high_final = list(high.index[:10])
        low_final = list(low.index[:10])

    # Ensure 10/10 via backfill helper (safe if pick() already returns 10)
    def backfill(cdf, cur, k):
        for s in cdf.index:
            if len(cur) >= k:
                break
            if s not in cur:
                cur.append(s)
        return cur

    high_final = backfill(high, high_final, 10)
    low_final  = backfill(low,  low_final,  10)

    # 4) PACK RESULTS — same keys as your original output
    def pack(symbols, data):
        out = []
        for s in symbols:
            if s in data.index:
                out.append({
                    'symbol': s,
                    'annualized_return': data.loc[s, 'annualized_return'],
                    'annualized_volatility': data.loc[s, 'annualized_volatility'] if 'annualized_volatility' in data.columns else None,
                    'beta': data.loc[s, 'beta'],
                    'sharpe_ratio': data.loc[s, 'sharpe_ratio'],
                    'sortino_ratio': data.loc[s, 'sortino_ratio'],
                    'treynor_ratio': data.loc[s, 'treynor_ratio'],
                    'pe_ratio': data.loc[s, 'pe_ratio'],
                    'piotroski_f_score': data.loc[s, 'piotroski_f_score'],
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

# -----------------------------------------------------------------------------
# ADK Agent Definition — preserved public name and sub-agent usage.
# -----------------------------------------------------------------------------
root_agent = LlmAgent(
    name='Portfolio_Generation_Agent',
    model='gemini-2.5-flash',
    description='Root agent orchestrating calculation (data) and review (QA).',
    instruction=(
        "Delegate data/metrics to Calculation_Agent; compile via generate_recommended_portfolio; "
        "ALWAYS send final JSON to Portfolio_Review_Agent for QA; address warnings then finalize."
    ),
    sub_agents=[calc_instance, review_instance]
)