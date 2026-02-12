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
)

import argparse  # CLI args

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
# Ensure flush is available
file_handler.flush = lambda: file_handler.stream.flush()

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_format)

logger = logging.getLogger("ProcessArchitect")
logger.addHandler(file_handler)
# logger.addHandler(console_handler)  # keep disabled unless needed
logger.propagate = False
logging.getLogger("google_adk.google.adk.agents.llm_agent").setLevel(logging.ERROR)

LOGLEVEL = getProperty("LOGLEVEL")
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
if logger:
    logger.setLevel(LOGLEVEL)

runtime_file = os.path.join(log_dir, "runtime_errors.log")
if os.path.exists(runtime_file):
    try:
        os.remove(runtime_file)
    except Exception as e:
        logger.error(f"Failed to remove runtime file: {str(e)}")
sys.stderr = open(runtime_file, "a")

# Import sub-agents after logging is set up to ensure they use the same logger configuration
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
    print(f"\n\033[91m - Received signal {signame} ({signum}). Terminating Process Architect Orchestrator.\033[0m", end="\n")
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
root_agent = LlmAgent(
    name="Process_Architect_Orchestrator",
    model=getProperty("MODEL"),
    instruction=load_instruction("agent.txt"),
    sub_agents=[
        full_design_pipeline,
        consultant_agent,
        scenario_tester_agent,
        update_design_pipeline,
        simulation_query_agent,
        build_doc_creation_agent("Create_Doc_Agent"),
        SubprocessDriverAgent(name="Subprocess_Driver_Agent_Main"),
    ]
)

# ---------------------------------------------------------
# LOCAL CHAT LOOP SUPPORT
# ---------------------------------------------------------
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
import asyncio
import uuid

# ------------------- COMMON HELPERS -------------------

async def init_session_and_runner(app_name: str = "ProcessArchitect"):
    """
    Creates a single ADK session and Runner. Reuse across file-mode and chat-mode.
    Returns: (runner, user_id, session_id)
    """
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


def is_shell_command(text: str) -> bool:
    """Detects a host OS command: lines starting with '$ ' or '$<cmd>'."""
    if text is None:
        return False
    stripped = text.strip()
    return stripped.startswith("$")


async def run_shell_command(cmdline: str):
    """
    Executes a host OS command and prints output.
    Accepts lines like: "$ ls /tmp"
    """
    import shlex
    import platform

    # Strip leading '$'
    stripped = cmdline.strip()
    command = stripped[1:].strip() if stripped.startswith("$") else stripped

    if not command:
        print("\033[93m[Shell]: No command to run.\033[0m")
        return

    print(f"\033[96m[Shell]: {command}\033[0m")

    # Use the system shell to support complex commands, pipes, redirects, etc.
    # asyncio.create_subprocess_shell is portable across macOS/Linux/Windows (uses cmd.exe on Windows).
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if stdout:
            try:
                print(stdout.decode("utf-8", errors="replace"), end="")
            except Exception:
                print(str(stdout))
        if stderr:
            try:
                # print stderr in red
                sys.stderr.write("\033[91m" + stderr.decode("utf-8", errors="replace") + "\033[0m")
            except Exception:
                sys.stderr.write(str(stderr))

        if proc.returncode != 0:
            print(f"\033[91m[Shell]: Exit code {proc.returncode}\033[0m")

    except FileNotFoundError:
        print("\033[91m[Shell]: Command not found.\033[0m")
    except Exception as e:
        print(f"\033[91m[Shell]: Error executing command: {e}\033[0m")


# ------------------- FILE MODE -------------------

async def process_file(file_path: str):
    """
    Sends each line of a file to the orchestrator as if typed by a user, one line at a time.
    Supports:
      - '# comment' lines (ignored)
      - 'sleep N' or 'wait N' (delay)
      - '$ <shell command>' (run OS command and print output)
      - 'exit/quit/stop' (terminate)
    """
    try:
        with open(file_path, "r", encoding="utf-8-sig") as _:
            pass
    except Exception as e:
        print(f"\033[91m- Error opening file '{file_path}': {e}\033[0m")
        sys.exit(1)

    runner, user_id, session_id = await init_session_and_runner()

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue

                # Commands handled locally
                if line.lower() in ["exit", "quit", "stop"]:
                    print("Exiting Process Architect Orchestrator.")
                    break
                elif line.startswith("#"):
                    print(f"\033[94m[Comment]: {line}\033[0m")
                    continue
                elif line.lower().startswith("sleep") or line.lower().startswith("wait"):
                    parts = line.split()
                    secs = parts[1] if len(parts) > 1 else getProperty("modelSleep", default=0.5)
                    print(f"\033[93m[Action]: Sleeping for {secs} seconds...\033[0m")
                    await asyncio.sleep(float(secs))
                    continue
                elif is_shell_command(line):
                    await run_shell_command(line)
                    # brief pause to avoid burst
                    await asyncio.sleep(float(getProperty("modelSleep", default=0.25)))
                    continue

                # Otherwise, send to the orchestrator as a user message
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
                    print(f"\033[94m[ArchitectBot]: {final_response}\033[0m")
                else:
                    print("\033[94m[ArchitectBot]: [No final response]\033[0m")

                await asyncio.sleep(float(getProperty("modelSleep", default=0.5)))

    except Exception as e:
        logger.error(f"Error during file processing: {str(e)}")
        sys.stdout = sys.__stdout__
        sys.stdout.flush()
        print(f"\n\033[0m - Error processing file: {str(e)}", end="\n")
        sys.exit(1)


# ------------------- INTERACTIVE MODE -------------------

async def start_local_chat():
    print("\nProcess Architect Orchestrator (local mode)")
    print("Type 'exit' to quit.\n")

    runner, user_id, session_id = await init_session_and_runner()

    while True:
        user_input = input("[user]: ").strip()

        # Local commands
        if user_input.lower() in ["exit", "quit", "stop"]:
            print("Exiting Process Architect Orchestrator.")
            break
        elif user_input.startswith("#"):
            print(f"\033[94m[Comment]: {user_input}\033[0m")
            continue
        elif user_input.lower().startswith("sleep") or user_input.lower().startswith("wait"):
            parts = user_input.split()
            secs = parts[1] if len(parts) > 1 else getProperty("modelSleep", default=0.5)
            print(f"\033[93m[Action]: Sleeping for {secs} seconds...\033[0m")
            await asyncio.sleep(float(secs))
            continue
        elif is_shell_command(user_input):
            await run_shell_command(user_input)
            await asyncio.sleep(float(getProperty("modelSleep", default=0.25)))
            continue

        # Send to orchestrator
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
                print(f"\n\033[94m[ArchitectBot]: {final_response}\033[0m")
            else:
                print("\n\033[94m[ArchitectBot]: [No final response]\033[0m")

        except Exception as e:
            logger.error(f"Error during chat loop: {str(e)}")
            sys.stdout = sys.__stdout__
            sys.stdout.flush()
            print(f"\n\033[0m - An error occurred: {str(e)}", end="\n")


# ---------------------------------------------------------
# CLI Entry (Refactored)
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

    print("\033[92m- Starting Process Architect Orchestrator in local chat mode...\033[0m", end="\n")
    await start_local_chat()


# ---------------------------------------------------------
# MAIN EXECUTION BLOCK
# ---------------------------------------------------------
if __name__ == "__main__":
    logger.debug("Pipeline initialized and ready for execution.")
    asyncio.run(run_cli())