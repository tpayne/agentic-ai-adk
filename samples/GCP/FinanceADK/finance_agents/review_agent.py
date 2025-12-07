
# review_agent.py — MERGED VERSION
# DATE: 2025-12-07
"""
Portfolio Review Agent — quality checks for portfolio JSON.
Merged highlights:
- Accepts JSON string OR Python dict.
- Minimal schema validation (fixed early-return bug) and env-tunable risk thresholds.
- Restored calculation sub-agent for targeted metric re-verification (e.g., Beta) on warnings.
"""
from google.adk.agents import LlmAgent
from typing import Dict, Any, List, Union
import logging
import os
import json

# -----------------------------------------------------------------------------
# Logging — guard duplicate handlers and honor LOGLEVEL
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

logger = get_logger('review_agent')

# -----------------------------------------------------------------------------
# Schema validation (fixed: validate risk category lists)
# -----------------------------------------------------------------------------
def _validate_portfolio_shape(portfolio: Dict[str, Any]) -> List[str]:
    """Ensure minimal expected structure is present and well-typed."""
    issues: List[str] = []
    for k in ['exchange', 'recommendation_date', 'risk_categories']:
        if k not in portfolio:
            issues.append(f"Missing top-level key: '{k}'.")
    rc = portfolio.get('risk_categories')
    if not isinstance(rc, dict):
        issues.append("'risk_categories' must be an object/dict.")
        return issues
    for k in ['high_performer_high_risk', 'stable_performer_low_mid_risk']:
        if k not in rc:
            issues.append(f"Missing risk category: '{k}'.")
        elif not isinstance(rc.get(k), list):
            issues.append(f"Risk category '{k}' must be a list.")
    return issues

# -----------------------------------------------------------------------------
# Review tool — schema + risk thresholds; accepts dict or JSON string
# -----------------------------------------------------------------------------
def review_portfolio_recommendation(portfolio_json: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Review the portfolio for:
      - Schema correctness
      - Expected count (env EXPECTED_COUNT_TOTAL; default 20)
      - Beta sanity checks per category (BETA_HIGH_MIN/BETA_LOW_MAX)

    Returns: {'review_status', 'observations', 'original_portfolio'}
    """
    try:
        portfolio = portfolio_json if isinstance(portfolio_json, dict) else json.loads(portfolio_json)
        issues = _validate_portfolio_shape(portfolio)
        if issues:
            return {'review_status': 'Rejected',
                    'observations': [f"Schema validation failed: {', '.join(issues)}"],
                    'original_portfolio': portfolio}
        rc = portfolio['risk_categories']
        high = rc.get('high_performer_high_risk', [])
        low = rc.get('stable_performer_low_mid_risk', [])
        status = 'Accepted'
        observations: List[str] = []
        expected_total = int(os.getenv('EXPECTED_COUNT_TOTAL', '20'))
        total = len(high) + len(low)
        if total != expected_total:
            status = 'Warning'
            observations.append(f'Portfolio count {total}/{expected_total} — expected exactly {expected_total}.')
        hi = float(os.getenv('BETA_HIGH_MIN', '1.2'))
        lo = float(os.getenv('BETA_LOW_MAX', '1.0'))
        for it in high:
            b = it.get('beta', 0)
            if b <= hi:
                status = 'Warning'
                observations.append(f"High-risk {it.get('symbol','?')} beta {b} <= {hi}.")
        for it in low:
            b = it.get('beta', 0)
            if b >= lo:
                status = 'Warning'
                observations.append(f"Low/mid-risk {it.get('symbol','?')} beta {b} >= {lo}.")
        if not observations:
            observations.append('All structural and risk-profile checks passed successfully.')
        return {'review_status': status, 'observations': observations, 'original_portfolio': portfolio}
    except json.JSONDecodeError:
        return {'review_status': 'Rejected',
                'observations': ['Input portfolio is not valid JSON.'],
                'original_portfolio': portfolio_json}
    except Exception as e:
        return {'review_status': 'Rejected',
                'observations': [f'Review failed: {e}'],
                'original_portfolio': portfolio_json}

# -----------------------------------------------------------------------------
# ADK Agent Definition — restore calculation sub-agent for re-verification
# -----------------------------------------------------------------------------
from .calculation_agent import calculation_agent as calc_agent

calc_instance_for_review = LlmAgent(
    name=calc_agent.name + '_Review_SubInstance',
    model=calc_agent.model,
    description=calc_agent.description,
    instruction=calc_agent.instruction,
    tools=calc_agent.tools,
)

review_agent = LlmAgent(
    name='Portfolio_Review_Agent',
    model='gemini-2.5-flash',
    description='QA agent reviewing the portfolio output for completeness and logical integrity.',
    instruction=(
        'Run the review_portfolio_recommendation tool. If status is Warning/Rejected, '
        'delegate via transfer_to_agent to the Calculation_Agent to re-check metrics (e.g., beta) '
        'for 2–3 flagged symbols before issuing the final report.'
    ),
    tools=[review_portfolio_recommendation],
    sub_agents=[calc_instance_for_review]
)
