# process_agents/agent.py
import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load variables from .env file into os.environ
load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise EnvironmentError("GOOGLE_API_KEY is not set in environment variables.")

from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent

# Import sub-agents
from .consultant_agent import consultant_agent
from .create_process_agent import full_design_pipeline
from .scenario_agent import scenario_tester_agent
from .update_process_agent import update_design_pipeline

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


# Validate instruction files before proceeding
logger.info("Validating instruction files...")
if not validate_instruction_files():
    logger.error("Instruction file validation failed. Aborting pipeline.")
    sys.exit(1)

logger.info("Pipeline initialised...")

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
        scenario_tester_agent,
        update_design_pipeline,
    ]
)

if __name__ == "__main__":
    logger.info("Pipeline initialized and ready for execution.")
    print("Automated Standard Pipeline Initialized. Logs writing to output/logs/")