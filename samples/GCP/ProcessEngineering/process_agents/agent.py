# process_agents/agent.py
import os
import signal
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

import pkgutil 
import google 
import google.adk 

google.__path__ = pkgutil.extend_path(google.__path__, google.__name__)
google.adk.__path__ = pkgutil.extend_path(google.adk.__path__, google.adk.__name__)

# Load variables from .env file into os.environ
load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise EnvironmentError("GOOGLE_API_KEY is not set in environment variables.")

from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent

# Import sub-agents
from .agent_registry import (
    full_design_pipeline,
    consultant_agent,
    scenario_tester_agent,
    update_design_pipeline,
    simulation_query_agent,
)

from .utils import load_instruction
from .utils import validate_instruction_files
from .utils import getProperty

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
logger.addHandler(file_handler)
#logger.addHandler(console_handler)
logger.propagate = False

# Suppress the specific ADK warning about output_schema and agent transfers
logging.getLogger("google_adk.google.adk.agents.llm_agent").setLevel(logging.ERROR)
# Get log level from environment variable, default to WARNING
LOGLEVEL = getProperty("LOGLEVEL")
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
if logger:
    logger.setLevel(LOGLEVEL)

# Reset runtime error log
runtime_file = os.path.join(log_dir, "runtime_errors.log")
if os.path.exists(runtime_file):
    try:
        os.remove(runtime_file)
    except Exception as e:
        logger.error(f"Failed to remove runtime file: {str(e)}")

sys.stderr = open(runtime_file, "a")

# Validate instruction files before proceeding
logger.debug("Validating instruction files...")
if not validate_instruction_files():
    logger.error("Instruction file validation failed. Aborting pipeline.")
    sys.exit(1)

logger.debug("Pipeline initialised...")

# Signal handler for abnormal errors
def handler(signum, frame):
    signame= signal.Signals(signum).name
    logger.warning("Trapped signal %d", signum)
    sys.exit(1)

signal.signal(signal.SIGBUS, handler)
signal.signal(signal.SIGABRT, handler)
signal.signal(signal.SIGILL, handler)
signal.signal(signal.SIGTERM, handler)

# ---------------------------------------------------------
# ROOT AGENT
# ---------------------------------------------------------
root_agent = LlmAgent(
    name="Process_Architect_Orchestrator",
    model=getProperty("MODEL"),
    instruction=load_instruction("agent.txt"),
    # Ensure sub_agents are provided so the LLM can route to them
    sub_agents=[
        full_design_pipeline, 
        consultant_agent,     
        scenario_tester_agent,
        update_design_pipeline,
        simulation_query_agent,
    ]
)

# ---------------------------------------------------------
# LOCAL CHAT LOOP SUPPORT (run outside `adk run`)
# ---------------------------------------------------------

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from google.genai import types

import asyncio
import uuid

async def start_local_chat():
    """
    Runs the Process Architect Orchestrator in an interactive loop.
    Exits when the user types 'exit', 'quit', or 'stop'.
    """

    print("\nProcess Architect Orchestrator (local mode)")
    print("Type 'exit' to quit.\n")

    # Create a persistent session for the entire chat
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="ProcessArchitect",
        user_id=user_id,
        session_id=session_id,
        state={}
    )

    runner = Runner(
        agent=root_agent,
        app_name="ProcessArchitect",
        session_service=session_service
    )

    while True:
        user_input = input("[user]: ").strip()

        if user_input.lower() in ["exit", "quit", "stop"]:
            print("Exiting Process Architect Orchestrator.")
            break

        content = types.Content(
            role="user",
            parts=[types.Part(text=user_input)]
        )

        events = runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content
        )

        final_response = None

        async for event in events:
            if event.is_final_response() and event.content and event.content.parts:
                final_response = event.content.parts[0].text

        if final_response:
            print(f"\nArchitect: {final_response}\n")
        else:
            print("\nArchitect: [No final response]\n")

# ---------------------------------------------------------
# MAIN EXECUTION BLOCK
# ---------------------------------------------------------
if __name__ == "__main__":
    logger.debug("Pipeline initialized and ready for execution.")
    asyncio.run(start_local_chat())
