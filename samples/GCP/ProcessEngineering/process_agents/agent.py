# process_agents/agent.py
from google.adk.agents import LoopAgent, SequentialAgent

import time
from .analysis_agent import analysis_agent
from .design_agent import design_agent
from .compliance_agent import compliance_agent
from .doc_gen_agent import doc_gen_agent

# 1. Create a Review Loop
# This replaces the hitl review logic. 
# It pairs the Design Agent and Compliance Agent in a loop.
review_loop = LoopAgent(
    name="Design_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Design_Stage",
            sub_agents=[design_agent, compliance_agent]
        )
    ],
    max_iterations=5
)

# 2. Reconstruct the Root Pipeline
# The flow is now: Analysis -> (Loop: Design/Compliance) -> Documentation
root_agent = SequentialAgent(
    name="Automated_Process_Architect_Pipeline",
    sub_agents=[
        analysis_agent, 
        review_loop, 
        doc_gen_agent
    ]
)


if __name__ == "__main__":
    print("Automated Standard Pipeline Initialized.")