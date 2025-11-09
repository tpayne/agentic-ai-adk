# adk/portfolio_agent.py

# ADK and type imports
from google.adk.agents import LlmAgent

from typing import Dict, List, Any
import logging
import pandas as pd
import numpy as np # Required for generate_recommended_portfolio if more complex logic is added

# Import the root agent from agent.py as the sub-agent
from .calculation_agent import calculation_agent as root_calculation_agent
from .review_agent import review_agent as root_review_agent
import os

# --- logging ---
logger = logging.getLogger("recommendation_agent")
log_level = logging.DEBUG if os.getenv("LOGGING", "").lower() == "debug" else logging.INFO
logger.setLevel(log_level)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

root_calculation_instance = LlmAgent(
    # Copy all necessary properties from the original agent object
    name=root_calculation_agent.name + "_Root_Instance", 
    model=root_calculation_agent.model,
    description=root_calculation_agent.description,
    instruction=root_calculation_agent.instruction,
    tools=root_calculation_agent.tools, 
)

root_review_instance = LlmAgent(
    # Copy all necessary properties from the original agent object
    name=root_review_agent.name + "_Root_Instance", 
    model=root_review_agent.model,
    description=root_review_agent.description,
    instruction=root_review_agent.instruction,
    tools=root_review_agent.tools, 
)


# --- Internal Portfolio Logic (Parent Agent's Compilation Tool) ---
def generate_recommended_portfolio(
    exchange_name: str, 
    stock_data_results: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyzes a dictionary of calculated financial indicators and risk metrics 
    for multiple stocks and generates a recommended portfolio of 20 stocks 
    categorized by risk profile.

    The input 'stock_data_results' is expected to contain performance and risk 
    metrics (like Beta, Annualized Return, Volatility) for each stock.

    Args:
        exchange_name: The name of the exchange/index (e.g., 'SP500', 'FTSE100').
        stock_data_results: A dictionary where keys are stock symbols and values 
                            are dictionaries of their calculated metrics.

    Returns:
        A structured dictionary containing a balanced portfolio categorized by risk.
    """
    
    portfolio = {
        'high_performer_high_risk': [],
        'stable_performer_low_mid_risk': [],
        'total_stocks_analyzed': 0
    }
    
    # Simple, deterministic sorting logic for demonstration (replace with complex logic if needed)
    for symbol, metrics in stock_data_results.items():
        # Ensure only valid results are processed
        if isinstance(metrics, dict) and 'beta' in metrics and 'stock_annualized_return' in metrics:
            
            portfolio['total_stocks_analyzed'] += 1
            
            beta = metrics['beta']
            annual_return = metrics['stock_annualized_return'] # Percentage value
            
            # Risk Classification Logic
            # High Risk: Beta > 1.2 AND high historical return (e.g., > 20%)
            if beta > 1.2 and annual_return > 20.0:
                if len(portfolio['high_performer_high_risk']) < 10: # Cap at 10
                    portfolio['high_performer_high_risk'].append({
                        'symbol': symbol,
                        'beta': round(beta, 2),
                        'annual_return_percent': round(annual_return, 2)
                    })
            
            # Low-Mid Risk: Beta < 1.0 AND positive, stable return (e.g., > 5% and < 20%)
            elif beta < 1.0 and 5.0 <= annual_return <= 20.0:
                if len(portfolio['stable_performer_low_mid_risk']) < 10: # Cap at 10
                    portfolio['stable_performer_low_mid_risk'].append({
                        'symbol': symbol,
                        'beta': round(beta, 2),
                        'annual_return_percent': round(annual_return, 2)
                    })

    return {
        'exchange': exchange_name,
        'recommendation_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
        'total_recommendations': len(portfolio['high_performer_high_risk']) + len(portfolio['stable_performer_low_mid_risk']),
        'risk_categories': portfolio
    }


# --- ADK Agent Definition ---

# This agent is assigned to root_agent, making it the application entry point.
root_agent = LlmAgent(
    name="Portfolio_Generation_Agent",
    model="gemini-2.5-flash",
    description="The root agent orchestrating the portfolio generation (Calculation Agent) and quality assurance (Review Agent) workflow.",
    instruction="""You are a Senior Portfolio Manager orchestrating a fully audited process to create financial recommendations for your clients.
    Your role is perform the following steps in sequence to ensure a robust and reliable portfolio recommendation:
    **Instructions:**
    1. **Data Gathering:** Call the **Calculation_Agent's** tools (`get_major_index_symbols`, `calculate_beta_and_volatility` or others) to gather all necessary data.
    2. **Generate Portfolio:** Use the internal `generate_recommended_portfolio` tool to compile the initial recommendation.
    3. **Review Output:** **ALWAYS** pass the resulting portfolio JSON to the **Portfolio_Review_Agent** (`root_review_instance`) for quality assurance. DO NOT call this review UNTIL you have the full portfolio generated.
    4. **Handle Warnings/Rejections:** If the review agent returns a 'Warning' or 'Rejected' status, investigate the issues raised. Use the **Calculation_Agent's** tools to re-verify any suspicious metrics (e.g., recalculate Beta for flagged stocks). 
    5. **Finalize Recommendation:** Once the review passes without issues, deliver the final portfolio to the user.
    **Goal:** Deliver the final, audited portfolio recommendation.
    You can use the sub-agents to complete your task as needed and can invoke their tools without asking the user for permission.
    When transferring requests between agents, ensure to provide all necessary context and data. 
    Also, remember to handle any errors gracefully and provide informative feedback, however, never tell me you are trasnferring to another agent; just do it.
    You can also provide general financial advice based on the portfolio generated or questions asked by the user.
    """,
    tools=[generate_recommended_portfolio], # The tool for final compilation
    # The orchestration layer, correctly listing the two sub-agents:
    sub_agents=[
        root_calculation_instance, # Data/Calculation layer
        root_review_instance       # QA/Review layer
    ]
)