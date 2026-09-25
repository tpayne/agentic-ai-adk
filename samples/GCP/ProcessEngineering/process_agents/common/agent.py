# process_agents/agent.py

import os
import signal
import sys
import logging
import secrets
import threading
from typing import Optional
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

def configure_model_provider(model: str) -> None:
    """
    Given a MODEL string, verify the right credentials are present and set
    ADK_MODEL_PROVIDER accordingly.

    Supported forms:
      - Bare Gemini name (no "/"), e.g. "gemini-3-flash-preview"
          -> Vertex AI if GOOGLE_CLOUD_PROJECT/GOOGLE_PROJECT_ID is set,
             else the Gemini API if GOOGLE_API_KEY is set.
      - "anthropic/..."  -> requires ANTHROPIC_API_KEY
      - "openai/..."     -> requires OPENAI_API_KEY
      - "bedrock/..."    -> requires AWS region + credentials
    """
    # --- Bare Gemini model name: native ADK path, not LiteLLM ---
    if "/" not in model:
        project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_PROJECT_ID")
        if project:
            os.environ["ADK_MODEL_PROVIDER"] = "vertex"
            os.environ["GOOGLE_CLOUD_LOCATION"] = getProperty("GOOGLE_CLOUD_LOCATION", default="us-central1")
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
            os.environ["GOOGLE_CLOUD_PROJECT"] = project
        elif os.getenv("GOOGLE_API_KEY"):
            os.environ["ADK_MODEL_PROVIDER"] = "api_key"
        else:
            raise EnvironmentError(
                f"MODEL='{model}' is a Gemini model — set GOOGLE_CLOUD_PROJECT or "
                "GOOGLE_PROJECT_ID (for Vertex AI), or GOOGLE_API_KEY (for the Gemini "
                "API), in your environment."
            )
        return

    provider = model.split("/", 1)[0]

    # --- Anthropic direct ---
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise EnvironmentError(f"MODEL='{model}' requires ANTHROPIC_API_KEY to be set.")
        os.environ["ADK_MODEL_PROVIDER"] = "anthropic"

    # --- OpenAI ---
    elif provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise EnvironmentError(f"MODEL='{model}' requires OPENAI_API_KEY to be set.")
        os.environ["ADK_MODEL_PROVIDER"] = "openai"

    # --- AWS Bedrock ---
    elif provider == "bedrock":
        region = (
            os.getenv("AWS_REGION_NAME")
            or os.getenv("AWS_REGION")
            or getProperty("AWS_REGION_NAME", default=None)
        )
        if not region:
            raise EnvironmentError(
                f"MODEL='{model}' requires AWS_REGION_NAME (or AWS_REGION) to be set."
            )
        os.environ["AWS_REGION_NAME"] = region
        # Note: we can't reliably detect IAM-role auth (EC2/ECS/EKS instance
        # profiles, IRSA) from env vars alone, so we only hard-fail when
        # neither static keys nor a named profile are present — the common
        # "forgot to configure anything locally" case.
        if not (
            (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))
            or os.getenv("AWS_PROFILE")
        ):
            raise EnvironmentError(
                f"MODEL='{model}' requires AWS credentials: set "
                "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY, AWS_PROFILE, or run "
                "under an IAM role with Bedrock access."
            )
        os.environ["ADK_MODEL_PROVIDER"] = "bedrock"
        import litellm
        litellm.modify_params = True  # required for multi-turn tool calls on Bedrock

    else:
        raise EnvironmentError(
            f"Unrecognized provider prefix '{provider}/' in MODEL='{model}'. "
            "Supported: anthropic/, openai/, bedrock/ (or a bare Gemini name)."
        )


# --- usage ---
MODEL = getProperty("MODEL", default="gemini-3-flash-preview")
configure_model_provider(MODEL)

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
    consultant_design_agent,
    cloudarch_pipeline,
    scenario_tester_agent,
    design_scenario_tester_agent,
    update_design_pipeline,
    simulation_query_agent,
    design_simulation_query_agent,
    build_doc_creation_agent,
    SubprocessDriverAgent,
    full_design_doc_pipeline,
    update_design_doc_pipeline,
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
    instruction_file="common/agent.txt",
    before_model_callback=None,  # Disable before callback for root agent
    after_model_callback=None,   # Disable after callback for root agent
    sub_agents=[
        full_design_pipeline,
        consultant_agent,
        consultant_design_agent,
        cloudarch_pipeline,
        scenario_tester_agent,
        design_scenario_tester_agent,
        update_design_pipeline,
        simulation_query_agent,
        design_simulation_query_agent,
        build_doc_creation_agent("Create_Doc_Agent"),
        SubprocessDriverAgent(name="Subprocess_Driver_Agent_Main"),
        full_design_doc_pipeline,
        update_design_doc_pipeline,
    ],
)

