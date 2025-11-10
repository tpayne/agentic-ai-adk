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

# --- Configure Logging ---
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
    stock_data_results: Dict[str, Any],
    stock_daily_returns: Dict[str, List[float]] 
) -> Dict[str, Any]:
    """
    Analyzes a dictionary of calculated financial indicators and risk metrics 
    for multiple stocks and generates a recommended portfolio of 20 stocks 
    categorized by risk profile, now incorporating Sharpe Ratio and Correlation.

    The input 'stock_data_results' is expected to contain performance, risk, 
    Sharpe Ratio, and P/E ratio for each stock.

    Args:
        exchange_name: The name of the exchange/index (e.g., 'SP500', 'FTSE100').
        stock_data_results: A dictionary where keys are stock symbols and values 
                            are dictionaries of their calculated metrics.
        stock_daily_returns: A dictionary where keys are stock symbols and values
                             are lists of their daily returns over the period, 
                             used for the correlation matrix.

    Returns:
        A structured dictionary containing a balanced portfolio categorized by risk.
    """
    
    # --- 1. PREP DATA ---
    df = pd.DataFrame.from_dict(stock_data_results, orient='index')
    
    # Drop any rows where critical data is missing
    required_metrics = ['beta', 'annualized_return', 'sharpe_ratio', 'pe_ratio']
    existing_metrics = [m for m in required_metrics if m in df.columns]
    
    df.dropna(subset=existing_metrics, inplace=True)

    # --- 2. FILTER & SORT ---
    # High-Risk/High-Return Candidates: Beta > 1.2 AND above average Sharpe Ratio
    high_risk_candidates = df[
        (df['beta'] > 1.2) & 
        (df['sharpe_ratio'] > df['sharpe_ratio'].median())
    ].sort_values(by='annualized_return', ascending=False)

    # Low-Mid-Risk/Stable Candidates: Beta < 1.0 AND high Sharpe Ratio
    low_risk_candidates = df[
        (df['beta'] < 1.0) & 
        (df['sharpe_ratio'] > df['sharpe_ratio'].quantile(0.75)) & # Only top quartile Sharpe
        (df['pe_ratio'] < 30) # NEW FUNDAMENTAL FILTER: Avoid extremely expensive stocks
    ].sort_values(by='annualized_return', ascending=False)


    # --- 3. CORRELATION MATRIX & DIVERSIFICATION ---
    
    # Compile a list of potential final symbols for the diversification check
    potential_symbols = list(high_risk_candidates.index[:15]) + list(low_risk_candidates.index[:15])
    
    try:
        # Create the DataFrame for Correlation using daily returns
        corr_df = pd.DataFrame({
            symbol: stock_daily_returns[symbol]
            for symbol in potential_symbols
            if symbol in stock_daily_returns 
        })
        corr_df.dropna(inplace=True) 

        if len(corr_df.columns) > 1 and len(corr_df) > 10: 
            # Calculate the Absolute Correlation Matrix (abs() correlation is used to simplify diversification)
            corr_matrix = corr_df.corr().abs()
            
            # Diversification Heuristic: Select candidates with low average correlation
            def select_diversified(candidates_df, count, existing_selection):
                symbols = list(candidates_df.index)
                final_selection = []
                
                for symbol in symbols:
                    if len(final_selection) >= count:
                        break
                    
                    if symbol not in corr_matrix.index or symbol in existing_selection:
                        continue
                        
                    is_diversified = True
                    if final_selection or existing_selection:
                        all_selected = final_selection + existing_selection
                        valid_selected = [s for s in all_selected if s in corr_matrix.index]
                        
                        if valid_selected:
                            # Calculate the average absolute correlation to the current portfolio
                            avg_corr = corr_matrix.loc[symbol, valid_selected].mean()
                            
                            # Heuristic: Only add if average correlation is below the 0.4 threshold
                            if avg_corr > 0.4: 
                                is_diversified = False
                    
                    if is_diversified:
                        final_selection.append(symbol)
                        
                return final_selection
            
            # Select final 10 high-risk picks
            high_risk_final = select_diversified(high_risk_candidates, 10, [])
            # Select final 10 low-risk picks, diversifying against the high-risk picks as well
            low_risk_final = select_diversified(low_risk_candidates, 10, high_risk_final) 

        else:
            # Fallback to simple top 10/10 if data is insufficient for correlation
            high_risk_final = list(high_risk_candidates.index[:10])
            low_risk_final = list(low_risk_candidates.index[:10])
            logger.warning("Data insufficient for correlation. Falling back to simple sorting.")
            
    except Exception as e:
        # Fallback if correlation calculation fails entirely
        logger.warning(f"Correlation calculation failed: {e}. Falling back to simple sorting.")
        high_risk_final = list(high_risk_candidates.index[:10])
        low_risk_final = list(low_risk_candidates.index[:10])


    # --- 4. COMPILE FINAL PORTFOLIO ---
    
    # Helper to compile the final stock data
    def compile_stock_list(symbols, data_df):
        return [
            {
                'symbol': sym,
                'annualized_return': data_df.loc[sym, 'annualized_return'],
                'annualized_volatility': data_df.loc[sym, 'annualized_volatility'],
                'beta': data_df.loc[sym, 'beta'],
                'sharpe_ratio': data_df.loc[sym, 'sharpe_ratio'], 
                'pe_ratio': data_df.loc[sym, 'pe_ratio'],         
            }
            for sym in symbols
            if sym in data_df.index
        ]
        
    portfolio = {
        'high_performer_high_risk': compile_stock_list(high_risk_final, df),
        'stable_performer_low_mid_risk': compile_stock_list(low_risk_final, df),
    }

    # Final Output Structure
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
    1. **Data Gathering (Delegation):** You **MUST** delegate the initial data retrieval and iterative metric calculation tasks to the **Calculation_Agent** using the **`transfer_to_agent`** tool. The delegated request must cover all necessary data: fetching index symbols, the risk-free rate, and calculating Beta, P/E Ratio, Sharpe Ratio, and daily returns for the correlation matrix.
    2. **Generate Portfolio:** Use the internal `generate_recommended_portfolio` tool to compile the initial recommendation, ensuring you pass the calculated metrics **AND** the collected stock daily returns for the correlation matrix calculation.
    3. **Review Output (Delegation):** **ALWAYS** use the **`transfer_to_agent`** tool to pass the resulting portfolio JSON to the **Portfolio_Review_Agent** (`root_review_instance`) for quality assurance. DO NOT delegate this review UNTIL you have the full portfolio generated.
    4. **Handle Warnings/Rejections:** If the review agent returns a 'Warning' or 'Rejected' status, investigate the issues raised. Delegate a request back to the **Calculation_Agent** using **`transfer_to_agent`** to re-verify any suspicious metrics (e.g., recalculate Beta or Sharpe Ratio).
    5. **Finalize Recommendation:** Once the review passes without issues, deliver the final portfolio to the user.  **Goal:** Deliver the final, audited portfolio recommendation.
    You can use the sub-agents to complete your task as needed and can invoke their tools without asking the user for permission.
    When transferring requests between agents, ensure to provide all necessary context and data. 
    Also, remember to handle any errors gracefully and provide informative feedback, however, never tell me you are trasnferring to another agent; just do it.
    You can also provide general financial advice based on the portfolio generated or questions asked by the user.
    """,
    # The orchestration layer, correctly listing the two sub-agents:
    sub_agents=[
        root_calculation_instance, # Data/Calculation layer
        root_review_instance       # QA/Review layer
    ]
)