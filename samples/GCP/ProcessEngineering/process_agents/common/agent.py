# process_agents/agent.py

import os
import signal
import sys
import logging
import secrets
import threading
import time
import hmac
import json
import queue
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
import pkgutil
import google
import google.adk
from google.adk.agents import LoopAgent, SequentialAgent, LlmAgent

# `google` and `google.adk` are namespace packages -- multiple
# independently-installed distributions (this app's own code plus
# google-adk, google-genai, etc.) all contribute modules under the same
# `google.*` import path. extend_path ensures Python's import machinery
# searches every installed location for submodules under these names
# instead of only the first `google`/`google.adk` directory it finds,
# which would otherwise hide sibling packages installed elsewhere on
# sys.path.
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

    # Every branch below (anthropic/openai/bedrock) is routed through
    # LiteLLM (see agent_wrappers._resolve_model). Some models impose
    # stricter parameter constraints than our own per-agent "quick knobs"
    # assume -- e.g. litellm rejects any non-default temperature outright
    # for some Claude models ("litellm.UnsupportedParamsError: ... Only
    # temperature=1 is supported"). drop_params tells litellm to silently
    # drop a param a given model doesn't support instead of raising, so
    # each agent's own tuned temperature/top_p still applies for models
    # that support it and is harmlessly ignored for ones that don't.
    import litellm
    litellm.drop_params = True

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
# WARNING+ only (retries, backoff, cache/eviction errors, etc.) -- LOGLEVEL
# below is usually DEBUG, which is fine for the file but would flood an
# interactive session. Without this handler attached at all, a long-running
# pipeline that's silently retrying/backing off (e.g. on 429s, or a stalled
# call) produces zero visible signal on the terminal -- it just looks hung.
console_handler.setLevel(logging.WARNING)
logger = logging.getLogger("ProcessArchitect")
logger.addHandler(file_handler)
logger.addHandler(console_handler)
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

# Validate instruction files BEFORE importing agent_registry, not after.
# agent_registry transitively imports every design/process/cloudarch agent
# module, each of which constructs its agents (with instruction_file=...)
# at import time -- a missing file previously raised FileNotFoundError
# straight out of that import, crashing with a raw traceback, well before
# this validator ever got a chance to run and report it cleanly. This
# function has no dependency on agent_registry, so running it first is safe.
logger.debug("Validating instruction files...")
if not validate_instruction_files():
    logger.error("Instruction file validation failed. Aborting pipeline.")
    sys.exit(1)
logger.debug("Pipeline initialised...")

# Import sub-agents
from .agent_registry import (
    full_design_pipeline,
    consultant_agent,
    consultant_design_agent,
    cloudarch_pipeline,
    consultant_cloudarch_agent,
    cloudarch_simulation_query_agent,
    scenario_tester_agent,
    design_scenario_tester_agent,
    update_design_pipeline,
    simulation_query_agent,
    design_simulation_query_agent,
    build_doc_creation_agent,
    SubprocessDriverAgent,
    full_design_doc_pipeline,
    update_design_doc_pipeline,
    requirements_summary_agent,
    requirements_consultant_agent,
)

# Signal handler for abnormal errors
def handler(signum, frame):
    # Restore the real stdout/stderr first -- if the crash happens while
    # silence_console() has stdout redirected to CleanedStdout (mid
    # generation-pipeline run), printing this message before restoring
    # would otherwise vanish into the log file instead of reaching the
    # user's terminal.
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
        consultant_cloudarch_agent,
        cloudarch_simulation_query_agent,
        scenario_tester_agent,
        design_scenario_tester_agent,
        update_design_pipeline,
        simulation_query_agent,
        design_simulation_query_agent,
        build_doc_creation_agent("Create_Doc_Agent"),
        SubprocessDriverAgent(name="Subprocess_Driver_Agent_Main"),
        full_design_doc_pipeline,
        update_design_doc_pipeline,
        requirements_summary_agent,
        requirements_consultant_agent,
    ],
)

# ---------------------------------------------------------
# LOCAL CHAT LOOP SUPPORT
# ---------------------------------------------------------
from google.adk.runners import Runner
from google.adk.agents import RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
import asyncio
import uuid

