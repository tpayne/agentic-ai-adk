
# review_agent.py
# VERSION: 2025-12-06.2

from google.adk.agents import LlmAgent
from typing import Dict, Any, List
import logging, os, json

from .calculation_agent import calculation_agent as calc_agent

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

logger = get_logger('review_agent')

# clone calc agent for delegated verification
calc_instance = LlmAgent(
    name=calc_agent.name + '_Root_Instance',
    model=calc_agent.model,
    description=calc_agent.description,
    instruction=calc_agent.instruction,
    tools=calc_agent.tools,
)

# --- internal checks -------------------------------------------------------

def _validate_portfolio_shape(p: Dict[str,Any]) -> List[str]:
    issues = []
    for k in ['exchange','recommendation_date','risk_categories']:
        if k not in p: issues.append(f"Missing top-level key: '{k}'.")
    rc = p.get('risk_categories')
    if not isinstance(rc, dict):
        issues.append("'risk_categories' must be an object/dict.")
        return issues
    for k in ['high_performer_high_risk','stable_performer_low_mid_risk']:
        if k not in rc: issues.append(f"Missing risk category: '{k}'.")
        elif not isinstance(rc.get(k), list): issues.append(f"Risk category '{k}' must be a list.")
    return issues


def review_portfolio_recommendation(portfolio_json: str) -> Dict[str, Any]:
    """Lightweight schema + risk threshold validation. Env: BETA_HIGH_MIN/BETA_LOW_MAX/EXPECTED_COUNT_TOTAL"""
    try:
        p = json.loads(portfolio_json)
        issues = _validate_portfolio_shape(p)
        if issues:
            return {'review_status':'Rejected','observations':[f"Schema issues: {', '.join(issues)}"],'original_portfolio': p}
        rc = p['risk_categories']
        high, low = rc.get('high_performer_high_risk', []), rc.get('stable_performer_low_mid_risk', [])
        status = 'Accepted'; obs: List[str] = []
        expected_total = int(os.getenv('EXPECTED_COUNT_TOTAL','20'))
        total = len(high)+len(low)
        if total != expected_total:
            status = 'Warning'; obs.append(f'Portfolio count {total}/{expected_total} — expected exactly {expected_total}.')
        hi = float(os.getenv('BETA_HIGH_MIN','1.2'))
        lo = float(os.getenv('BETA_LOW_MAX','1.0'))
        for it in high:
            b = it.get('beta', 0)
            if b <= hi:
                status = 'Warning'; obs.append(f"High-risk {it.get('symbol','?')} beta {b} <= {hi}.")
        for it in low:
            b = it.get('beta', 0)
            if b >= lo:
                status = 'Warning'; obs.append(f"Low/mid-risk {it.get('symbol','?')} beta {b} >= {lo}.")
        if not obs:
            obs.append('All structural and risk-profile checks passed successfully.')
        return {'review_status': status, 'observations': obs, 'original_portfolio': p}
    except json.JSONDecodeError:
        return {'review_status':'Rejected','observations':['Input portfolio is not valid JSON.'],'original_portfolio': portfolio_json}
    except Exception as e:
        return {'review_status':'Rejected','observations':[f'Review failed: {e}'],'original_portfolio': portfolio_json}

# --- agent -----------------------------------------------------------------
review_agent = LlmAgent(
    name='Portfolio_Review_Agent',
    model='gemini-2.5-flash',
    description='QA agent reviewing the portfolio output for completeness and logical integrity.',
    instruction='Run the review_portfolio_recommendation tool; if status is Warning/Rejected, delegate to calculation agent to re-check metrics (e.g., beta).',
    tools=[review_portfolio_recommendation],
    sub_agents=[calc_instance]
)
