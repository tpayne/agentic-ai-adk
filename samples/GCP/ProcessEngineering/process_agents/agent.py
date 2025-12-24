# process_agents/agent.py
import os
import sys
import logging
from datetime import datetime
from google.adk.agents import LoopAgent, SequentialAgent

# Import sub-agents
from .analysis_agent import analysis_agent
from .design_agent import design_agent
from .compliance_agent import compliance_agent
from .json_normalizer_agent import json_normalizer_agent
from .edge_inference_agent import edge_inference_agent
from .doc_generation_agent import doc_generation_agent

# ---------------------------------------------------------
# HARDENED LOGGING SYSTEM (Immediate Write / No Buffering)
# ---------------------------------------------------------
log_dir = "output/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# Define a strict format
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 1. File Handler with Immediate Flush
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(log_format)
# This lambda forces the stream to flush every time a log is emitted
file_handler.flush = lambda: file_handler.stream.flush() 

# 2. Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_format)

# 3. Configure the Root-level logger for the app
logger = logging.getLogger("ProcessArchitect")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False # Prevent double-logging in some environments

# Redirect standard error to a file to catch ADK internal tracebacks
sys.stderr = open(os.path.join(log_dir, "runtime_errors.log"), "a")



# ---------------------------------------------------------
# PIPELINE DEFINITION
# ---------------------------------------------------------

# Design → Compliance loop: Iteratively refines the process 
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

# Main Orchestrator
# Added edge_inference_agent back into the sequence
root_agent = SequentialAgent(
    name="Automated_Process_Architect_Pipeline",
    sub_agents=[
        analysis_agent,        # Stage 1: Requirements
        review_loop,           # Stage 2: Design/Audit Loop
        json_normalizer_agent, # Stage 3: Stabilization (Writes process_data.json)
        edge_inference_agent,  # Stage 4: Logical Flow (Writes flow.png)
        doc_generation_agent   # Stage 5: Artifact Build (Writes .docx)
    ]
)

if __name__ == "__main__":
    logger.info("Pipeline initialized and ready for execution.")
    print("Automated Standard Pipeline Initialized. Logs writing to output/logs/")