# root_agent transfers between many sub_agents (see sub_agents=[...] above), so
# every transfer swaps the system instruction/tool set and would otherwise
# resend the whole (often 40k+ token, per output/logs/*.log) prompt uncached.
# context_cache_config gives each agent its own cache across turns.
#
# events_compaction_config addresses the other half of that same growth: the
# full_design_doc_pipeline chains ~15 sub-agents through one shared session,
# each of whose turns get appended to it, so a single elaborate run's prompt
# can balloon into the hundreds of thousands of tokens purely from that
# shared history (observed: ~850k tokens/call on a real run, which then blew
# through the per-minute quota and forced long retry/backoff cycles). Every
# stage that reads real prior output does so via a tool call against files
# on disk (load_master_process_json etc.), not by re-reading it out of chat
# history, so it's safe to let ADK compact old conversation turns into an
# LLM-generated summary once a single agent's own prompt crosses
# contextCompactionTokenThreshold, keeping only the last
# contextCompactionEventRetention raw events for continuity. This runs
# per-agent, mid-pipeline (before each model call), not just between
# separate user turns.
root_app = App(
    name="ProcessArchitect",
    root_agent=root_agent,
    context_cache_config=ContextCacheConfig(),
    events_compaction_config=EventsCompactionConfig(
        token_threshold=int(getProperty("contextCompactionTokenThreshold", default=150000)),
        event_retention_size=int(getProperty("contextCompactionEventRetention", default=8)),
    ),
)

# Circuit breaker of last resort for a single invocation (one top-level user
# turn, including every sub-agent it delegates through). loopIterations/
# stop_if_ready only cap how many times an *outer* LoopAgent repeats; they do
# nothing to bound how long any *one* agent's own turn can run once it starts
# repeatedly calling tools without producing a final response. Observed for
# real: an agent stuck re-submitting a bad payload to a validator call after
# call, never converging, never handing off to Stop_Controller -- 68+ minutes
# and still going when killed by hand. ADK's own default here is 500, which
# at that run's ~90-150s/call pace would still have meant hours, not minutes.
# maxLlmCallsPerInvocation is intentionally generous relative to what a
# normal full pipeline run needs (so it won't cut off legitimate work) --
# it's a backstop against a *future* stuck-loop pattern we haven't seen yet,
# not a performance tuning knob. If it fires, the invocation raises rather
# than silently truncating output, so it's diagnosable rather than mysterious.
RUN_CONFIG = RunConfig(
    max_llm_calls=int(getProperty("maxLlmCallsPerInvocation", default=200))
)

# A SEPARATE RunConfig, used only by POST /chat/stream (see build_web_app),
# with streaming_mode=StreamingMode.SSE -- this makes the Runner yield
# genuine partial/typewriter-effect Events (event.partial=True) as the model
# generates them, in addition to the aggregated final one, rather than only
# ever emitting one complete Event per turn like RUN_CONFIG's default
# StreamingMode.NONE does. Deliberately NOT applied to RUN_CONFIG itself:
# every other call site (interactive REPL, -i/-f modes, POST /chat) only
# ever reads event.is_final_response(), which stays False for partial
# events regardless -- but keeping this scoped to the one route that
# actually consumes partial events keeps those call sites' behavior
# byte-for-byte unchanged rather than relying on that not mattering.
STREAMING_RUN_CONFIG = RunConfig(
    max_llm_calls=int(getProperty("maxLlmCallsPerInvocation", default=200)),
    streaming_mode=StreamingMode.SSE,
)


def display_text(text: str, type: str = "info", end: str = "\n"):
    # `end` exists so run_shell_command can print already-newline-terminated
    # subprocess stdout without doubling it up (display_text(..., end=""))
    # -- previously missing entirely, so that call raised TypeError and
    # silently dropped the shell command's real output, reporting a
    # (fake) execution error instead.
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
        print(f"{colour}{text}{ANSI_RESET}", end=end)
    elif type == "warning":
        print(f"{warning}[Warning]: {text}{ANSI_RESET}", end=end)
    elif type == "error":
        print(f"{error}[Error]: {text}{ANSI_RESET}", end=end)
    sys.stdout.flush()

def is_shell_command(text: str) -> bool:
    # A leading "$" is this CLI's escape convention for running a raw
    # shell command instead of sending the line to the agent -- used by
    # both the interactive chat loop and -f <file> batch mode.
    if text is None:
        return False
    return text.strip().startswith("$")


