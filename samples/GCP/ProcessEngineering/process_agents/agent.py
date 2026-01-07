# process_agents/agent.py
import os
import sys
import logging
from datetime import datetime
from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent

# Import sub-agents
from .analysis_agent import analysis_agent
from .design_agent import design_agent as design_agent
from .compliance_agent import compliance_agent
from .consultant_agent import consultant_agent
from .json_normalizer_agent import json_normalizer_agent
from .json_review_agent import json_review_agent
from .edge_inference_agent import edge_inference_agent
from .doc_generation_agent import doc_generation_agent
from .json_writer_agent import json_writer_agent
from .simulation_agent import simulation_agent
from .subprocess_driver_agent import subprocess_driver_agent
from .scenario_agent import scenario_tester_agent

from .utils import load_instruction
from .utils import validate_instruction_files

# ---------------------------------------------------------
# LOGGING SETUP
# ---------------------------------------------------------
log_dir = "output/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(log_format)
file_handler.flush = lambda: file_handler.stream.flush()

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_format)

logger = logging.getLogger("ProcessArchitect")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False

# Reset runtime error log
runtime_file = os.path.join(log_dir, "runtime_errors.log")
if os.path.exists(runtime_file):
    try:
        os.remove(runtime_file)
    except Exception as e:
        logger.error(f"Failed to remove runtime file: {str(e)}")

sys.stderr = open(runtime_file, "a")

# Reset process_data.json
if not os.environ.get("RUN_DEBUG"):
#     # Remove process_data.json if RUN_DEBUG is not set
#     logger.info("Removing state files...")
#     state_file = "output/process_data.json"
#     if os.path.exists(state_file):
#         try:
#             os.remove(state_file)
#             cleanup_status = "Existing state file cleared."
#         except Exception as e:
#             cleanup_status = f"Cleanup failed: {str(e)}"
#     else:
#         cleanup_status = "No previous state file found. Starting clean."
#     logger.info(f"Pipeline initialized. {cleanup_status}")

    state_file = "output/simulation_results.json"
    if os.path.exists(state_file):
        try:
            os.remove(state_file)
            cleanup_status = "Existing simulation file cleared."
        except Exception as e:
            cleanup_status = f"Cleanup failed: {str(e)}"
    else:
        cleanup_status = "No previous simulation file found. Starting clean."

    logger.info(f"Pipeline initialized. {cleanup_status}")

# Validate instruction files before proceeding
logger.info("Validating instruction files...")
if not validate_instruction_files():
    logger.error("Instruction file validation failed. Aborting pipeline.")
    sys.exit(1)

# ---------------------------------------------------------
# PIPELINE DEFINITION
# ---------------------------------------------------------

# Design → Compliance loop: Iteratively refines the process 
# Note: This loop needs an exit_loop added to optimize termination,
# currently it relies on max_iterations and burns unnecessary tokens.

design_instance = LlmAgent(
    name=design_agent.name + '_Design_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

design_compliance_instance = LlmAgent(
    name=design_agent.name + '_Compliance_Instance',
    model=design_agent.model,
    description=design_agent.description,
    instruction=design_agent.instruction,
    tools=design_agent.tools,
    output_key=design_agent.output_key,
)

review_loop = LoopAgent(
    name="Design_Compliance_Loop",
    sub_agents=[
        SequentialAgent(
            name="Iterative_Design_Stage",
            sub_agents=[design_instance, compliance_agent, design_compliance_instance, simulation_agent],
        )
    ],
    max_iterations=7 # The max iterations for this loop. Adjust as needed.
)

# JSON Normalization → Review loop: Stabilizes the process JSON
json_normalization_loop = SequentialAgent(
    name="JSON_Normalization_Retry_Loop",
    sub_agents=[
        LoopAgent(
            name="Normalizer_Review_Sequence",
            sub_agents=[json_normalizer_agent, json_review_agent],
            max_iterations=20 # The max iterations for this loop. Adjust as needed.
        ),
        json_writer_agent
    ],
)

# Build the full design pipeline
subprocess_stage = subprocess_driver_agent
full_design_pipeline = SequentialAgent(
    name="Full_Design_Pipeline",
    description="Use this tool ONLY when the user wants to CREATE, DESIGN, or GENERATE a new business process from scratch.",
    sub_agents=[
        analysis_agent,          # Stage 1: Requirements
        review_loop,             # Stage 2: Design/Audit Loop
        json_normalization_loop, # Stage 3: Stabilization (writes process_data.json)
        subprocess_stage,        # Stage 4: Per-step subprocess generation (writes output/subprocesses/*.json)
        edge_inference_agent,    # Stage 5: Logical Flow
        doc_generation_agent     # Stage 6: Artifact Build
    ]
)

# ---------------------------------------------------------
# ROOT AGENT
# ---------------------------------------------------------
root_agent = LlmAgent(
    name="Process_Architect_Orchestrator",
    model="gemini-2.0-flash-001",
    instruction=load_instruction("agent.txt"),
    # Ensure sub_agents are provided so the LLM can route to them
    sub_agents=[
        full_design_pipeline, 
        consultant_agent,     
        scenario_tester_agent 
    ]
)

if __name__ == "__main__":
    logger.info("Pipeline initialized and ready for execution.")
    print("Automated Standard Pipeline Initialized. Logs writing to output/logs/")