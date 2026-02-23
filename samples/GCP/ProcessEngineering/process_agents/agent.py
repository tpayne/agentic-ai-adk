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
from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent

google.__path__ = pkgutil.extend_path(google.__path__, google.__name__)
google.adk.__path__ = pkgutil.extend_path(google.adk.__path__, google.adk.__name__)

from .utils import (
    load_instruction,
    validate_instruction_files,
    getProperty,
    getResponseColour,
    ANSI_RED,
    ANSI_GREEN, 
    ANSI_CYAN, 
    ANSI_RESET
)

import argparse

# Load variables from .env file of env into os.environ
load_dotenv()
if os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_PROJECT_ID"):
    os.environ["ADK_MODEL_PROVIDER"] = "vertex"
    os.environ["GOOGLE_CLOUD_LOCATION"] = getProperty("GOOGLE_CLOUD_LOCATION", default="us-central1")
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_PROJECT_ID")
    if not os.environ["GOOGLE_CLOUD_PROJECT"]:
        raise EnvironmentError("Vertex AI requires GOOGLE_CLOUD_PROJECT to be set in your .env")
elif os.getenv("GOOGLE_API_KEY"):
    os.environ["ADK_MODEL_PROVIDER"] = "api_key"
else:
    raise EnvironmentError("Either GOOGLE_CLOUD_PROJECT (for Vertex) or GOOGLE_API_KEY must be set in environment variables.")

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
logger.propagate = False
logging.getLogger("google_adk.google.adk.agents.llm_agent").setLevel(logging.ERROR)

LOGLEVEL = getProperty("LOGLEVEL")
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
logger.setLevel(LOGLEVEL)

runtime_file = os.path.join(log_dir, "runtime_errors.log")
if os.path.exists(runtime_file):
    try:
        os.remove(runtime_file)
    except Exception as e:
        logger.error(f"Failed to remove runtime file: {str(e)}")
sys.stderr = open(runtime_file, "a")

# Import sub-agents
from .agent_registry import (
    full_design_pipeline,
    consultant_agent,
    scenario_tester_agent,
    update_design_pipeline,
    simulation_query_agent,
    build_doc_creation_agent,
    SubprocessDriverAgent,
)

# Validate instruction files before proceeding
logger.debug("Validating instruction files...")
if not validate_instruction_files():
    logger.error("Instruction file validation failed. Aborting pipeline.")
    sys.exit(1)
logger.debug("Pipeline initialised...")

# Signal handler for abnormal errors
def handler(signum, frame):
    signame = signal.Signals(signum).name
    sys.stdout = sys.__stdout__
    sys.stdout.flush()
    print(f"\n{ANSI_RED} - Received signal {signame} ({signum}). Terminating Process Architect Orchestrator.{ANSI_RESET}", end="\n")
    sys.stderr = sys.__stderr__
    sys.stderr.flush()
    logger.warning("Trapped signal %d", signum)
    sys.exit(1)

signal.signal(signal.SIGBUS, handler)
signal.signal(signal.SIGABRT, handler)
signal.signal(signal.SIGILL, handler)
signal.signal(signal.SIGTERM, handler)

# ---------------------------------------------------------
# ROOT AGENT
# ---------------------------------------------------------
from .agent_wrappers import ProcessLlmAgent  # DefaultLlmAgent shortcut

root_agent = ProcessLlmAgent(
    name="Process_Architect_Orchestrator",
    instruction_file="agent.txt",
    before_model_callback=None,  # Disable before callback for root agent
    after_model_callback=None,   # Disable after callback for root agent
    sub_agents=[
        full_design_pipeline,
        consultant_agent,
        scenario_tester_agent,
        update_design_pipeline,
        simulation_query_agent,
        build_doc_creation_agent("Create_Doc_Agent"),
        SubprocessDriverAgent(name="Subprocess_Driver_Agent_Main"),
    ],
)

# ---------------------------------------------------------
# LOCAL CHAT LOOP SUPPORT
# ---------------------------------------------------------
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
import asyncio
import uuid


def display_text(text: str, type: str = "info"):
    colour = getResponseColour("responseColourInfo")
    warning = getResponseColour("responseColourWarning")
    error = getResponseColour("responseColourError")    
    if not colour:
        colour = ANSI_GREEN
    if not warning:
        warning = ANSI_CYAN
    if not error:
        error = ANSI_RED
    if type == "info":
        print(f"{colour}{text}{ANSI_RESET}")
    elif type == "warning":
        print(f"{warning}[Warning]: {text}{ANSI_RESET}")
    elif type == "error":
        print(f"{error}[Error]: {text}{ANSI_RESET}")
    sys.stdout.flush()

def is_shell_command(text: str) -> bool:
    if text is None:
        return False
    return text.strip().startswith("$")