async def run_shell_command(cmdline: str):
    """Executes a "$ <command>" line (see is_shell_command) via the shell
    and streams its stdout/stderr through display_text, rather than
    sending it to the agent."""
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
# Guards the lazy-init of _web_runner/_web_session_service below: Flask's
# threaded request handling means two concurrent first requests can both see
# them as None and each build their own Runner/InMemorySessionService, after
# which whichever one wins the final "if None" assignment leaves the other
# thread's session created in a service the shared runner doesn't use.
_web_runtime_init_lock = threading.Lock()
_WEB_APP_NAME = "ProcessArchitect"
WEB_SESSION_COOKIE = "process_architect_session"

# ---------------------------------------------------------
# WEB SERVICE: AUTH + RATE LIMITING
# ---------------------------------------------------------
# --detached defaults to HTTPS on 127.0.0.1 (loopback-only, see
# run_web_service) -- widening host beyond loopback with no webApiKey
# configured makes run_web_service refuse to start (see the
# is_loopback/api_key_configured/allow_insecure check there) rather than
# silently exposing an unauthenticated, model-backed chat API. Both
# webApiKey and webRateLimitPerMinute remain opt-in config rather than
# hardcoded on, since this
# is still a local sample tool by default, but they give an easy,
# no-new-dependency way to lock it down before exposing it further.
_web_rate_limit_lock = threading.Lock()
_web_rate_limit_state: dict = {}  # client key -> [monotonic timestamps within the current window]


def _check_rate_limit(client_key: str, limit_per_minute: int) -> bool:
    """Fixed 60s sliding window per client_key. limit_per_minute <= 0 disables
    the check entirely (returns True unconditionally)."""
    if limit_per_minute <= 0:
        return True
    now = time.monotonic()
    window_start = now - 60.0
    with _web_rate_limit_lock:
        timestamps = [t for t in _web_rate_limit_state.get(client_key, ()) if t >= window_start]
        if len(timestamps) >= limit_per_minute:
            _web_rate_limit_state[client_key] = timestamps
            return False
        timestamps.append(now)
        _web_rate_limit_state[client_key] = timestamps
        return True


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

    if _web_runner is None or _web_session_service is None:
        with _web_runtime_init_lock:
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
        run_config=RUN_CONFIG,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text

    return web_session_id, (final_response or "")


async def _stream_chat_turn(user_id: str, session_id: str, query: str, event_queue: "queue.Queue") -> None:
    """
    Runs one query through _web_runner with STREAMING_RUN_CONFIG, pushing
    an incremental update dict into event_queue after every meaningful
    Event instead of collecting only the final one like _run_chat_turn
    does. A None sentinel is always pushed last (even after an error) so
    the (synchronous) reading side -- see build_web_app's /chat/stream --
    knows when to stop.

    Runs inside its own thread's event loop rather than the Flask
    request's own, since Flask/WSGI route functions must stay plain
    synchronous generators -- see /chat/stream's own docstring for the
    full bridging picture.

    Pushed dicts are shaped like one of:
      {"status": "progress", "origin": "<agent>", "text": "<short note>"}
      {"status": "delta", "text": "<answer text SO FAR -- always the full
                                     current state, not a fragment, so a
                                     client can just replace what it
                                     shows with this>"}
      {"status": "done", "response": "<final answer>"}
      {"status": "error", "error": "..."}
    """
    content = types.Content(role="user", parts=[types.Part(text=query)])
    answer_so_far = ""
    last_progress_author: Optional[str] = None
    try:
        async for event in _web_runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
            run_config=STREAMING_RUN_CONFIG,
        ):
            if event.partial and event.content and event.content.parts:
                # Genuine typewriter-effect chunk (see StreamingMode.SSE's
                # own docstring) -- skip function-call parts, which are
                # internal tool-call-argument streaming, not user-facing
                # text.
                chunk = "".join(
                    part.text or "" for part in event.content.parts if not part.function_call
                )
                if chunk:
                    answer_so_far += chunk
                    event_queue.put({"status": "delta", "text": answer_so_far})
                continue

            function_calls = event.get_function_calls()
            if function_calls:
                names = ", ".join(fc.name for fc in function_calls if fc.name)
                event_queue.put({
                    "status": "progress",
                    "origin": event.author or "agent network",
                    "text": f"Calling {names}" if names else "Calling a tool...",
                })
                last_progress_author = event.author
                continue

            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(part.text or "" for part in event.content.parts if part.text)
                if final_text:
                    answer_so_far = final_text
                    event_queue.put({"status": "delta", "text": answer_so_far})
                continue

            # Any other event (e.g. a hand-off to a different sub-agent)
            # is still worth a lightweight note so the UI shows SOMETHING
            # changed, rather than going quiet between deltas -- but only
            # when the active agent actually changes, not on every one of
            # these, to avoid flooding the client with near-duplicates.
            if event.author and event.author != last_progress_author:
                last_progress_author = event.author
                # text deliberately does NOT repeat event.author -- the
                # client already prefixes progress notes with "origin",
                # so including it here too would read as "X: X is
                # responding...".
                event_queue.put({
                    "status": "progress",
                    "origin": event.author,
                    "text": "responding...",
                })

        event_queue.put({"status": "done", "response": answer_so_far})
    except Exception:
        logger.exception("Web chat stream error")
        event_queue.put({"status": "error", "error": "An internal error has occurred."})
    finally:
        event_queue.put(None)


