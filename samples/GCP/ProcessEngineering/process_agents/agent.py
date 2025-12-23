from google.adk.agents import LoopAgent, SequentialAgent
from .analysis_agent import analysis_agent
from .design_agent import design_agent
from .compliance_agent import compliance_agent
from .json_normalizer_agent import json_normalizer_agent
from .doc_generation_agent import doc_generation_agent

# Design → Compliance loop
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

# Full pipeline
root_agent = SequentialAgent(
    name="Automated_Process_Architect_Pipeline",
    sub_agents=[
        analysis_agent,
        review_loop,
        json_normalizer_agent,
        doc_generation_agent
    ]
)

if __name__ == "__main__":
    print("Automated Standard Pipeline Initialized.")
