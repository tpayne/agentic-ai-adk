# adk/review_agent.py

# ADK and type imports
from google.adk.agents import LlmAgent
from typing import Dict, Any, List
import logging
import json # Used for safe JSON parsing/formatting
import os

from .calculation_agent import calculation_agent as review_calculation_agent

review_calculation_instance = LlmAgent(
    # Copy all necessary properties from the original agent object
    name=review_calculation_agent.name + "_Root_Instance", 
    model=review_calculation_agent.model,
    description=review_calculation_agent.description,
    instruction=review_calculation_agent.instruction,
    tools=review_calculation_agent.tools, 
)

#--- logging ---
logger = logging.getLogger("recommendation_agent")
logging.basicConfig(level=logging.WARNING)
# Get log level from environment variable, default to WARNING
LOGLEVEL = os.getenv("LOGLEVEL", "WARNING").upper()
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
    if logger: logger.setLevel(LOGLEVEL)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

# --- Internal Review Logic (Manual Python Function) ---

def review_portfolio_recommendation(portfolio_json: str) -> Dict[str, Any]:
    """
    Analyzes the structured JSON output from the Portfolio_Generation_Agent to ensure 
    it meets risk balance, metric integrity, and formatting standards.

    Args:
        portfolio_json: The complete JSON string output from the Portfolio_Generation_Agent.

    Returns:
        A dictionary containing the review status, key observations, and the original portfolio.
    """
    try:
        # Safely parse the JSON output
        portfolio = json.loads(portfolio_json)
        
        review_status = "Accepted"
        observations = []
        
        risk_categories = portfolio.get('risk_categories', {})
        high_risk_list = risk_categories.get('high_performer_high_risk', [])
        low_mid_risk_list = risk_categories.get('stable_performer_low_mid_risk', [])

        # 1. Check Portfolio Balance (Goal: 10/10)
        high_count = len(high_risk_list)
        low_count = len(low_mid_risk_list)
        
        if high_count + low_count != 20:
            review_status = "Warning"
            observations.append(f"Portfolio count is unbalanced or incomplete: {high_count + low_count}/20 stocks recommended.")
            
        # 2. Check Risk Profile Integrity (e.g., Beta values)
        # Check high-risk assumptions
        for item in high_risk_list:
            if item.get('beta', 0) <= 1.2:
                observations.append(f"Stock {item['symbol']} in 'high_risk' category has low Beta ({item['beta']}). Needs verification.")
                review_status = "Warning"

        # Check low-risk assumptions
        for item in low_mid_risk_list:
            if item.get('beta', 0) >= 1.0:
                observations.append(f"Stock {item['symbol']} in 'low/mid_risk' category has high Beta ({item['beta']}). Needs verification.")
                # Only set to 'Warning' if it wasn't already 'Rejected'
                if review_status != "Rejected":
                    review_status = "Warning"
        
        if not observations:
             observations.append("All structural and risk-profile checks passed successfully.")

        return {
            "review_status": review_status,
            "observations": observations,
            "original_portfolio": portfolio
        }
    
    except json.JSONDecodeError:
        return {
            "review_status": "Rejected",
            "observations": ["Input portfolio is not valid JSON."],
            "original_portfolio": portfolio_json 
        }
    except Exception as e:
        return {
            "review_status": "Rejected",
            "observations": [f"Review failed due to unexpected internal error: {e}"],
            "original_portfolio": portfolio_json 
        }


# --- ADK Agent Definition ---

review_agent = LlmAgent(
    name="Portfolio_Review_Agent",
    model="gemini-2.5-flash",
    description="A Quality Assurance agent specialized in reviewing the structured output of the Portfolio_Generation_Agent for completeness, balance, and logical integrity, with the ability to re-verify calculated metrics.",
    instruction="""Your sole task is to take the JSON output from the Portfolio_Generation_Agent and review it.

    **Review Workflow:**
    1. **Initial Check:** Run the entire JSON output through the internal `review_portfolio_recommendation` tool to get a structural and logical assessment.
    2. **Deep Verification (using Sub-Agent):** If the internal review raises a 'Warning' or 'Rejected' status, or if any stock's metrics appear suspicious (e.g., a stock with unexpectedly low Beta in the high-risk list), you **MUST** use the **`transfer_to_agent`** tool to delegate a request to the **`calculation_agent`** to invoke its **`calculate_beta_and_volatility`** tool. Re-calculate the Beta for 2-3 flagged stocks to confirm the original data's integrity. *Assume the market index was S&P 500 ('^GSPC') and the period was '5y' for re-verification unless stated otherwise.*
    3. **Final Report:** Provide a concise summary of the overall review status (Accepted, Warning, or Rejected), including the findings from any data re-verification steps.
    """,
    tools=[review_portfolio_recommendation],
    sub_agents=[review_calculation_instance]
)