# ---------------------------------------------------------
# LOCAL CHAT LOOP SUPPORT
# ---------------------------------------------------------
from google.adk.runners import Runner
from google.adk.apps import App
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
import asyncio
import uuid

# root_agent transfers between many sub_agents (see sub_agents=[...] above), so
# every transfer swaps the system instruction/tool set and would otherwise
# resend the whole (often 40k+ token, per output/logs/*.log) prompt uncached.
# context_cache_config gives each agent its own cache across turns.
root_app = App(
    name="ProcessArchitect",
    root_agent=root_agent,
    context_cache_config=ContextCacheConfig(),
)


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
    display_text(f"[Shell]: {command}")
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if stdout:
            display_text(stdout.decode("utf-8", errors="replace"), end="")

        if stderr:
            display_text(f"[Shell]: {stderr.decode('utf-8', errors='replace')}", type="error")

        if proc.returncode != 0:
            display_text(f"Shell command exited with code {proc.returncode}", type="error")

    except Exception as e:
        display_text(f"[Shell]: Error executing command: {e}", type="error")

async def init_session_and_runner(app_name: str = "ProcessArchitect"):
    # output/stop_counter.json persists across sessions on disk (LoopAgents
    # read/write it via stop_if_ready). It's normally cleared by Stage 1 of
    # the create/update pipelines (log_*_metadata's _remove_previous_approval_logs),
    # but that only runs if this session's first turn happens to route
    # through Stage 1. A killed prior run, or a first turn that transfers
    # straight into a later loop-bearing stage, can leave a stale nonzero
    # count that makes *this* session's loop escalate after too few
    # iterations. Since this always runs at the start of a fresh session
    # (including "clear"), reset it here unconditionally too.
    from .utils_agent import _reset_stop_counter, PROJECT_ROOT
    _reset_stop_counter(os.path.join(PROJECT_ROOT, "output", "stop_counter.json"))

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
        app=root_app,
        app_name=app_name,
        session_service=session_service
    )
    return runner, user_id, session_id


# ---------------------------------------------------------
# WEB SERVICE MODE (Flask REST API, activated by -d/--detached)
# ---------------------------------------------------------
# Maps an opaque web session id (handed to callers as "session_id" and also
# set as a cookie) to the underlying ADK user_id/session_id pair, so a single
# shared Runner/session_service can multiplex many concurrent chats.
_web_sessions: dict = {}
_web_sessions_lock = threading.Lock()
_web_runner = None
_web_session_service = None
_WEB_APP_NAME = "ProcessArchitect"
WEB_SESSION_COOKIE = "process_architect_session"


async def _get_or_create_web_session(existing_session_id: Optional[str]):
    """
    Resolve a web session id to its ADK (user_id, session_id) pair.

    If existing_session_id is missing/unknown, a fresh ADK session is
    created and registered under a new web session id, which is returned
    alongside the pair.
    """
    global _web_runner, _web_session_service

    if existing_session_id:
        with _web_sessions_lock:
            entry = _web_sessions.get(existing_session_id)
        if entry:
            return existing_session_id, entry["user_id"], entry["session_id"]

    if _web_session_service is None:
        _web_session_service = InMemorySessionService()
    if _web_runner is None:
        _web_runner = Runner(
            app=root_app,
            app_name=_WEB_APP_NAME,
            session_service=_web_session_service,
        )

    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    await _web_session_service.create_session(
        app_name=_WEB_APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={},
    )

    web_session_id = str(uuid.uuid4())
    with _web_sessions_lock:
        _web_sessions[web_session_id] = {"user_id": user_id, "session_id": session_id}
    return web_session_id, user_id, session_id


async def _run_chat_turn(existing_session_id: Optional[str], query: str):
    """Resolve/create the web session, then run one query through it."""
    web_session_id, user_id, session_id = await _get_or_create_web_session(existing_session_id)

    content = types.Content(role="user", parts=[types.Part(text=query)])
    final_response = None
    async for event in _web_runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text

    return web_session_id, (final_response or "")