def build_web_app(https: bool = True):
    """
    Build (but do not run) the Flask REST app for -d/--detached mode.

    Exposes:
      POST   /chat            {"query": "...", "session_id": "..." (optional)}
                               -> {"status": "ok", "session_id": "...",
                                   "query": "...", "response": "..."}
      POST   /chat/stream      Same request body; response is
                               text/event-stream instead -- a live
                               sequence of `data: {...}\n\n` events
                               shaped like _stream_chat_turn's own
                               docstring describes, ending with a
                               {"status": "done", "response": "..."}
                               event. See that function for why/how.
      DELETE /chat/<session_id>  Drops server-side state for that session.
      GET    /artifacts/<name>  "process" or "design" -> {"status": "ok",
                               "name": "...", "data": {...the parsed
                               output/<name>_data.json...}}, or 404 if
                               that pipeline hasn't produced one yet.
      GET    /status           Liveness probe.

    Sessions are tracked both by an explicit "session_id" JSON field (for
    plain REST/CLI clients) and by a cookie (for browser-based clients) --
    whichever is supplied wins; if neither resolves to a known session, a
    new one is created and handed back both ways.

    Every route except /status requires webApiKey (if configured) via an
    "Authorization: Bearer <key>" or "X-API-Key" header, and is capped at
    webRateLimitPerMinute requests/minute per source IP -- see the AUTH +
    RATE LIMITING block above for why.

    CORS is enabled permissively (reflecting whatever Origin the browser
    sends, no credentials) -- see _add_cors_headers below for why this
    doesn't widen this service's actual exposure. This is what lets
    samples/WebClient/ProcessEngineering (a static page with no backend
    of its own) call this API directly from a browser.
    """
    from flask import Flask, request, jsonify, make_response, Response

    web_app = Flask("ProcessArchitectWebService")
    web_app.secret_key = getProperty("FLASK_SECRET_KEY") or secrets.token_hex(32)

    api_key = getProperty("webApiKey")
    if not api_key:
        display_text(
            "No webApiKey configured -- the web service is UNAUTHENTICATED. Anyone who can "
            "reach it can create sessions and trigger model calls that may incur cost or "
            "exhaust resources. Set webApiKey in properties/agentapp.properties (or the "
            "WEBAPIKEY env var) before exposing this beyond localhost.",
            type="warning",
        )
    rate_limit_per_minute = int(getProperty("webRateLimitPerMinute", default=30))

    def _api_key_matches(candidate: Optional[str]) -> bool:
        # Constant-time comparison: a naive `==` leaks how many leading
        # characters matched via response-time differences, which is a real
        # (if slow) way to brute-force a shared secret over the network.
        return isinstance(candidate, str) and hmac.compare_digest(candidate, api_key)

    @web_app.after_request
    def _add_cors_headers(response):
        # Reflects whatever Origin the browser sends (no credentials
        # involved) rather than a fixed allowlist -- this is a local
        # sample tool, not a multi-tenant production service, and the web
        # client (samples/WebClient/ProcessEngineering) authenticates each
        # turn via an explicit session_id in the request body rather than
        # a cross-origin cookie, so this doesn't widen the actual exposure
        # beyond what webApiKey/rate-limiting already gate. Lets that same
        # static client talk to this backend AND the neuro-san port's own
        # --flask REST API (which mirrors this contract exactly) from a
        # single page regardless of which origin it's served from.
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response

    @web_app.before_request
    def _enforce_web_controls():
        if request.method == "OPTIONS":
            return ("", 204)  # CORS preflight -- no auth, no rate limit

        if request.path == "/status":
            return None  # liveness probe stays open: no auth, no rate limit

        if api_key:
            auth_header = request.headers.get("Authorization", "")
            bearer_token = auth_header[7:] if auth_header.startswith("Bearer ") else None
            if not (_api_key_matches(bearer_token) or _api_key_matches(request.headers.get("X-API-Key"))):
                return jsonify({"status": "error", "error": "Unauthorized"}), 401

        if not _check_rate_limit(request.remote_addr or "unknown", rate_limit_per_minute):
            return jsonify({"status": "error", "error": "Rate limit exceeded"}), 429

        return None

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
        except Exception:
            logger.exception("Web chat error")
            return jsonify({
                "status": "error",
                "error": "An internal error has occurred.",
            }), 500

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

    @web_app.route("/chat/stream", methods=["POST"])
    def chat_stream():
        """
        Streaming counterpart to POST /chat: same request body, same
        session resolution/cookie, but the response is
        text/event-stream -- a live sequence of
        `data: {...}\n\n` progress/delta/done events (see
        _stream_chat_turn's own docstring for their exact shape) instead
        of one blocking JSON body sent only once the whole turn is done.
        POST /chat is unchanged and still the right choice for any
        caller that just wants the final text (scripts, curl,
        server-to-server callers).

        Flask/WSGI route functions must stay plain synchronous
        generators, but _web_runner.run_async is an async generator --
        bridged here by running _stream_chat_turn to completion inside
        ITS OWN asyncio event loop on a background thread, which pushes
        each incremental update into a thread-safe queue.Queue; this
        (synchronous) generator just blocks on that queue and yields
        SSE-formatted lines as items arrive. Session resolution itself
        happens synchronously, up front, in this request's own thread
        (not the background one) -- exactly like POST /chat already
        does via asyncio.run(...) -- so the session cookie can be set on
        the response before the streaming body starts.
        """
        payload = request.get_json(silent=True) or {}
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            return jsonify({
                "status": "error",
                "error": "Field 'query' is required and must be a non-empty string.",
            }), 400

        session_id = payload.get("session_id") or request.cookies.get(WEB_SESSION_COOKIE)
        web_session_id, user_id, adk_session_id = asyncio.run(_get_or_create_web_session(session_id))

        def generate():
            event_queue: "queue.Queue" = queue.Queue()
            thread = threading.Thread(
                target=lambda: asyncio.run(
                    _stream_chat_turn(user_id, adk_session_id, query.strip(), event_queue)
                ),
                daemon=True,
            )
            thread.start()
            while True:
                item = event_queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps({**item, 'session_id': web_session_id})}\n\n"

        resp = Response(generate(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"  # disable proxy buffering if ever fronted by nginx
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
            entry = _web_sessions.pop(session_id, None)
        existed = entry is not None
        # Popping _web_sessions only forgets the cookie/session_id mapping;
        # the ADK session itself (and its event history) lives in
        # _web_session_service until explicitly deleted, or it leaks for the
        # life of the process across repeated create/delete cycles.
        if existed and _web_session_service is not None:
            asyncio.run(
                _web_session_service.delete_session(
                    app_name=_WEB_APP_NAME,
                    user_id=entry["user_id"],
                    session_id=entry["session_id"],
                )
            )
        return jsonify({"status": "ok", "session_id": session_id, "cleared": existed})

    @web_app.route("/artifacts/<name>", methods=["GET"])
    def artifact(name):
        """
        Read-only access to this project's own output/process_data.json or
        output/design_data.json, for the web client's "Process / Design"
        tab -- a hierarchical viewer of whichever pipeline's current
        artifact, not something a chat turn's response text would
        otherwise expose. Both backends serve this the same way (the
        neuro-san port's build_web_app has an identical route) and both
        keep these files at an identical path, so the client's fetch
        logic doesn't need to know which backend it's talking to.

        Deliberately a raw file read, NOT the existing
        load_master_process_json/load_master_design_json helpers in
        .utils -- those silently fall back to a blank template when the
        file is missing (useful for a pipeline about to populate one, not
        for a debugging viewer that needs to tell "genuinely not generated
        yet" apart from "here's an empty template"), so this reports a
        real 404 instead.
        """
        from .utils_agent import PROJECT_ROOT

        filenames = {"process": "process_data.json", "design": "design_data.json"}
        filename = filenames.get(name)
        if filename is None:
            return jsonify({
                "status": "error",
                "error": f"Unknown artifact '{name}' -- use 'process' or 'design'.",
            }), 400

        path = os.path.join(PROJECT_ROOT, "output", filename)
        if not os.path.exists(path):
            return jsonify({
                "status": "error",
                "error": f"No {filename} found yet -- run the {name} pipeline at least once, then try again.",
            }), 404

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            logger.exception("Failed to read/parse %s", filename)
            return jsonify({
                "status": "error",
                "error": f"Could not read {filename} -- see server logs.",
            }), 500

        return jsonify({"status": "ok", "name": name, "data": data})

    @web_app.route("/status", methods=["GET"])
    def status():
        return jsonify({"status": "live"})

    return web_app


def run_web_service(port: Optional[int], use_https: bool):
    """Build and serve the Flask REST app until interrupted."""
    host = getProperty("host", default="127.0.0.1")

    is_loopback = host in ("127.0.0.1", "localhost", "::1")
    api_key_configured = bool(getProperty("webApiKey"))
    allow_insecure = bool(getProperty("allowInsecureWebService", default=False))
    if not is_loopback and not api_key_configured and not allow_insecure:
        display_text(
            f"Refusing to start: host={host!r} is reachable beyond localhost and no webApiKey "
            "is configured, which would expose the chat API (and the model calls/cost behind "
            "it) to any client that can reach this port. Fix one of: set webApiKey in "
            "properties/agentapp.properties (or the WEBAPIKEY env var); set host=127.0.0.1 to "
            "restrict this to local access only; or set allowInsecureWebService=True to "
            "explicitly accept the risk.",
            type="error",
        )
        sys.exit(1)

    web_app = build_web_app(https=use_https)

    listen_port = port if port is not None else (443 if use_https else 8080)

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
    """
    -f <file> batch mode: reads `file_path` line by line and submits each
    logical line (see the backslash-continuation handling below) to the
    agent in turn, as if it had been typed interactively one at a time.
    Recognizes the same control lines as the interactive REPL (exit/quit/
    stop, clear, "#" comments, sleep/wait, "$ ..." shell commands) via
    handle_logical_line.
    """
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

        # A failure on this one line (a transient API error, the
        # max_llm_calls circuit breaker, a tool raising deep inside a
        # pipeline, etc.) must not abort the rest of the file -- this is
        # the same per-turn try/except start_local_chat's REPL loop already
        # has (see below), so an interactive session survives a bad turn
        # and keeps prompting. This function previously had no such guard:
        # any exception here propagated out of the "for raw_line in f"
        # loop in process_file() straight into its own outer try/except,
        # which prints one error and calls sys.exit(1) -- silently
        # abandoning every remaining line in the file after whichever one
        # happened to fail, which is what "only processes the first
        # command" looks like from the outside.
        try:
            content = types.Content(role="user", parts=[types.Part(text=line)])
            final_response = None
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
                run_config=RUN_CONFIG,
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
            new_message=content,
            run_config=RUN_CONFIG,
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
                new_message=content,
                run_config=RUN_CONFIG,
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
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        # Ctrl+C in ANY mode -- interactive chat, -f/-i, or -d's blocking
        # Flask dev server loop. asyncio.run()'s own Runner cancels the
        # in-flight task on SIGINT and re-raises that as KeyboardInterrupt
        # once run_until_complete unwinds (see cpython's asyncio/
        # runners.py) -- left uncaught, that surfaces as a raw
        # CancelledError-then-KeyboardInterrupt traceback instead of a
        # clean exit (the neuro-san port's cli.py has the identical
        # asyncio.run(run_cli()) shape and the identical fix).
        display_text("\n- Interrupted -- shutting down.")
        sys.exit(0)