async def run_shell_command(cmdline: str):
    import asyncio
    stripped = cmdline.strip()
    command = stripped[1:].strip()
    print(f"{ANSI_CYAN}[Shell]: {command}{ANSI_RESET}")
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if stdout:
            print(stdout.decode("utf-8", errors="replace"), end="")

        if stderr:
            sys.stderr.write(f"{ANSI_RED}{stderr.decode('utf-8', errors='replace')}{ANSI_RESET}")

        if proc.returncode != 0:
            display_text(f"Shell command exited with code {proc.returncode}", type="error")

    except Exception as e:
        display_text(f"[Shell]: Error executing command: {e}", type="error")


async def init_session_and_runner(app_name: str = "ProcessArchitect"):
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state={}
    )
    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service
    )
    return runner, user_id, session_id


# ---------------------------------------------------------
# FILE MODE
# ---------------------------------------------------------
async def process_file(file_path: str):
    try:
        with open(file_path, "r", encoding="utf-8-sig"):
            pass
    except Exception as e:
        display_text(f"- Error opening file '{file_path}': {e}", type="error")
        sys.exit(1)

    runner, user_id, session_id = await init_session_and_runner()

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue

                if line.lower() in ["exit", "quit", "stop"]:
                    display_text("Exiting Process Architect Orchestrator.")
                    break
                elif line.lower() == "clear":
                    display_text("[Action]: Clearing all histories and resetting session...")
                    runner, user_id, session_id = await init_session_and_runner()
                    continue
                elif line.startswith("#"):
                    display_text(f"[Comment]: {line}")
                    continue
                elif line.lower().startswith("sleep") or line.lower().startswith("wait"):
                    parts = line.split()
                    secs = parts[1] if len(parts) > 1 else getProperty("modelSleep", default=0.5)
                    display_text(f"[Action]: Sleeping for {secs} seconds...")
                    await asyncio.sleep(float(secs))
                    continue
                elif is_shell_command(line):
                    await run_shell_command(line)
                    await asyncio.sleep(float(getProperty("modelSleep", default=0.25)))
                    continue


                print(f"\n[user-file]: {line}")

                content = types.Content(role="user", parts=[types.Part(text=line)])
                final_response = None
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=content
                ):
                    if event.is_final_response() and event.content and event.content.parts:
                        final_response = event.content.parts[0].text

                if final_response:
                    display_text(f"[ArchitectBot]: {final_response}")
                else:
                    display_text(f"[ArchitectBot]: [No final response]")

                await asyncio.sleep(float(getProperty("modelSleep", default=0.5)))

    except Exception as e:
        sys.stdout = sys.__stdout__
        sys.stdout.flush()
        display_text(f"- Error processing file: {str(e)}", type="error")
        sys.exit(1)


# ---------------------------------------------------------
# INTERACTIVE MODE
# ---------------------------------------------------------
async def start_local_chat():
    display_text("Process Architect Orchestrator (local mode)")
    display_text("Type 'exit' to quit.")

    runner, user_id, session_id = await init_session_and_runner()

    while True:
        user_input = input("[user]: ").strip()

        if user_input.lower() in ["exit", "quit", "stop"]:
            display_text("Exiting Process Architect Orchestrator.")
            break
        elif user_input.lower() == "clear":
            display_text("[Action]: Clearing all histories and resetting session...")
            runner, user_id, session_id = await init_session_and_runner()
            continue
        elif user_input.startswith("#"):
            display_text(f"[Comment]: {user_input}")
            continue
        elif user_input.lower().startswith("sleep") or user_input.lower().startswith("wait"):
            parts = user_input.split()
            secs = parts[1] if len(parts) > 1 else getProperty("modelSleep", default=0.5)
            display_text(f"[Action]: Sleeping for {secs} seconds...")
            await asyncio.sleep(float(secs))
            continue
        elif is_shell_command(user_input):
            await run_shell_command(user_input)
            await asyncio.sleep(float(getProperty("modelSleep", default=0.25)))
            continue

        try:
            content = types.Content(role="user", parts=[types.Part(text=user_input)])
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
                display_text(f"[ArchitectBot]: {final_response}")
            else:
                display_text(f"[ArchitectBot]: [No final response]")

        except Exception as e:
            sys.stdout = sys.__stdout__
            sys.stdout.flush()
            display_text(f"- An error occurred: {str(e)}", type="error")


# ---------------------------------------------------------
# CLI Entry
# ---------------------------------------------------------
async def run_cli():
    parser = argparse.ArgumentParser(description="Process Architect Orchestrator")
    parser.add_argument(
        "-f", "--file",
        dest="file",
        type=str,
        required=False,
        help="Process file instructions from a text file (one instruction per line). If not provided, starts in interactive chat mode."
    )
    args = parser.parse_args()

    if args.file:
        await process_file(args.file)
        return

    display_text("- Starting Process Architect Orchestrator in local chat mode...")
    await start_local_chat()

# ---------------------------------------------------------
# MAIN EXECUTION BLOCK
# ---------------------------------------------------------
if __name__ == "__main__":
    logger.debug("Pipeline initialized and ready for execution.")
    asyncio.run(run_cli())