def build_web_app(https: bool = True):
    """
    Build (but do not run) the Flask REST app for -d/--detached mode.

    Exposes:
      POST   /chat            {"query": "...", "session_id": "..." (optional)}
                               -> {"status": "ok", "session_id": "...",
                                   "query": "...", "response": "..."}
      DELETE /chat/<session_id>  Drops server-side state for that session.
      GET    /status           Liveness probe.

    Sessions are tracked both by an explicit "session_id" JSON field (for
    plain REST/CLI clients) and by a cookie (for browser-based clients) --
    whichever is supplied wins; if neither resolves to a known session, a
    new one is created and handed back both ways.
    """
    from flask import Flask, request, jsonify, make_response

    web_app = Flask("ProcessArchitectWebService")
    web_app.secret_key = getProperty("FLASK_SECRET_KEY") or secrets.token_hex(32)

    @web_app.route("/chat", methods=["POST"])
    def chat():
        payload = request.get_json(silent=True) or {}
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            return jsonify({
                "status": "error",
                "error": "Field 'query' is required and must be a non-empty string.",
            }), 400

        session_id = payload.get("session_id") or request.cookies.get(WEB_SESSION_COOKIE)

        try:
            web_session_id, response_text = asyncio.run(
                _run_chat_turn(session_id, query.strip())
            )
        except Exception as e:
            logger.error(f"Web chat error: {e}")
            return jsonify({"status": "error", "error": str(e)}), 500

        resp = make_response(jsonify({
            "status": "ok",
            "session_id": web_session_id,
            "query": query,
            "response": response_text,
        }))
        resp.set_cookie(
            WEB_SESSION_COOKIE,
            web_session_id,
            httponly=True,
            samesite="Lax",
            secure=https,
        )
        return resp

    @web_app.route("/chat/<session_id>", methods=["DELETE"])
    def chat_reset(session_id):
        with _web_sessions_lock:
            existed = _web_sessions.pop(session_id, None) is not None
        return jsonify({"status": "ok", "session_id": session_id, "cleared": existed})

    @web_app.route("/status", methods=["GET"])
    def status():
        return jsonify({"status": "live"})

    return web_app


def run_web_service(port: Optional[int], use_https: bool):
    """Build and serve the Flask REST app until interrupted."""
    web_app = build_web_app(https=use_https)

    listen_port = port if port is not None else (443 if use_https else 8080)
    host = getProperty("host", default="0.0.0.0")

    ssl_context = None
    if use_https:
        cert_file = getProperty("sslCertFile")
        key_file = getProperty("sslKeyFile")
        if cert_file and key_file:
            ssl_context = (cert_file, key_file)
        else:
            try:
                import OpenSSL  # noqa: F401
                ssl_context = "adhoc"
                display_text(
                    "No sslCertFile/sslKeyFile configured -- serving HTTPS with an "
                    "ad-hoc, self-signed certificate. Do not use this in production.",
                    type="warning",
                )
            except ImportError:
                display_text(
                    "HTTPS requested but no sslCertFile/sslKeyFile are configured and "
                    "'pyOpenSSL' is not installed (needed to generate an ad-hoc "
                    "certificate). Install pyOpenSSL, configure sslCertFile/sslKeyFile "
                    "in properties/agentapp.properties, or rerun with --http.",
                    type="error",
                )
                sys.exit(1)

    scheme = "https" if use_https else "http"
    display_text(f"- Starting Process Architect web service on {scheme}://{host}:{listen_port} (POST /chat)...")
    web_app.run(host=host, port=listen_port, ssl_context=ssl_context, threaded=True, debug=False)


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

    async def handle_logical_line(line: str) -> bool:
        """
        Process one fully-assembled (continuation-joined) instruction line.
        Returns True if the caller should stop reading further lines.
        """
        nonlocal runner, user_id, session_id

        if not line:
            return False

        if line.lower() in ["exit", "quit", "stop"]:
            display_text("Exiting Process Architect Orchestrator.")
            return True
        elif line.lower() == "clear":
            display_text("[Action]: Clearing all histories and resetting session...")
            runner, user_id, session_id = await init_session_and_runner()
            return False
        elif line.startswith("#"):
            display_text(f"[Comment]: {line}")
            return False
        elif line.lower().startswith("sleep") or line.lower().startswith("wait"):
            parts = line.split()
            secs = parts[1] if len(parts) > 1 else getProperty("modelSleep", default=0.5)
            display_text(f"[Action]: Sleeping for {secs} seconds...")
            await asyncio.sleep(float(secs))
            return False
        elif is_shell_command(line):
            await run_shell_command(line)
            await asyncio.sleep(float(getProperty("modelSleep", default=0.25)))
            return False

        display_text(f"[user-file]: {line}")

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
        return False

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            # Lines ending in "\" continue onto the next line, joined with a
            # single space rather than a newline, so:
            #   one \
            #   two three \
            #   four
            # is assembled and submitted as one logical line: "one two three four".
            continuation_parts = []

            for raw_line in f:
                bare = raw_line.rstrip("\n").rstrip("\r")

                if bare.rstrip().endswith("\\"):
                    continuation_parts.append(bare.rstrip()[:-1].strip())
                    continue

                continuation_parts.append(bare.strip())
                line = " ".join(part for part in continuation_parts if part)
                continuation_parts = []

                if await handle_logical_line(line):
                    break
            else:
                # File ended mid-continuation (trailing "\" on the last
                # line) -- submit whatever was accumulated rather than
                # silently dropping it.
                if continuation_parts:
                    line = " ".join(part for part in continuation_parts if part)
                    await handle_logical_line(line)

    except Exception as e:
        sys.stdout = sys.__stdout__
        sys.stdout.flush()
        display_text(f"- Error processing file: {str(e)}", type="error")
        sys.exit(1)


