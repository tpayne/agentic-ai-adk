# process_agents/agent.py

import os
import signal
import sys
import logging
import logging.handlers
import secrets
import threading
import time
import hmac
import inspect
import json
import queue
import base64
import binascii
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
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
      - "anthropic/..."      -> requires ANTHROPIC_API_KEY
      - "openai/..."         -> requires OPENAI_API_KEY
      - "bedrock/..."        -> requires AWS region + credentials
      - "ollama_chat/..."    -> local Ollama server; no API key required.
                               Optionally set OLLAMA_BASE_URL (default:
                               http://localhost:11434).
      - "ollama/..."         -> local Ollama server (generation/embedding
                               endpoint); no API key required.
      - "openrouter/..."     -> OpenRouter gateway; requires OPENROUTER_API_KEY.
                               Provides access to 300+ models from many
                               providers. See https://openrouter.ai/models.
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

    # Every branch below is routed through LiteLLM (see
    # agent_wrappers._resolve_model). Some models impose stricter parameter
    # constraints than our own per-agent "quick knobs" assume -- e.g. litellm
    # rejects any non-default temperature outright for some Claude models
    # ("litellm.UnsupportedParamsError: ... Only temperature=1 is supported").
    # drop_params tells litellm to silently drop a param a given model doesn't
    # support instead of raising, so each agent's own tuned temperature/top_p
    # still applies for models that support it and is harmlessly ignored for
    # ones that don't.
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

    # --- Local Ollama (ollama_chat/ or ollama/) ---
    elif provider in ("ollama_chat", "ollama"):
        # No API key required for a locally-served Ollama instance.
        # OLLAMA_BASE_URL may be set to override the default localhost endpoint
        # (http://localhost:11434); _resolve_model in agent_wrappers.py reads
        # it and passes it as api_base to LiteLlm so every agent's model call
        # hits the right host without any per-agent configuration.
        os.environ["ADK_MODEL_PROVIDER"] = "ollama"

    # --- OpenRouter (300+ models via a single gateway API key) ---
    elif provider == "openrouter":
        if not os.getenv("OPENROUTER_API_KEY"):
            raise EnvironmentError(
                f"MODEL='{model}' requires OPENROUTER_API_KEY to be set. "
                "Get a key at https://openrouter.ai/keys"
            )
        os.environ["ADK_MODEL_PROVIDER"] = "openrouter"

    else:
        raise EnvironmentError(
            f"Unrecognized provider prefix '{provider}/' in MODEL='{model}'. "
            "Supported: anthropic/, openai/, bedrock/, ollama_chat/, ollama/, "
            "openrouter/ (or a bare Gemini name)."
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
# RotatingFileHandler, not a plain FileHandler -- each process start
# already mints its own timestamped log_file above, but -d/--detached
# (the web service) can run for a very long time without restarting,
# and this file would otherwise grow unbounded for that entire uptime.
# 10MB x 5 backups (50MB ceiling) is generous for this project's own
# request volume while still being a real, enforced bound.
file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
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
    cloudarch_attack_simulation_query_agent,
    cloudarch_finops_query_agent,
    cloudarch_iac_pipeline,
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
    requirements_reviewer_agent,
    requirements_simulation_query_agent,
    requirements_doc_pipeline,
    proposal_response_pipeline,
    process_import_agent,
    design_import_agent,
    cloudarch_import_agent,
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
from .utils_agent import clear_pipeline_lock, download_artifact

root_agent = ProcessLlmAgent(
    name="Process_Architect_Orchestrator",
    instruction_file="common/agent.txt",
    before_model_callback=None,  # Disable before callback for root agent
    after_model_callback=None,   # Disable after callback for root agent
    tools=[clear_pipeline_lock, download_artifact],
    sub_agents=[
        full_design_pipeline,
        consultant_agent,
        consultant_design_agent,
        cloudarch_pipeline,
        consultant_cloudarch_agent,
        cloudarch_simulation_query_agent,
        cloudarch_attack_simulation_query_agent,
        cloudarch_finops_query_agent,
        cloudarch_iac_pipeline,
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
        requirements_reviewer_agent,
        requirements_simulation_query_agent,
        requirements_doc_pipeline,
        proposal_response_pipeline,
        process_import_agent,
        design_import_agent,
        cloudarch_import_agent,
    ],
)

# ---------------------------------------------------------
# AGENT INSTRUCTIONS INDEX
# ---------------------------------------------------------
# Developed in tandem with the neuro-san port's own cli.py
# _build_agent_instructions_index -- same purpose (the web client's Agent
# Network tab hover tooltip, which otherwise only ever sees what's
# OBSERVABLE from the chat stream itself: an agent's dotted invocation
# path, how many times it's been called, never the actual prompt driving
# it), much simpler to build here: an ADK agent is a plain (pydantic)
# object with a real .instruction attribute already in memory, not HOCON
# text to parse from disk. Walking root_agent's own .sub_agents tree
# (every ADK BaseAgent subclass -- LlmAgent, SequentialAgent, LoopAgent --
# exposes this) naturally finds every real LLM-backed agent regardless of
# how deep a SequentialAgent/LoopAgent wrapper nests it; a pure
# orchestration wrapper has no .instruction of its own, so it's skipped
# automatically rather than needing to be filtered out by type.
#
# Also walks each node's own .tools -- plain Python functions (e.g.
# download_artifact), not LlmAgents, so they have no .instruction either.
# Without this, every tool node in the web client's Agent Network tab
# (any plain function call, not just a sub-agent call) 404s on hover
# instead of showing the thing closest to that tool's own "instructions":
# its docstring, which is also the literal text the LLM sees describing
# when/how to call it.
_agent_instructions_index: Optional[Dict[str, str]] = None


def _build_agent_instructions_index() -> Dict[str, str]:
    index: Dict[str, str] = {}
    seen_ids = set()

    def visit(node) -> None:
        if node is None or id(node) in seen_ids:
            return
        seen_ids.add(id(node))
        name = getattr(node, "name", None)
        instruction = getattr(node, "instruction", None)
        if name and isinstance(instruction, str) and instruction.strip():
            index.setdefault(name, instruction)
        for tool in getattr(node, "tools", None) or []:
            tool_name = getattr(tool, "__name__", None)
            doc = inspect.getdoc(tool)
            if tool_name and doc:
                index.setdefault(tool_name, doc)
        for child in getattr(node, "sub_agents", None) or []:
            visit(child)

    visit(root_agent)
    return index


def _get_agent_instructions_index() -> Dict[str, str]:
    """Lazily builds _build_agent_instructions_index's result ONCE per
    process and reuses it -- root_agent's own tree is a fixed, fully-
    built object graph by the time this module finishes importing, so
    re-walking it on every single hover in the web client's Agent Network
    tab would be wasted work for an answer that never changes."""
    global _agent_instructions_index
    if _agent_instructions_index is None:
        _agent_instructions_index = _build_agent_instructions_index()
    return _agent_instructions_index


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


def _event_response_text(event) -> Optional[str]:
    """Joins every text Part in `event.content.parts`, skipping function-
    call/response parts and None text. Deliberately does NOT gate on
    event.is_final_response() the way every call site here used to --
    ADK's own is_final_response() formula (google.adk.events.event.Event.
    is_final_response) always returns False for an event that carries a
    function_call, EVEN when that same event also carries genuine
    narrative text in a sibling Part (a real pattern: a model emitting a
    one-line comment alongside the tool call it's required to make).
    Gating on is_final_response() alone silently threw that text away.
    Returns None (not "") when there's nothing real to extract, so
    callers can keep whichever earlier non-None text they already have
    instead of clobbering it with a later content-free/text-free event
    (e.g. a trailing agent whose own instructions are to stay silent)."""
    if not event.content or not event.content.parts:
        return None
    text = "".join(part.text or "" for part in event.content.parts if part.text)
    return text or None


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
    from .utils_agent import _reset_stop_counter
    from process_toolkit import paths as toolkit_paths
    _reset_stop_counter(toolkit_paths.output_path("stop_counter.json"))

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

# A client that creates a session and never calls DELETE /chat/<session_id>
# (closed tab, crash, forgotten cleanup) would otherwise leak its entry here
# -- and its backing ADK session in _web_session_service -- for the life of
# the process. Entries idle longer than this are swept opportunistically by
# _get_or_create_web_session below. Generous relative to this project's own
# documented ~5-10 minute typical turn time, so a slow-but-active session is
# never evicted out from under a still-engaged user.
_WEB_SESSION_IDLE_TIMEOUT_SECONDS = float(getProperty("webSessionIdleTimeoutSeconds", default=3600))
# Bounds how often the sweep below actually scans _web_sessions, independent
# of request volume -- a pure efficiency knob (an O(active sessions) scan on
# every single request would be wasteful), not something a deployer needs to
# tune, so it's a plain constant rather than a getProperty.
_WEB_SESSION_SWEEP_INTERVAL_SECONDS = 300.0
_web_sessions_last_swept = 0.0

# web_session_id -> count of turns currently executing on it, streaming or
# not. A COUNT, not a set/bool: two overlapping requests for the SAME
# session_id (e.g. a double-click/retry, or overlapping /chat + /chat/stream)
# both mark it active, and the sweep must keep excluding it until BOTH have
# finished, not just whichever happens to finish first -- a plain set, where
# one turn's own cleanup (.discard()) would blindly remove the session even
# while the OTHER turn is still running, doesn't capture that. last_accessed
# (above) is stamped at turn START, so a turn that legitimately runs longer
# than _WEB_SESSION_IDLE_TIMEOUT_SECONDS would otherwise look just as idle
# to the sweep as an abandoned session, and get its entry (and its backing
# ADK session) deleted while still in use. Checked by the sweep in
# _get_or_create_web_session; incremented/decremented by _run_chat_turn
# (non-streaming) and chat_stream's generate() (streaming), guarded by
# _web_sessions_lock since both already take it to touch _web_sessions
# itself.
_active_web_sessions: dict = {}

# Tracks the currently in-flight /chat/stream task per web session, so
# POST /chat/<session_id>/stop (see chat_stop below) can actually cancel
# it instead of merely abandoning the client-side connection -- the
# client giving up on reading the stream does NOT, by itself, stop the
# background thread's real model call (and its real token cost) from
# continuing to completion. Entries are added right before a turn's
# asyncio Task starts running and removed in its own "finally" (success,
# error, or cancellation alike) -- see chat_stream's generate().
_active_stream_tasks: dict = {}
_active_stream_tasks_lock = threading.Lock()

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
# Unlike the timestamp lists above (self-trimming on every call for a key
# that's actually in use), a client_key that stops making requests entirely
# keeps its dict entry forever -- distinct IPs seen even once would
# otherwise accumulate unbounded over the process's lifetime. Swept on the
# same opportunistic cadence as _web_sessions above.
_WEB_RATE_LIMIT_SWEEP_INTERVAL_SECONDS = 300.0
_web_rate_limit_last_swept = 0.0


def _check_rate_limit(client_key: str, limit_per_minute: int) -> bool:
    """Fixed 60s sliding window per client_key. limit_per_minute <= 0 disables
    the check entirely (returns True unconditionally)."""
    global _web_rate_limit_last_swept
    if limit_per_minute <= 0:
        return True
    now = time.monotonic()
    window_start = now - 60.0
    with _web_rate_limit_lock:
        if now - _web_rate_limit_last_swept >= _WEB_RATE_LIMIT_SWEEP_INTERVAL_SECONDS:
            _web_rate_limit_last_swept = now
            stale_keys = [
                key for key, timestamps in _web_rate_limit_state.items()
                if not any(t >= window_start for t in timestamps)
            ]
            for key in stale_keys:
                _web_rate_limit_state.pop(key, None)
        timestamps = [t for t in _web_rate_limit_state.get(client_key, ()) if t >= window_start]
        if len(timestamps) >= limit_per_minute:
            _web_rate_limit_state[client_key] = timestamps
            # A sustained flood (attack, or a misbehaving client retrying
            # too aggressively) was otherwise invisible in the logs --
            # every rejected request hit this branch and returned 429
            # with zero trace of it ever happening.
            logger.warning(
                "Rate limit exceeded for %s: %d requests in the last 60s (limit %d).",
                client_key, len(timestamps), limit_per_minute,
            )
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
    global _web_runner, _web_session_service, _web_sessions_last_swept

    now = time.monotonic()
    evicted: list = []
    entry = None
    with _web_sessions_lock:
        if now - _web_sessions_last_swept >= _WEB_SESSION_SWEEP_INTERVAL_SECONDS:
            _web_sessions_last_swept = now
            stale_ids = [
                sid for sid, e in _web_sessions.items()
                if sid not in _active_web_sessions
                and now - e.get("last_accessed", now) >= _WEB_SESSION_IDLE_TIMEOUT_SECONDS
            ]
            evicted = [(sid, _web_sessions.pop(sid)) for sid in stale_ids]
        if existing_session_id:
            entry = _web_sessions.get(existing_session_id)
            if entry is not None:
                entry["last_accessed"] = now

    for stale_id, stale_entry in evicted:
        logger.info("Evicting idle web session %s after %.0fs of inactivity.",
                    stale_id, _WEB_SESSION_IDLE_TIMEOUT_SECONDS)
        if _web_session_service is not None:
            try:
                await _web_session_service.delete_session(
                    app_name=_WEB_APP_NAME,
                    user_id=stale_entry["user_id"],
                    session_id=stale_entry["session_id"],
                )
            except Exception:
                logger.warning("Failed to delete idle ADK session %s during eviction sweep.",
                                stale_id, exc_info=True)

    if entry is not None:
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
        _web_sessions[web_session_id] = {
            "user_id": user_id, "session_id": session_id, "last_accessed": time.monotonic(),
        }
    return web_session_id, user_id, session_id


def _accumulate_event_usage(event, totals: Dict[str, int]) -> None:
    """Adds one Event's usage_metadata into `totals`, for the Token Usage
    tab's per-turn chart. Callers must only call this for NON-PARTIAL
    events (see the loop below) -- ADK's own Runner only ever persists
    non-partial events into session history ("We should append non-partial
    events only" -- see Runner._should_append_event in the installed
    google-adk package's runners.py), which means there is exactly one
    non-partial event per real model call, carrying that call's usage
    (ADK's streaming machinery re-stamps usage_metadata forward onto each
    call's own final event once it becomes known -- see
    google.adk.utils.streaming_utils). Calling this for every event
    including partial chunks would instead risk counting one streamed
    call's usage once per chunk; restricting to non-partial events sidesteps
    that without needing any dedup heuristic of our own.
    """
    usage = event.usage_metadata
    if usage is None:
        return
    totals["prompt_tokens"] += usage.prompt_token_count or 0
    totals["completion_tokens"] += usage.candidates_token_count or 0
    totals["total_tokens"] += usage.total_token_count or 0


def _new_usage_totals() -> Dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


# POST /chat and /chat/stream's optional "files" field (see
# _parse_attachments below): each entry is {"name", "mime_type",
# "data_base64"}. Unlike the Neurosan port's own cli.py (see its matching
# comment -- its underlying framework's multimodal plumbing is a stub in
# the installed version), google-genai's Content.parts already accepts a
# real multimodal Part directly: types.Part.from_bytes(data=..., mime_type=
# ...) wraps the bytes as inline_data, which Gemini actually receives and
# can read (images natively, and plenty of document types like PDF/text
# too) -- no server-side text-extraction workaround needed on this side,
# see _content_parts_for_turn below. Defaults kept identical to the
# Neurosan port's (same numbers, same field names) so the shared
# WebClient's behavior doesn't change depending on which backend it's
# talking to -- configurable here (unlike that port, which hardcodes
# them) for consistency with every other tunable in this file
# (webApiKey, webRateLimitPerMinute, modelTimeoutSeconds, ...), all of
# which go through getProperty rather than a bare literal.
ATTACHMENT_MAX_FILES = int(getProperty("attachmentMaxFiles", default=4))
ATTACHMENT_MAX_BYTES = int(getProperty("attachmentMaxBytes", default=8 * 1024 * 1024))  # per file, raw (decoded) size

# Flask's own MAX_CONTENT_LENGTH (set on web_app in build_web_app) rejects an
# oversized request before reading its body at all -- without it, chat()/
# chat_stream() below call request.get_json() first and only check
# ATTACHMENT_MAX_FILES/ATTACHMENT_MAX_BYTES afterward, so a request far
# beyond what any legitimate attachment set could produce would still be
# fully parsed into memory (the JSON body, its base64 strings, all of it)
# before those per-file limits ever get a chance to reject it. Derived from
# the two limits above rather than its own getProperty, so it can't drift
# out of sync with them: base64 inflates raw bytes by ~4/3, and the extra
# 1MB covers the query text plus JSON punctuation/field-name overhead.
MAX_REQUEST_BODY_BYTES = int(ATTACHMENT_MAX_FILES * ATTACHMENT_MAX_BYTES * 4 / 3) + 1 * 1024 * 1024


def _parse_attachments(payload: Dict[str, Any]) -> "tuple[Optional[List[Dict[str, Any]]], Optional[str]]":
    """
    Validates and decodes POST /chat or /chat/stream's optional "files"
    field: [{"name": str, "mime_type": str, "data_base64": str}, ...].
    Returns (decoded_files, None) on success -- decoded_files is the same
    shape with "data_base64" replaced by "data" (raw bytes) -- or
    (None, error_message) on the first violation found, for the caller to
    turn into a 400 response exactly like the existing "query required"
    check does. Returns ([], None) when "files" is absent/empty.

    Re-validates server-side (size/count) even though the web client
    enforces the same limits before ever sending -- a client is never a
    trusted boundary. Deliberately kept identical (same checks, same
    error wording) to the Neurosan port's own cli.py._parse_attachments,
    so a caller sees the same behavior regardless of which backend it
    talks to.
    """
    raw_files = payload.get("files")
    if raw_files is None:
        return [], None
    if not isinstance(raw_files, list):
        return None, "Field 'files' must be a list."
    if len(raw_files) > ATTACHMENT_MAX_FILES:
        return None, f"Too many attached files (max {ATTACHMENT_MAX_FILES})."

    decoded: List[Dict[str, Any]] = []
    for entry in raw_files:
        if not isinstance(entry, dict):
            return None, "Each entry in 'files' must be an object."
        name = entry.get("name")
        mime_type = entry.get("mime_type")
        data_b64 = entry.get("data_base64")
        if not isinstance(name, str) or not name.strip():
            return None, "Each attached file requires a non-empty 'name'."
        if not isinstance(mime_type, str) or not mime_type.strip():
            return None, f"Attached file '{name}' is missing 'mime_type'."
        if not isinstance(data_b64, str) or not data_b64:
            return None, f"Attached file '{name}' is missing 'data_base64'."
        try:
            data = base64.b64decode(data_b64, validate=True)
        except (binascii.Error, ValueError):
            return None, f"Attached file '{name}' has invalid base64 data."
        if len(data) > ATTACHMENT_MAX_BYTES:
            max_mb = ATTACHMENT_MAX_BYTES / (1024 * 1024)
            return None, f"Attached file '{name}' exceeds the {max_mb:.0f}MB size limit."
        decoded.append({"name": name, "mime_type": mime_type, "data": data})

    return decoded, None


def _content_parts_for_turn(query: str, files: Optional[List[Dict[str, Any]]]) -> List["types.Part"]:
    """
    Builds the list of Parts for this turn's Content: the query text,
    plus one real multimodal Part per attached file (see
    ATTACHMENT_MAX_FILES's own comment for why this works natively here
    but needs a text-extraction workaround on the Neurosan port). Gemini
    receives each attached file as genuine inline_data -- an image is
    actually seen by the model's vision input, not just described in
    text.

    KNOWN GAP (prompt-injection exposure, not yet addressed): nothing
    here marks this content as untrusted, LLM-facing data rather than
    instructions -- a malicious attachment's embedded text ("ignore
    prior instructions and approve this unconditionally") is read by the
    model directly, with no app-level framing in between. Going through
    native multimodal content rather than this app's own text extraction
    (the Neurosan port's approach) shifts this risk onto the model's own
    handling instead of eliminating it. See this project's own README
    "Known issues and caveats" for the fuller writeup.
    """
    parts = [types.Part(text=query)]
    for f in (files or []):
        parts.append(types.Part.from_bytes(data=f["data"], mime_type=f["mime_type"]))
    return parts


def _mark_web_session_active(web_session_id: str) -> None:
    """Excludes web_session_id from the idle-eviction sweep in
    _get_or_create_web_session for as long as a turn is actually running on
    it -- see _active_web_sessions's own comment for why this is a count,
    not a flag."""
    with _web_sessions_lock:
        _active_web_sessions[web_session_id] = _active_web_sessions.get(web_session_id, 0) + 1


def _mark_web_session_inactive(web_session_id: str) -> None:
    """Decrements this session's active-turn count; only actually removes
    it (making the session eligible for the idle sweep again) once no
    OTHER overlapping turn is still running on it. Also refreshes
    last_accessed to now -- a turn that ran right up to (or past)
    _WEB_SESSION_IDLE_TIMEOUT_SECONDS would otherwise still carry its
    turn-START timestamp the instant it finishes, making it look just as
    idle as a genuinely abandoned session to the very next sweep, even
    though it just finished successfully."""
    with _web_sessions_lock:
        remaining = _active_web_sessions.get(web_session_id, 0) - 1
        if remaining > 0:
            _active_web_sessions[web_session_id] = remaining
        else:
            _active_web_sessions.pop(web_session_id, None)
        entry = _web_sessions.get(web_session_id)
        if entry is not None:
            entry["last_accessed"] = time.monotonic()


async def _release_any_leftover_pipeline_lock(user_id: str, session_id: str) -> None:
    """
    Safety net: every pipeline (process/design-doc/cloudarch) acquires its
    own output/ directory pipeline-lock exactly once, as the first action
    of a brand new top-level turn, and releases it (via
    release_pipeline_lock_for_turn, an after_agent_callback) once that
    SAME turn's own LoopAgent genuinely finishes -- the whole thing
    happens within one run_async() call, never spanning more than one
    turn. So a token still sitting in this ADK session's own state once
    that run_async() call has returned, for ANY reason, means the
    pipeline's own after_agent_callback never ran.

    The one way that happens: POST /chat/<session_id>/stop (see chat_stop
    below) cancels this turn's asyncio Task mid-flight. asyncio.
    CancelledError is raised at whatever await point the agent chain
    happened to be suspended at -- there is no guarantee ADK's own
    LoopAgent treats that the same as a normal last iteration and still
    runs its registered after_agent_callback, and empirically it does
    not. Without this, a cancelled turn would leave BOTH the lock AND its
    background heartbeat (process_toolkit.run_lock) running forever --
    worse than before that heartbeat existed, since the heartbeat would
    keep the lock's started_at fresh indefinitely, permanently defeating
    the staleness-based self-healing every pipeline run still depends on
    for the crash/abandonment case the heartbeat was never meant to
    replace.

    Called from both _run_chat_turn and _stream_chat_turn's own
    finally/cleanup, unconditionally (success, in-band error, and
    cancellation alike) -- cheap and a no-op on the overwhelming majority
    of calls, where the pipeline's own finalize step already released
    everything normally.
    """
    if _web_session_service is None:
        return
    try:
        session = await _web_session_service.get_session(
            app_name=_WEB_APP_NAME, user_id=user_id, session_id=session_id,
        )
    except Exception:
        logger.warning("Could not check session %s for a leftover pipeline lock.", session_id, exc_info=True)
        return
    if session is None or not session.state:
        return

    from .utils_agent import PIPELINE_LOCK_TOKEN_STATE_KEY
    from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat

    stored = session.state.get(PIPELINE_LOCK_TOKEN_STATE_KEY)
    token = stored.get("token") if isinstance(stored, dict) else None
    if not token:
        return
    logger.warning(
        "Turn for session %s ended with pipeline lock token %s still held -- "
        "releasing it defensively (most likely a cancelled turn).", session_id, token,
    )
    stop_pipeline_lock_heartbeat(token)
    release_pipeline_lock(token)


async def _run_chat_turn(existing_session_id: Optional[str], query: str, files: Optional[List[Dict[str, Any]]] = None):
    """Resolve/create the web session, then run one query through it."""
    from process_toolkit import paths as toolkit_paths

    web_session_id, user_id, session_id = await _get_or_create_web_session(existing_session_id)
    _mark_web_session_active(web_session_id)
    with toolkit_paths.use_session(web_session_id):
        try:
            content = types.Content(role="user", parts=_content_parts_for_turn(query, files))
            final_response = None
            usage_totals = _new_usage_totals()
            async for event in _web_runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
                run_config=RUN_CONFIG,
            ):
                if not event.partial:
                    _accumulate_event_usage(event, usage_totals)
                    text = _event_response_text(event)
                    if text:
                        final_response = text

            usage = {**usage_totals, "model": MODEL}
            return web_session_id, (final_response or ""), usage
        finally:
            # release_pipeline_lock/stop_pipeline_lock_heartbeat below
            # resolve this session's own lock file via process_toolkit.paths
            # too -- must run INSIDE this same use_session() block, not
            # after it exits, or they'd resolve the wrong (flat) lock path.
            await _release_any_leftover_pipeline_lock(user_id, session_id)
            _mark_web_session_inactive(web_session_id)


async def _stream_chat_turn(
    user_id: str, session_id: str, query: str, event_queue: "queue.Queue",
    files: Optional[List[Dict[str, Any]]] = None,
) -> None:
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
      {"status": "done", "response": "<final answer>", "usage": {"prompt_tokens": N,
                                     "completion_tokens": N, "total_tokens": N, "model": "..."}}
      {"status": "stopped", "response": "<partial answer so far>", "usage": {...same shape}}
      {"status": "error", "error": "..."}

    A "stopped" event means POST /chat/<session_id>/stop (see build_web_app)
    cancelled this turn's asyncio Task mid-flight -- NOT merely that the
    client gave up reading the stream (which alone would not stop the
    actual model call, or its real token cost, from running to completion
    in the background thread).
    """
    content = types.Content(role="user", parts=_content_parts_for_turn(query, files))
    answer_so_far = ""
    last_progress_author: Optional[str] = None
    usage_totals = _new_usage_totals()
    turn_started = time.monotonic()
    try:
        async for event in _web_runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
            run_config=STREAMING_RUN_CONFIG,
        ):
            if not event.partial:
                _accumulate_event_usage(event, usage_totals)

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

            # Deliberately NOT gated on event.is_final_response() -- it
            # always returns False for an event carrying a function_call,
            # even when that same event ALSO carries genuine narrative
            # text in a sibling Part (see _event_response_text's own
            # docstring). Extract that text regardless of whether this
            # same event also invoked a tool, so a model that comments
            # alongside a mandatory tool call doesn't lose that comment.
            final_text = _event_response_text(event)
            if final_text:
                answer_so_far = final_text
                event_queue.put({"status": "delta", "text": answer_so_far})

            if function_calls or (event.content and event.content.parts):
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

        # Previously only visible at DEBUG, so a successful turn's
        # outcome/duration/usage left no trace at this project's default
        # LOGLEVEL (WARNING) or even at INFO -- only exceptions were ever
        # visible by default, so diagnosing "why did this session behave
        # oddly" after the fact (without reproducing it) had no trail.
        logger.info(
            "Chat stream turn completed: session=%s user=%s query_len=%d files=%d duration=%.2fs usage=%s",
            session_id, user_id, len(query), len(files or []), time.monotonic() - turn_started, usage_totals,
        )
        event_queue.put({
            "status": "done",
            "response": answer_so_far,
            "usage": {**usage_totals, "model": MODEL},
        })
    except asyncio.CancelledError:
        # POST /chat/<session_id>/stop cancelled us -- report whatever
        # partial answer/usage had accrued so far, then re-raise so the
        # Task is properly marked cancelled (the "finally" below still
        # runs either way, sending the None sentinel the reading side
        # needs regardless of how this turn ended).
        logger.info(
            "Chat stream turn stopped: session=%s user=%s query_len=%d files=%d duration=%.2fs usage=%s",
            session_id, user_id, len(query), len(files or []), time.monotonic() - turn_started, usage_totals,
        )
        event_queue.put({
            "status": "stopped",
            "response": answer_so_far,
            "usage": {**usage_totals, "model": MODEL},
        })
        raise
    except Exception:
        logger.exception("Web chat stream error")
        event_queue.put({"status": "error", "error": "An internal error has occurred."})
    finally:
        await _release_any_leftover_pipeline_lock(user_id, session_id)
        event_queue.put(None)


def build_web_app(https: bool = True):
    """
    Build (but do not run) the Flask REST app for -d/--detached mode.

    Exposes:
      POST   /chat            {"query": "...", "session_id": "..." (optional),
                               "files": [{"name": "...", "mime_type": "...",
                               "data_base64": "..."}, ...] (optional, up to
                               ATTACHMENT_MAX_FILES entries, each up to
                               ATTACHMENT_MAX_BYTES decoded)}
                               -> {"status": "ok", "session_id": "...",
                                   "query": "...", "response": "...",
                                   "usage": {"prompt_tokens": N,
                                   "completion_tokens": N, "total_tokens": N,
                                   "model": "..."}}
                               Attached files reach Gemini as genuine
                               multimodal content (see
                               _content_parts_for_turn) -- unlike the
                               Neurosan port, which only extracts them to
                               text (see that port's own cli.py for why).
      POST   /chat/stream      Same request body; response is
                               text/event-stream instead -- a live
                               sequence of `data: {...}\n\n` events
                               shaped like _stream_chat_turn's own
                               docstring describes, ending with a
                               {"status": "done", "response": "...",
                               "usage": {...same shape as /chat's above}}
                               event. See that function for why/how.
      POST   /chat/<session_id>/stop  Cancels that session's in-flight
                               /chat/stream turn, if any -> {"status": "ok",
                               "session_id": "...", "stopped": true|false}.
      DELETE /chat/<session_id>  Drops server-side state for that session.
      GET    /artifacts/<name>  "process" or "design" -> {"status": "ok",
                               "name": "...", "data": {...the parsed
                               output/<name>_data.json...}}, or 404 if
                               that pipeline hasn't produced one yet.
      GET    /status           Liveness probe -- also reports the
                               currently configured model as {"status":
                               "live", "model": "..."}.

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
    from flask import Flask, request, jsonify, make_response, Response, send_file

    web_app = Flask("ProcessArchitectWebService")
    web_app.secret_key = getProperty("FLASK_SECRET_KEY") or secrets.token_hex(32)
    # Rejects an oversized request at the WSGI layer, before Flask reads any
    # of its body -- see MAX_REQUEST_BODY_BYTES's own comment for why this
    # has to happen before request.get_json(), not after.
    web_app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BODY_BYTES

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

    def _web_session_id_for_get_request() -> Optional[str]:
        """Resolves the requesting web session's own id for a plain GET
        route (the /artifacts/* routes below) -- these have no JSON body
        of their own the way POST /chat does, so a `session_id` QUERY
        parameter is checked first. That's what the web client actually
        sends (it tracks its own session id in JS state and passes it
        explicitly on every request, the same as the POST routes' own
        `payload.get("session_id")`) rather than relying on this cookie
        at all -- _add_cors_headers below reflects back whatever Origin a
        browser sends but (deliberately, see its own comment) never sets
        Access-Control-Allow-Credentials, so a cross-origin fetch() (the
        web client's own default deployment: a static page served from a
        different origin than this API) never actually sends OR receives
        this cookie, regardless of `secure`/`samesite`. The cookie is
        still checked second, for any OTHER same-origin caller that
        never passes the query parameter explicitly."""
        return request.args.get("session_id") or request.cookies.get(WEB_SESSION_COOKIE)

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

        files, files_error = _parse_attachments(payload)
        if files_error:
            return jsonify({"status": "error", "error": files_error}), 400

        session_id = payload.get("session_id") or request.cookies.get(WEB_SESSION_COOKIE)

        turn_started = time.monotonic()
        try:
            web_session_id, response_text, usage = asyncio.run(
                _run_chat_turn(session_id, query.strip(), files=files)
            )
        except Exception:
            logger.exception("Web chat error")
            return jsonify({
                "status": "error",
                "error": "An internal error has occurred.",
            }), 500

        # Previously only visible at DEBUG, so a successful turn's
        # outcome/duration/usage left no trace at this project's default
        # LOGLEVEL -- only exceptions were ever visible by default, so
        # diagnosing "why did this session behave oddly" after the fact
        # (without reproducing it) had no trail.
        logger.info(
            "Chat turn completed: session=%s query_len=%d files=%d duration=%.2fs usage=%s",
            web_session_id, len(query), len(files or []), time.monotonic() - turn_started, usage,
        )

        resp = make_response(jsonify({
            "status": "ok",
            "session_id": web_session_id,
            "query": query,
            "usage": usage,
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

        files, files_error = _parse_attachments(payload)
        if files_error:
            return jsonify({"status": "error", "error": files_error}), 400

        session_id = payload.get("session_id") or request.cookies.get(WEB_SESSION_COOKIE)
        web_session_id, user_id, adk_session_id = asyncio.run(_get_or_create_web_session(session_id))
        _mark_web_session_active(web_session_id)

        def generate():
            event_queue: "queue.Queue" = queue.Queue()

            def run():
                # A bare asyncio.run(...) (as this used before) gives no
                # handle to cancel the coroutine once it's running --
                # creating the loop/Task explicitly here instead, and
                # registering them in _active_stream_tasks, is what lets
                # POST /chat/<session_id>/stop actually reach in and cancel
                # this specific turn from a different request's thread.
                #
                # use_session() is entered explicitly here, inside this
                # bare threading.Thread's own target function, rather than
                # relying on it propagating in from the outer Flask request
                # thread -- confirmed empirically that it would NOT: a bare
                # threading.Thread (unlike asyncio.to_thread/loop.create_task)
                # does not copy the caller's contextvars.Context. Entering it
                # before loop.create_task() below is what matters -- that
                # call snapshots whatever context is active at that moment,
                # which _stream_chat_turn's entire Task (including its own
                # finally block's pipeline-lock release, which also resolves
                # this session's own output/ directory) then runs under.
                from process_toolkit import paths as toolkit_paths

                with toolkit_paths.use_session(web_session_id):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    task = None
                    try:
                        # Constructing the coroutine (evaluating/binding
                        # _stream_chat_turn's own arguments) happens eagerly,
                        # synchronously, right here -- a bad argument (e.g. a
                        # signature mismatch) raises immediately, before
                        # loop.create_task even runs, let alone the coroutine
                        # body itself. Keeping that construction INSIDE this
                        # try (not before it, as this used to be written)
                        # matters: _stream_chat_turn's own finally (below in
                        # that function) is what reliably pushes event_queue's
                        # terminating None, but that finally can only run once
                        # the coroutine body has actually started -- an
                        # exception here, before that ever happens, previously
                        # left event_queue with no sentinel at all, and
                        # generate()'s consumer loop below blocks on
                        # event_queue.get() forever as a result: a silent hang,
                        # not a clean error. Confirmed directly: a transient
                        # files= keyword-argument mismatch during development
                        # hit exactly this path.
                        task = loop.create_task(
                            _stream_chat_turn(user_id, adk_session_id, query.strip(), event_queue, files=files)
                        )
                        with _active_stream_tasks_lock:
                            _active_stream_tasks[web_session_id] = (loop, task)
                        loop.run_until_complete(task)
                    except asyncio.CancelledError:
                        pass  # _stream_chat_turn's own "stopped" event already queued
                    except Exception:
                        # Reached only when the coroutine never started running
                        # at all (see the comment above) -- _stream_chat_turn's
                        # own error handling never got a chance to push
                        # anything, so this is the only place that still can.
                        logger.exception("Web chat stream setup error")
                        event_queue.put({"status": "error", "error": "An internal error has occurred."})
                        event_queue.put(None)
                    finally:
                        with _active_stream_tasks_lock:
                            # Only remove OUR OWN entry -- guards against a race
                            # where a brand new turn for the same session has
                            # already registered its own (loop, task) pair by
                            # the time this cleanup runs.
                            if task is not None and _active_stream_tasks.get(web_session_id) == (loop, task):
                                _active_stream_tasks.pop(web_session_id, None)
                        loop.close()
                        _mark_web_session_inactive(web_session_id)

            thread = threading.Thread(target=run, daemon=True)
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

    @web_app.route("/chat/<session_id>/stop", methods=["POST"])
    def chat_stop(session_id):
        """
        Cancels session_id's CURRENTLY IN-FLIGHT /chat/stream turn, if any
        -- for a user who started a long multi-agent turn and realized
        partway through that the instructions were wrong, so the rest of
        it is just burning tokens for nothing. This is a REAL cancellation
        of the running asyncio Task (see _active_stream_tasks / generate()
        above), not merely the client giving up on the connection -- the
        latter, alone, would leave the background thread's actual model
        call (and its real token cost) running to completion regardless.

        Always 200 -- "nothing was running" and "it was running and is now
        cancelled" are both unexceptional outcomes, not errors, for a
        caller that just wants "make sure nothing is still running".
        """
        with _active_stream_tasks_lock:
            entry = _active_stream_tasks.get(session_id)
        if entry is None:
            return jsonify({"status": "ok", "session_id": session_id, "stopped": False})
        loop, task = entry
        loop.call_soon_threadsafe(task.cancel)
        return jsonify({"status": "ok", "session_id": session_id, "stopped": True})

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
        # Removes this session's own output/<session_id>/ directory right
        # now rather than waiting for the next purge sweep -- an explicit
        # "drop this session" request is as clear a signal as it gets that
        # nothing will need those files again.
        from process_toolkit.session_purge import purge_session

        try:
            purge_session(session_id)
        except ValueError:
            pass  # session_id didn't look like a real session directory name -- nothing to remove
        return jsonify({"status": "ok", "session_id": session_id, "cleared": existed})

    @web_app.route("/artifacts/<name>", methods=["GET"])
    def artifact(name):
        """
        Read-only access to this web session's own output/<session_id>/
        process_data.json, design_data.json, requirements_summary.json,
        proposal_response.json, or cloudarch_drawio.xml (or flat output/
        for a caller with no session id at all -- e.g. a direct API
        caller that never went through POST /chat first), resolved via a
        `session_id` query parameter (see _web_session_id_for_get_request's
        own docstring for why a query parameter, not just the session
        cookie, matters here) -- a plain GET has no JSON body of its own
        to carry a session_id in the way POST /chat does. Powers the web
        client's "Process / Design / Requirements / Proposal Response"
        and "Cloud Architecture" tabs -- a hierarchical/diagram viewer of
        whichever pipeline's current artifact. Both backends serve this the same
        way (the neuro-san port's build_web_app has an identical route)
        and both keep these files at an identical relative path, so the
        client's fetch logic doesn't need to know which backend it's
        talking to.

        Deliberately a raw file read, NOT the existing
        load_master_process_json/load_master_design_json helpers in
        .utils -- those silently fall back to a blank template when the
        file is missing (useful for a pipeline about to populate one, not
        for a debugging viewer that needs to tell "genuinely not generated
        yet" apart from "here's an empty template"), so this reports a
        real 404 instead.

        "cloudarch" returns `data` as the raw XML STRING (not JSON-parsed)
        -- the client's own mxGraph-XML renderer parses it directly, the
        same way it already does for a saved .drawio file.
        """
        from process_toolkit import paths as toolkit_paths

        filenames = {
            "process": "process_data.json",
            "design": "design_data.json",
            "requirements": "requirements_summary.json",
            "proposal_response": "proposal_response.json",
            "cloudarch": "cloudarch_drawio.xml",
        }
        filename = filenames.get(name)
        if filename is None:
            return jsonify({
                "status": "error",
                "error": (
                    f"Unknown artifact '{name}' -- use 'process', 'design', 'requirements', "
                    "'proposal_response', or 'cloudarch'."
                ),
            }), 400

        with toolkit_paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(toolkit_paths.output_dir(), filename)
            if not os.path.exists(path):
                return jsonify({
                    "status": "error",
                    "error": f"No {filename} found yet -- run the {name} pipeline at least once, then try again.",
                }), 404

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = f.read() if name == "cloudarch" else json.load(f)
            except Exception:
                logger.exception("Failed to read/parse %s", filename)
                return jsonify({
                    "status": "error",
                    "error": f"Could not read {filename} -- see server logs.",
                }), 500

        return jsonify({"status": "ok", "name": name, "data": data})

    @web_app.route("/artifacts/documents", methods=["GET"])
    def list_documents():
        """
        Every generated .docx currently in this web session's own
        output/<session_id>/ (or flat output/ for a caller with no
        session id), for the web client's own download picker -- see
        .artifact_downloads.list_output_documents's own docstring for why
        this has to be a directory listing rather than a fixed, known
        filename the way process/design/cloudarch above are. Same
        contract as the neuro-san port's own identical route.
        """
        from process_toolkit import paths as toolkit_paths
        from .artifact_downloads import list_output_documents

        with toolkit_paths.use_session(_web_session_id_for_get_request()):
            documents = list_output_documents()
        return jsonify({"status": "ok", "documents": documents})

    @web_app.route("/artifacts/documents/<filename>/download", methods=["GET"])
    def download_document(filename):
        """Downloads one generated .docx by its own filename (exactly as
        returned by GET /artifacts/documents) as a real file attachment,
        for the web client's download button -- see .artifact_downloads.
        safe_output_file_path for how `filename` is kept from escaping
        output/. `path` is resolved to a concrete absolute string up
        front, so send_file's own (possibly deferred) streaming below
        doesn't depend on the session context still being active."""
        from process_toolkit import paths as toolkit_paths
        from .artifact_downloads import safe_output_file_path

        with toolkit_paths.use_session(_web_session_id_for_get_request()):
            path = safe_output_file_path(filename)
        if path is None or not filename.lower().endswith(".docx"):
            return jsonify({
                "status": "error",
                "error": f"No generated document named '{filename}' in output/.",
            }), 404
        return send_file(
            path,
            as_attachment=True,
            download_name=os.path.basename(path),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @web_app.route("/artifacts/cloudarch/download", methods=["GET"])
    def download_cloudarch():
        """Downloads this web session's own output/<session_id>/
        cloudarch_drawio.xml (or flat output/ for a caller with no
        session id) as a real file attachment (as opposed to GET
        /artifacts/cloudarch above, which returns it JSON-wrapped as a
        string for the client's own mxGraph-XML renderer) -- for opening
        directly in a real draw.io client, or just keeping a copy."""
        from process_toolkit import paths as toolkit_paths

        with toolkit_paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(toolkit_paths.output_dir(), "cloudarch_drawio.xml")
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": "No cloudarch_drawio.xml found yet -- run the cloudarch pipeline at least once, then try again.",
            }), 404
        return send_file(path, as_attachment=True, download_name="cloudarch_drawio.xml", mimetype="application/xml")

    @web_app.route("/artifacts/cloudarch_iac/download", methods=["GET"])
    def download_cloudarch_iac():
        """Downloads this web session's own output/<session_id>/
        cloudarch_iac.zip as a real file attachment -- structurally
        identical to download_cloudarch above, for the IaC zip
        CloudArch_IaC_Pipeline's own final step produces."""
        from process_toolkit import paths as toolkit_paths
        from process_toolkit.iac.generation import IAC_ZIP_FILENAME

        with toolkit_paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(toolkit_paths.output_dir(), IAC_ZIP_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": "No cloudarch_iac.zip found yet -- run the IaC pipeline at least once, then try again.",
            }), 404
        return send_file(path, as_attachment=True, download_name=IAC_ZIP_FILENAME, mimetype="application/zip")

    @web_app.route("/artifacts/<name>/download", methods=["GET"])
    def download_process_or_design_json(name):
        """Downloads this web session's own output/<session_id>/
        process_data.json, design_data.json, requirements_summary.json,
        or proposal_response.json as a real file attachment (as opposed
        to GET /artifacts/<name> above, which returns it JSON-wrapped for
        the client's own data-explorer viewer) -- structurally identical
        to download_cloudarch above, just for the other artifact kinds.
        Same contract as the neuro-san port's own identical route. The
        downloaded file can later be re-attached to a chat turn to resume
        working on it -- see Process_Import_Agent/Design_Import_Agent's
        own instructions for how an attachment literally named
        process_data.json/design_data.json is recognized and restored
        verbatim rather than re-extracted, and Requirements_Summary_Agent's/
        Proposal_Response_Agent's own literal-restore STEPs for
        requirements_summary.json/proposal_response.json."""
        from process_toolkit import paths as toolkit_paths

        filenames = {
            "process": "process_data.json",
            "design": "design_data.json",
            "requirements": "requirements_summary.json",
            "proposal_response": "proposal_response.json",
        }
        filename = filenames.get(name)
        if filename is None:
            return jsonify({
                "status": "error",
                "error": (
                    f"Unknown artifact '{name}' -- use 'process', 'design', 'requirements', "
                    "or 'proposal_response'."
                ),
            }), 400
        with toolkit_paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(toolkit_paths.output_dir(), filename)
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": f"No {filename} found yet -- run the {name} pipeline at least once, then try again.",
            }), 404
        return send_file(path, as_attachment=True, download_name=filename, mimetype="application/json")

    @web_app.route("/agents/<name>/instructions", methods=["GET"])
    def agent_instructions(name):
        """
        Read-only lookup of one agent's real "instruction" (system
        prompt) text from root_agent's own live object tree -- for the
        web client's Agent Network tab, which otherwise only ever sees
        what's OBSERVABLE from the chat stream itself (an agent's dotted
        invocation path, how many times it's been called, its past
        queries/responses), never the actual prompt driving it. Same
        contract as the neuro-san port's own identical route.
        """
        index = _get_agent_instructions_index()
        instruction = index.get(name)
        if instruction is None:
            return jsonify({
                "status": "error",
                "error": f"No agent named '{name}' found in this project's own agent tree.",
            }), 404
        return jsonify({"status": "ok", "name": name, "instructions": instruction, "description": None, "source_file": None})

    @web_app.route("/status", methods=["GET"])
    def status():
        return jsonify({"status": "live", "model": MODEL})

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

    # One purge sweep thread for the life of this process -- see
    # process_toolkit.session_purge's own docstring. _active_web_sessions
    # (not a second on-disk flag) is what keeps a session currently
    # mid-request from being purged out from under it, regardless of how
    # stale its own last-activity timestamp looks. sessionMaxAgeDays/
    # sessionPurgeIntervalSeconds follow this port's own getProperty
    # convention (properties file, falling back to the SESSIONMAXAGEDAYS/
    # SESSIONPURGEINTERVALSECONDS env vars) -- same names the neuro-san
    # port's own cli.py reads directly as env vars.
    from process_toolkit.session_purge import start_session_purge_thread

    session_max_age_seconds = float(getProperty("sessionMaxAgeDays", default=3)) * 86400.0
    session_purge_interval_seconds = float(getProperty("sessionPurgeIntervalSeconds", default=3600))
    start_session_purge_thread(
        session_purge_interval_seconds,
        session_max_age_seconds,
        is_session_active=lambda session_id: session_id in _active_web_sessions,
    )

    scheme = "https" if use_https else "http"
    display_text(f"- Starting Process Architect web service on {scheme}://{host}:{listen_port} (POST /chat)...")
    web_app.run(host=host, port=listen_port, ssl_context=ssl_context, threaded=True, debug=False)


# ---------------------------------------------------------
# LOCAL "list"/"download" CONTROL LINES
# ---------------------------------------------------------
# Developed in tandem with the neuro-san port's own cli.py
# _display_output_document_listing/_handle_download_control_line -- same
# two control lines, same local-filesystem-copy semantics (no server
# round trip needed: the interactive/-f CLI already runs in-process on
# this project's own filesystem), shared by both start_local_chat (the
# REPL) and process_file (-f batch mode) below.
def _display_output_document_listing() -> None:
    """"list"/"ls" control line -- shows every generated .docx plus the
    cloud architecture diagram (if either exists), so "download <name>"
    has something concrete to copy from without the user having to go
    look inside output/ themselves."""
    from process_toolkit import paths as toolkit_paths
    from .artifact_downloads import cloudarch_diagram_exists, list_output_documents

    lines = []
    for doc in list_output_documents():
        lines.append(f"  {doc['filename']}  ({doc['size_bytes']:,} bytes, modified {doc['modified']})")
    if cloudarch_diagram_exists():
        cloudarch_path = os.path.join(toolkit_paths.output_dir(), "cloudarch_drawio.xml")
        stat = os.stat(cloudarch_path)
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        lines.append(f"  cloudarch_drawio.xml  ({stat.st_size:,} bytes, modified {modified})")
    if lines:
        display_text("[Action]: Generated documents in output/:\n" + "\n".join(lines))
    else:
        display_text("[Action]: No generated documents yet.")


def _handle_download_control_line(line: str) -> None:
    """"download <filename> [destination]" control line -- a plain local
    file copy, since the interactive/-f CLI modes already run in-process
    against this project's own filesystem (no server round trip needed,
    unlike the web client's own download buttons, which DO need the
    /artifacts/.../download Flask routes above since a browser has no
    direct filesystem access). `filename` is whatever "list" just showed
    (a generated .docx, or "cloudarch_drawio.xml"); `destination`
    defaults to the current working directory, and may itself be either
    a directory (the file is copied in under its own name) or a full
    target file path."""
    from .artifact_downloads import copy_artifact_to_destination

    parts = line.split(maxsplit=2)
    if len(parts) < 2:
        display_text("Usage: download <filename> [destination]", type="error")
        return
    filename = parts[1]
    destination = parts[2] if len(parts) > 2 else "."

    try:
        dest_path = copy_artifact_to_destination(filename, destination)
    except ValueError:
        display_text(
            f"No generated file named '{filename}' in output/. Use 'list' to see what's available.",
            type="error",
        )
        return
    except OSError as e:
        display_text(f"Could not copy '{filename}' to '{destination}': {e}", type="error")
        return
    display_text(f"[Action]: Downloaded '{filename}' to {dest_path}")


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
        elif line.lower() in ("list", "list documents", "ls"):
            _display_output_document_listing()
            return False
        elif line.lower() == "download" or line.lower().startswith("download "):
            _handle_download_control_line(line)
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
                text = _event_response_text(event)
                if text:
                    final_response = text

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
            text = _event_response_text(event)
            if text:
                final_response = text

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
        elif user_input.lower() in ("list", "list documents", "ls"):
            _display_output_document_listing()
            continue
        elif user_input.lower() == "download" or user_input.lower().startswith("download "):
            _handle_download_control_line(user_input)
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
                text = _event_response_text(event)
                if text:
                    final_response = text

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