# ---------------------------------------------------------
# SINGLE-PROMPT MODE
# ---------------------------------------------------------
async def process_single_prompt(prompt: str):
    """Send one prompt, print the response, and return -- no REPL loop, no
    file parsing. For scripted/one-shot use, e.g.:
        python -m process_agents.agent -i "tell me what this process is about"
    """
    runner, user_id, session_id = await init_session_and_runner()

    try:
        content = types.Content(role="user", parts=[types.Part(text=prompt)])
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

    except Exception as e:
        sys.stdout = sys.__stdout__
        sys.stdout.flush()
        display_text(f"- An error occurred: {str(e)}", type="error")
        sys.exit(1)


# ---------------------------------------------------------
# INTERACTIVE MODE
# ---------------------------------------------------------
async def start_local_chat():
    display_text("Process Architect Orchestrator (local mode)")
    display_text("Type 'exit' to quit. Use '\\' at the end of a line to continue on a new line.")

    runner, user_id, session_id = await init_session_and_runner()

    while True:
        try:
            input_buffer = []
            while True:
                prompt_prefix = "[user]: " if not input_buffer else "... "
                raw_line = input(prompt_prefix)

                if raw_line.rstrip().endswith("\\"):
                    # Strip trailing backslash and keep accumulating
                    input_buffer.append(raw_line.rstrip()[:-1].strip())
                else:
                    input_buffer.append(raw_line.strip())
                    break

            # Joined with a single space, not a newline, so continuation
            # lines are submitted as one logical line -- consistent with
            # process_file's handling of "\" continuation.
            user_input = " ".join(part for part in input_buffer if part).strip()

        except (EOFError, KeyboardInterrupt):
            display_text("\nExiting Process Architect Orchestrator.")
            break

        if not user_input:
            continue

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
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-f", "--file",
        dest="file",
        type=str,
        required=False,
        help="Process file instructions from a text file (one instruction per line). If not provided, starts in interactive chat mode."
    )
    mode_group.add_argument(
        "-i", "--input",
        dest="input",
        type=str,
        required=False,
        help="Process a single prompt, print the response, and exit (no interactive loop). E.g.: -i \"tell me what this process is about\""
    )
    mode_group.add_argument(
        "-d", "--detached",
        dest="detached",
        action="store_true",
        help="Run as a detached Flask web service exposing a REST 'POST /chat' endpoint "
             "(multi-session via cookie or an explicit session_id), instead of the "
             "interactive/file/single-prompt CLI. See --http and --port."
    )
    parser.add_argument(
        "--http",
        dest="http",
        action="store_true",
        help="With --detached, serve plain HTTP on port 8080 instead of the default HTTPS on port 443."
    )
    parser.add_argument(
        "-p", "--port",
        dest="port",
        type=int,
        required=False,
        help="With --detached, override the listening port (default: 443 for HTTPS, 8080 for --http)."
    )
    args = parser.parse_args()

    if not args.detached and (args.http or args.port is not None):
        parser.error("--http and --port only apply with -d/--detached.")

    if args.detached:
        run_web_service(port=args.port, use_https=not args.http)
        return

    if args.file:
        await process_file(args.file)
        return

    if args.input:
        await process_single_prompt(args.input)
        return

    display_text("- Starting Process Architect Orchestrator in local chat mode...")
    await start_local_chat()

# ---------------------------------------------------------
# MAIN EXECUTION BLOCK
# ---------------------------------------------------------
if __name__ == "__main__":
    logger.debug("Pipeline initialized and ready for execution.")
    asyncio.run(run_cli())