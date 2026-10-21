#!/usr/bin/env python
"""Reinstates the ADK original's CLI surface
(samples/GCP/ProcessEngineering/process_agents/common/agent.py) against this
neuro-san port, talking to the top-level front-man (`process_architect` by
default) via neuro-san's own DIRECT (in-process) agent session -- no server
needs to be running for the default interactive/-i/-f modes.

Same flags as the ADK original:
    (no flags)         interactive chat REPL
    -i/--input TEXT    send one prompt, print the response, exit
    -f/--file PATH     submit each line of a file as a turn, in order
    -d/--detached      run this project's own server/UI (see below)
    --flask            with -d, run the Flask REST API below instead of `ns run`
    --http / -p/--port modify -d/--detached's listening port

Logging mirrors the ADK original's own pipeline_*.log exactly: standard
Python `logging`, a `LOGLEVEL` env var (same name, same five values --
DEBUG/INFO/WARNING/ERROR/CRITICAL, default WARNING), a file handler under
output/logs/ that follows LOGLEVEL, and a console handler fixed at
WARNING+ so a real problem (a timed-out agent, say) is still visible on
screen without needing LOGLEVEL raised. Off by default: this project's own
message-by-message agent/tool trace (which agent is active, token
accounting) logs at DEBUG/INFO, so set LOGLEVEL=DEBUG when you actually
want to see it -- `tail -f output/logs/cli.log` while it runs.

Same control lines recognized inside interactive/-f mode: "exit"/"quit"/
"stop", "clear" (reset the session), a leading "#" (comment, echoed but not
sent), "sleep <seconds>"/"wait <seconds>", a leading "$ ..." (run a raw
shell command instead of sending the line to the agent), and a trailing
"\\" to continue one logical line across multiple physical lines.

Plain -d/--detached (no --flask) launches neuro-san's own multi-session
HTTP server + nsflow chat UI (`ns run`) -- unchanged from before, still the
default, since it doesn't duplicate security-sensitive code neuro-san
already provides. -d --flask runs this project's OWN Flask REST API
instead: the same POST /chat, DELETE /chat/<session_id>, GET /status
contract (request/response JSON shapes, Authorization/X-API-Key auth,
WEBAPIKEY/WEBRATELIMITPERMINUTE/HOST/SSLCERTFILE/SSLKEYFILE/
ALLOWINSECUREWEBSERVICE env vars, loopback-only-unless-authenticated
refusal to start) as the ADK original's own -d mode -- see build_web_app's
docstring below. This exists so a single browser client (see
samples/WebClient/ProcessEngineering) can talk to EITHER backend
interchangeably, not to replace `ns run` as the default.

Must be run from this project's root directory (same requirement as
`uv run ns chat <network>` elsewhere in this project) -- neuro-san resolves
registries/manifest.hocon relative to the current working directory.
"""

import argparse
import asyncio
import base64
import binascii
import hmac
import json
import logging
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Loads a project-root .env file (if any) into os.environ, same as `ns
# chat`/`ns run` already do for this project's LLM provider API keys (see
# neuro_san_studio's own ProjectEnvironment.load_env_file) -- this project's
# README and .gitignore both already document/expect a .env file at this
# path, cli.py just never actually read it. Answers "can't you use a
# properties file for LOGLEVEL" with the mechanism this project already
# has, rather than inventing a second, parallel config-file convention: put
#     LOGLEVEL=DEBUG
# in a .env file here and it persists across every `cli.py` run, no need to
# prefix the command every time. Must run before anything below reads
# os.environ (LOGLEVEL in particular), and does not override a real
# environment variable that's already set (load_dotenv's own default).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# A direct (in-process) neuro-san session resolves agent names and
# CodedTool "class" references against AGENT_MANIFEST_FILE/AGENT_TOOL_PATH/
# PYTHONPATH, not simply "relative to cwd" -- `ns chat`/`ns run` set all
# three themselves before ever touching the client library (confirmed via
# the Dockerfile's entrypoint logs: "AGENT_MANIFEST_FILE set to: ..." /
# "AGENT_TOOL_PATH set to: ..."); a bare script importing the client
# directly (as this one does) has to do the same. PYTHONPATH specifically
# is easy to miss: neuro-san's ActivationFactory doesn't consult sys.path
# for this -- it reads the PYTHONPATH env var directly (os.environ, not
# sys.path) to find which entry AGENT_TOOL_PATH's absolute path sits
# under, then turns the remainder into the dotted module prefix it
# actually imports (see neuro_san/internals/graph/registry/
# activation_factory.py's _determine_agent_tool_path). Without it, class
# resolution fails with "Could not find class ... under AGENT_TOOL_PATH
# ''" the moment any agent tries to call a CodedTool -- the LLM call
# itself still succeeds, so this only surfaces once a real conversation
# actually reaches a tool call, not at session-open time. Set before
# importing anything from neuro_san.client so the very first manifest
# read already sees it. Uses this file's own directory rather than cwd,
# so `cli.py` works the same regardless of where it's invoked from.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# Force, don't setdefault: these two identify THIS project's own manifest/
# tools, never something a caller should override -- but a shell that
# already ran `ns chat`/`ns run` (per this project's own README) or another
# neuro-san project earlier in the same session leaves AGENT_MANIFEST_FILE/
# AGENT_TOOL_PATH exported, and setdefault would silently keep that stale
# value, reproducing the exact "Could not find class ... under
# AGENT_TOOL_PATH 'coded_tools'" failure this whole block exists to prevent
# (confirmed directly: a real run hit it with a stale, unset-looking
# relative AGENT_TOOL_PATH left over from an earlier session).
os.environ["AGENT_MANIFEST_FILE"] = os.path.join(_PROJECT_ROOT, "registries", "manifest.hocon")
os.environ["AGENT_TOOL_PATH"] = os.path.join(_PROJECT_ROOT, "coded_tools")
if _PROJECT_ROOT not in (os.environ.get("PYTHONPATH") or "").split(os.pathsep):
    existing_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = (
        f"{existing_pythonpath}{os.pathsep}{_PROJECT_ROOT}" if existing_pythonpath else _PROJECT_ROOT
    )

# Alongside output/ (process_data.json, cloudarch_drawio.xml, generated
# *.docx, ...), this is this project's answer to the ADK original's own
# output/logs/pipeline_*.log: real, inspectable records of a run, not just
# whatever scrolled past in the terminal.
_LOGS_DIR = os.path.join(_PROJECT_ROOT, "output", "logs")
_THINKING_FILE = os.path.join(_LOGS_DIR, "agent_thinking.txt")
_THINKING_DIR = os.path.join(_LOGS_DIR, "agent_thinking")
_APP_LOG_FILE = os.path.join(_LOGS_DIR, "cli.log")

# Actual configuration happens in coded_tools/__init__.py (same shared
# helper also configures logging for the `ns chat`/`ns run` server path,
# which never executes this file at all, and previously had no equivalent
# logging setup whatsoever) -- that module is guaranteed to run before any
# CodedTool loads, including as a side effect of the very next import
# below, so it must be told the filename cli.py wants BEFORE that import
# happens, not after. Mirrors the ADK original's own agent.py logging
# setup: a dedicated "ProcessArchitect" logger (not root), a LOGLEVEL env
# var (same name, same five values) controlling the file handler, and a
# console handler fixed at WARNING+ regardless of LOGLEVEL -- so raising
# LOGLEVEL to get full DEBUG tracing never also floods the terminal with
# it; that still only goes to the file. Default WARNING means none of
# this project's own DEBUG/INFO trace logging below is active (or written
# anywhere) unless deliberately turned on -- "off by default, tracing
# when you need it," not a bespoke print mechanism of this script's own.
os.environ["PROCESS_ARCHITECT_LOG_FILENAME"] = "cli.log"
import coded_tools  # noqa: E402,F401 -- triggers configure_logging() above

from neuro_san.client.agent_session_factory import AgentSessionFactory  # noqa: E402
from neuro_san.client.streaming_input_processor import StreamingInputProcessor  # noqa: E402
from neuro_san.internals.journals.origination import Origination  # noqa: E402
from neuro_san.message.processors.message_processor import MessageProcessor  # noqa: E402
from neuro_san.message.types.chat_message_type import ChatMessageType  # noqa: E402
from neuro_san.message.types.chat_message_type_util import ChatMessageTypeUtil  # noqa: E402

from process_toolkit.ingestion.extractors import stage_attachments_to_directory  # noqa: E402
from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat  # noqa: E402
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY  # noqa: E402

AGENT_NAME_DEFAULT = "process_architect"
SLEEP_DEFAULT_SECONDS = 0.5

# POST /chat and /chat/stream's optional "files" field (see
# _parse_attachments below): each entry is {"name", "mime_type",
# "data_base64"}. neuro-san's own chat.proto has a "mime_data" field for
# genuine multimodal content, but it's a stub in the installed neuro-san
# version (base_message_dictionary_converter.py explicitly skips it,
# "# No mime_data for now", and the one utility that WOULD turn it into
# real model content is never called anywhere in the package) -- wiring a
# client-supplied mime_data through would silently vanish, not reach the
# LLM.
#
# Attachments are staged to a FIXED, per-ChatSession on-disk directory
# (see ChatSession._attachments_directory/_ingest_attachments below) via
# stage_attachments_to_directory, and that directory's path is appended
# directly to the user's own message text as a literal
# "[ATTACHMENT DIRECTORY: <path>]" marker (see
# ATTACHMENT_DIRECTORY_MARKER_TEMPLATE) -- NOT passed through sly_data to
# a dedicated CodedTool. An earlier version of this did exactly that (a
# "load_attached_files" CodedTool reading sly_data), which is architecturally
# sound (neuro-san threads the same sly_data dict unchanged through every
# level of a nested agent-calls-agent chain) but depends on an LLM
# correctly choosing to call that extra tool before anything else, every
# single turn -- exactly the kind of instruction an agent can quietly
# skip under its own judgment. Putting the directory path directly into
# the visible request text instead reuses the SAME "if request explicitly
# names a directory, read it" handling every network already has for a
# user who types a path themselves -- no new tool-calling behavior to
# rely on, and the path is directly visible in the agent's own thinking-
# file trace for debugging, instead of sitting invisibly in sly_data.
ATTACHMENT_DIRECTORY_MARKER_TEMPLATE = "[ATTACHMENT DIRECTORY: {path}]"
ATTACHMENT_MAX_FILES = 4
ATTACHMENT_MAX_BYTES = 8 * 1024 * 1024  # per file, raw (decoded) size

# Flask's own MAX_CONTENT_LENGTH (set on web_app in build_web_app) rejects an
# oversized request before reading its body at all -- without it, the /chat
# and /chat/stream routes call request.get_json() first and only check
# ATTACHMENT_MAX_FILES/ATTACHMENT_MAX_BYTES afterward, so a request far
# beyond what any legitimate attachment set could produce would still be
# fully parsed into memory (the JSON body, its base64 strings, all of it)
# before those per-file limits ever get a chance to reject it. Derived from
# the two limits above rather than its own constant, so it can't drift out
# of sync with them: base64 inflates raw bytes by ~4/3, and the extra 1MB
# covers the query text plus JSON punctuation/field-name overhead.
MAX_REQUEST_BODY_BYTES = int(ATTACHMENT_MAX_FILES * ATTACHMENT_MAX_BYTES * 4 / 3) + 1 * 1024 * 1024

_trace_logger = logging.getLogger("ProcessArchitect.CLI.Trace")
_web_logger = logging.getLogger("ProcessArchitect.CLI.WebService")

ANSI_RESET = "\033[0m"
ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_CYAN = "\033[96m"


def display_text(text: str, kind: str = "info", end: str = "\n") -> None:
    colour = {"info": ANSI_GREEN, "warning": ANSI_CYAN, "error": ANSI_RED}.get(kind, ANSI_GREEN)
    prefix = {"warning": "[Warning]: ", "error": "[Error]: "}.get(kind, "")
    print(f"{colour}{prefix}{text}{ANSI_RESET}", end=end)
    sys.stdout.flush()


class LiveTraceMessageProcessor(MessageProcessor):
    """Logs a concise one-line trace of every message in a turn's
    streaming response -- which agent is active, what kind of message it
    produced, and a short preview of its text/structure -- at DEBUG level
    via the standard `logging` module (see the LOGLEVEL setup above), not
    a bespoke print mechanism. Silent by default; set LOGLEVEL=DEBUG to
    see it in output/logs/cli.log. Complements the full-detail "thinking"
    trace files (see ChatSession.__init__), which are neuro-san's own
    always-on, unconditional record of every message regardless of
    LOGLEVEL -- this is the lighter-weight, level-gated version of the
    same stream.
    """

    _PREVIEW_LEN = 160

    def process_message(self, chat_message_dict: Dict[str, Any], message_type: ChatMessageType) -> None:
        if not _trace_logger.isEnabledFor(logging.DEBUG):
            return  # skip formatting work entirely when DEBUG tracing isn't even on

        text = chat_message_dict.get("text")
        structure = chat_message_dict.get("structure")

        # An AGENT_PROGRESS message with empty text and no structure is the
        # server's HTTP heartbeat keepalive frame, not real progress --
        # same filter ThinkingFileMessageProcessor itself uses, so the
        # trace isn't swamped with one blank line per tick either.
        if message_type == ChatMessageType.AGENT_PROGRESS and not text and structure is None:
            return

        origin_str = Origination.get_full_name_from_origin(chat_message_dict.get("origin")) or "?"
        type_str = ChatMessageTypeUtil.to_string(message_type)

        preview = (text or "").strip().replace("\n", " ")
        if not preview and isinstance(structure, dict):
            preview = f"<structure: {', '.join(structure.keys())}>"
        if len(preview) > self._PREVIEW_LEN:
            preview = preview[: self._PREVIEW_LEN - 1] + "…"

        tool_result_origin = chat_message_dict.get("tool_result_origin")
        suffix = ""
        if tool_result_origin:
            result_from = Origination.get_full_name_from_origin([tool_result_origin[-1]])
            suffix = f" (result from {result_from})"

        _trace_logger.debug("%s [%s]%s: %s", origin_str, type_str, suffix, preview)


def is_shell_command(text: Optional[str]) -> bool:
    """A leading "$" is this CLI's escape convention for running a raw
    shell command instead of sending the line to the agent -- same
    convention as the ADK original."""
    return bool(text) and text.strip().startswith("$")


def run_shell_command(cmdline: str) -> None:
    command = cmdline.strip()[1:].strip()
    display_text(f"[Shell]: {command}")
    try:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            display_text(f"[Shell]: {proc.stderr}", kind="error")
        if proc.returncode != 0:
            display_text(f"Shell command exited with code {proc.returncode}", kind="error")
    except Exception as e:
        display_text(f"[Shell]: Error executing command: {e}", kind="error")


def _parse_attachments(payload: Dict[str, Any]) -> "tuple[Optional[List[Dict[str, Any]]], Optional[str]]":
    """
    Validates and decodes POST /chat or /chat/stream's optional "files"
    field: [{"name": str, "mime_type": str, "data_base64": str}, ...].
    Returns (decoded_files, None) on success -- decoded_files is the same
    shape with "data_base64" replaced by "data" (raw bytes) -- or
    (None, error_message) on the first violation found, for the caller to
    turn into a 400 response exactly like the existing "query required"
    check does. Returns ([], None) when "files" is absent/empty -- not an
    error, just nothing to attach.

    Re-validates server-side (size/count) even though the web client
    enforces the same limits before ever sending -- a client is never a
    trusted boundary; a modified or scripted caller could send an
    oversized/overlong payload directly against this route.
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


def _append_attachment_directory_marker(text: str, directory: Optional[str]) -> str:
    """Appends an "[ATTACHMENT DIRECTORY: <path>]" marker (see
    ATTACHMENT_DIRECTORY_MARKER_TEMPLATE's own comment for why this is a
    literal text marker rather than a sly_data-only signal) onto the
    user's own message text, so the agent network's existing "request
    explicitly names a directory" handling picks it up exactly like a
    user who typed a path themselves. Returns `text` unchanged when
    `directory` is None (no attachment this turn)."""
    if not directory:
        return text
    marker = ATTACHMENT_DIRECTORY_MARKER_TEMPLATE.format(path=directory)
    return f"{text}\n\n{marker}" if text else marker


def _extract_usage(token_accounting: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Maps neuro-san's own token_accounting dict (see
    TokenAccountingMessageProcessor/LangChainTokenCounter in the installed
    neuro_san package -- "models" is a {provider_class: {model_name:
    {total_tokens, prompt_tokens, completion_tokens, ...}}} nested dict)
    onto the {prompt_tokens, completion_tokens, total_tokens, model} shape
    the web client's Token Usage tab expects -- the exact same keys the ADK
    original's own usage field uses, so the client doesn't need to know
    which backend it's talking to.

    Unlike the ADK original (one single statically-configured model,
    applied uniformly), neuro-san can genuinely invoke more than one
    distinct model within a single turn, so "model" here is every distinct
    model name actually seen this turn, joined with " + " -- real,
    per-turn data, not a static guess. None if neuro-san reported no
    accounting at all (e.g. a turn that made no LLM calls).
    """
    if not token_accounting:
        return None
    models = token_accounting.get("models") or {}
    model_names = sorted({name for providers in models.values() for name in providers.keys()})
    return {
        "prompt_tokens": token_accounting.get("prompt_tokens", 0),
        "completion_tokens": token_accounting.get("completion_tokens", 0),
        "total_tokens": token_accounting.get("total_tokens", 0),
        "model": " + ".join(model_names) if model_names else None,
    }


def _release_any_leftover_pipeline_lock(sly_data: Optional[Dict[str, Any]]) -> None:
    """
    Safety net: every pipeline (process/design-doc/cloudarch) acquires its
    own output/ directory pipeline-lock exactly once, as the first action
    of a brand new top-level turn (reset_loop_state_tool.py), and releases
    it (doc_generation_tool.py / loop_control_tool.py) once that SAME
    turn's own generate/review loop genuinely finishes -- the whole thing
    happens within one send()/send_streaming() call, never spanning more
    than one turn. So a token still sitting in sly_data once that call has
    returned, for ANY reason, means the pipeline's own finalize step never
    ran.

    The one way that happens: POST /chat/<session_id>/stop (see
    build_web_app's own chat_stop route) reaches into
    self.session.invocation_context.get_asyncio_executor().
    cancel_current_tasks(), cancelling whatever tool/model call is
    currently in flight -- there is no guarantee the specific CodedTool
    call that would have released the lock ever runs afterward. Without
    this, a cancelled turn would leave BOTH the lock AND its background
    heartbeat (process_toolkit.run_lock) running forever -- worse than
    before that heartbeat existed, since the heartbeat would keep the
    lock's started_at fresh indefinitely, permanently defeating the
    staleness-based self-healing every pipeline run still depends on for
    the crash/abandonment case the heartbeat was never meant to replace.

    Called from both send() and send_streaming()'s own cleanup,
    unconditionally (success, in-band error, and cancellation alike) --
    cheap and a no-op on the overwhelming majority of calls, where the
    pipeline's own finalize step already released everything normally.
    """
    if not sly_data:
        return
    token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
    if not token:
        return
    _web_logger.warning(
        "Turn ended with pipeline lock token %s still held -- releasing it "
        "defensively (most likely a cancelled turn).", token,
    )
    stop_pipeline_lock_heartbeat(token)
    release_pipeline_lock(token)


class ChatSession:
    """One underlying neuro-san direct session against an agent network,
    plus the request/response state (chat_context, sly_data) that must be
    threaded from one turn to the next for the conversation to actually
    continue rather than looking like a fresh request every time. Mirrors
    the role of the ADK original's Runner+session_id pair -- "clear"
    replaces one of these wholesale, exactly like the ADK's
    init_session_and_runner did.
    """

    def __init__(self, agent_name: str, isolated: bool = False):
        """
        isolated: use a unique thinking-file/dir pair under this instance's
        own output/logs/web_sessions/<uuid>/ subdirectory instead of the
        single shared _THINKING_FILE/_THINKING_DIR. The interactive/-i/-f
        CLI modes only ever have ONE ChatSession alive at a time, so wiping
        the shared global trace path on each "clear"/new session is exactly
        the desired "fresh trace per session" behavior there -- but the web
        service (see run_web_service) can have many ChatSessions alive
        concurrently, and without this, constructing session B would wipe
        out session A's still-active trace files out from under it. False
        by default so every existing (single-session) caller is unaffected.
        """
        self.agent_name = agent_name
        factory = AgentSessionFactory()
        self.session = factory.create_session("direct", agent_name, use_direct=True)

        if isolated:
            session_dir = os.path.join(_LOGS_DIR, "web_sessions", str(uuid.uuid4()))
            os.makedirs(session_dir, exist_ok=True)
            thinking_file = os.path.join(session_dir, "agent_thinking.txt")
            thinking_dir = os.path.join(session_dir, "agent_thinking")
        else:
            # Fresh trace per session (matching AgentCli.open_session's own
            # "clear out the previous thinking file/dir contents" behavior) --
            # a stale trace from an earlier, unrelated session shouldn't be
            # mistaken for this one's.
            os.makedirs(_LOGS_DIR, exist_ok=True)
            if os.path.exists(_THINKING_DIR):
                shutil.rmtree(_THINKING_DIR)
            os.makedirs(_THINKING_DIR)
            thinking_file = _THINKING_FILE
            thinking_dir = _THINKING_DIR

        os.makedirs(thinking_dir, exist_ok=True)
        with open(thinking_file, "w", encoding="utf-8") as f:
            f.write("\n")

        self.input_processor = StreamingInputProcessor("DEFAULT", thinking_file, self.session, thinking_dir)
        # Added after thinking_file/thinking_dir so the thinking-file writer
        # (installed by StreamingInputProcessor's own __init__) still runs
        # first -- order matters for a CompositeMessageProcessor's "block
        # downstream processing" semantics, not needed here, but matching
        # it anyway avoids any dependency on that not mattering later.
        self.input_processor.get_message_processor().add_processor(LiveTraceMessageProcessor())
        self.sly_data = None
        self.chat_context = None
        # Fixed for this ChatSession's entire lifetime -- deterministic
        # (pid + this instance's own id(), not a random mkdtemp suffix)
        # specifically so it's easy to find and inspect by hand while
        # debugging ("ls /tmp/process_architect_attachments_*"), and so
        # every turn's attachments land in the SAME place rather than a
        # fresh path each time. Created lazily (only once a turn actually
        # attaches a file -- see _ingest_attachments), not here, so a
        # session that never attaches anything never touches disk for this.
        self._attachments_directory = os.path.join(
            tempfile.gettempdir(), f"process_architect_attachments_{os.getpid()}_{id(self):x}",
        )
        # Set by send()/send_streaming() below, for the web service's
        # Token Usage tab -- see _extract_usage's own docstring for the
        # mapping from neuro-san's own token_accounting shape.
        self.last_usage: Optional[Dict[str, Any]] = None
        # The web service (run_web_service, threaded=True) can dispatch two
        # overlapping requests for the SAME session_id onto two different
        # OS threads, both resolving to this one ChatSession instance (see
        # _get_or_create_web_session) -- a double-click/retry on /chat, or
        # overlapping /chat + /chat/stream calls. Without a lock, their
        # read-modify-write of self.sly_data/self.chat_context (and
        # _ingest_attachments' check-then-set of self.sly_data) can
        # interleave and silently lose or clobber a turn's updates. A plain
        # threading.Lock, not asyncio.Lock, matches _web_sessions_lock
        # above: these are real OS threads, not one shared event loop.
        self._lock = threading.Lock()
        # Updated on every send()/send_streaming() call; read by the web
        # service's idle-session eviction sweep (see _web_sessions above).
        self.last_accessed = time.monotonic()

    def _cleanup_attachments_directory(self) -> None:
        """Removes this session's fixed attachment-staging directory
        (self._attachments_directory, set once in __init__) from disk,
        if it was ever created. Called only from close() -- the
        directory is a FIXED path for this session's whole lifetime now
        (not a fresh one per turn; see _ingest_attachments), so it only
        needs releasing once, when the session itself ends, not between
        turns."""
        shutil.rmtree(self._attachments_directory, ignore_errors=True)

    def _ingest_attachments(self, files: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """
        Stages this turn's attached files (see _parse_attachments) into
        this session's FIXED self._attachments_directory
        (process_toolkit.ingestion.extractors.stage_attachments_to_directory
        clears any files already there first, so a later turn's set
        never mixes with an earlier one left behind in the same path).

        Returns that directory path if files were staged THIS turn, or
        None if `files` was empty. The caller (send()/send_streaming())
        uses a non-None return to append an
        "[ATTACHMENT DIRECTORY: <path>]" marker (see
        ATTACHMENT_DIRECTORY_MARKER_TEMPLATE) directly onto the user's
        own message text -- a literal, visible string every network's
        existing "request explicitly names a directory" handling already
        knows how to act on, rather than a side channel (sly_data plus a
        dedicated CodedTool) an agent has to remember to separately call
        before anything else, every single turn.

        No-op (returns None, touches nothing on disk) when `files` is
        empty -- a turn with no NEW attachments leaves the directory's
        existing contents (from an earlier turn) alone, so a later turn
        can still reference something attached a few messages back by
        name, without re-attaching it.

        Raises RuntimeError if staging fails (see
        stage_attachments_to_directory's own "ERROR" cases -- e.g. a full
        disk) -- callers (send()/send_streaming()) already have a
        try/except around the whole turn that turns this into a clean
        "An internal error has occurred" response while logging the real
        reason, which is the right outcome here: silently proceeding as
        if nothing had been attached would make the user's actual
        requirements vanish with zero indication anything went wrong.
        """
        if not files:
            return None
        result = stage_attachments_to_directory(files, directory=self._attachments_directory)
        if result.get("status") != "OK":
            _web_logger.warning(
                "Failed to stage %d attached file(s) to disk: %s",
                len(files), result.get("error"),
            )
            raise RuntimeError(f"Failed to stage attached files to disk: {result.get('error')}")
        # WARNING, not INFO -- this project's console handler is fixed at
        # WARNING+ regardless of LOGLEVEL (see logging_setup's own
        # comment), so confirming a successful staging is visible
        # on-screen immediately, not only in output/logs/cli.log and only
        # if LOGLEVEL happens to be raised. This is the one concrete,
        # zero-LLM-cost checkpoint for "did the attachment actually make
        # it past the HTTP layer" -- if this line is missing from a run
        # where a file was attached, the problem is upstream of this
        # project's own code (the client never sent "files", or sent it
        # somewhere _parse_attachments doesn't look).
        _web_logger.warning(
            "Staged %d attached file(s) to %s: %s",
            len(result["files_written"]), result["directory"], result["files_written"],
        )
        return result["directory"]

    def close(self) -> None:
        """Releases this session's resources: the attachment-staging
        directory, then the underlying neuro-san session. Called from
        both the web service's idle-eviction sweep and its DELETE
        /chat/<session_id> route -- centralized here so neither call
        site can forget the staging-directory half of cleanup."""
        self._cleanup_attachments_directory()
        self.session.close()

    def send(self, text: str, files: Optional[List[Dict[str, Any]]] = None) -> str:
        with self._lock:
            turn_started = time.monotonic()
            self.last_accessed = turn_started
            try:
                attachments_directory = self._ingest_attachments(files)
                effective_text = _append_attachment_directory_marker(text, attachments_directory)
                state = {
                    "last_chat_response": None,
                    "user_input": effective_text,
                    "sly_data": self.sly_data,
                    "chat_context": self.chat_context or {},
                    "chat_filter": {"chat_filter_type": "MAXIMAL"},
                    "num_input": 0,
                }
                state = self.input_processor.process_once(state)
                self.sly_data = state.get("sly_data")
                self.chat_context = state.get("chat_context")

                token_accounting = state.get("token_accounting")
                self.last_usage = _extract_usage(token_accounting)

                # Previously only logged AT ALL when token_accounting happened
                # to be present, and even then carried no duration or explicit
                # outcome -- a successful turn with no accounting data left no
                # trace whatsoever at INFO level, the level this project's own
                # logging_setup.py defaults LOGLEVEL to.
                if _trace_logger.isEnabledFor(logging.INFO):
                    _trace_logger.info(
                        "Chat turn completed: duration=%.2fs usage=%s",
                        time.monotonic() - turn_started,
                        json.dumps(token_accounting) if token_accounting else None,
                    )

                return state.get("last_chat_response") or ""
            finally:
                _release_any_leftover_pipeline_lock(self.sly_data)

    def send_streaming(self, text: str, files: Optional[List[Dict[str, Any]]] = None):
        """
        Generator version of send(): yields an incremental update dict
        after EVERY message produced in the agent network's response
        stream for this turn, instead of blocking until the whole turn
        completes and returning only the final text. Threads
        self.sly_data/self.chat_context forward exactly like send() does
        (reusing self.input_processor's own formulate_chat_request/reset,
        not reimplementing them), so a session can freely mix streaming
        and non-streaming turns.

        self.session.streaming_chat() (neuro-san's own primitive --
        StreamingInputProcessor.process_once uses the exact same call
        internally, see its own source) is already a real generator
        yielding messages as the agent network produces them, not
        something synthesized here -- process_once just drains it fully
        before returning anything. This method is the minimal possible
        duplication of process_once's loop body needed to yield instead
        of drain, reusing every other piece of it as-is.

        Yields dicts shaped like one of:
          {"status": "progress", "origin": "<agent>", "text": "<short note>"}
          {"status": "delta", "text": "<compiled answer SO FAR -- always
                                         the full current text, not a
                                         fragment to append, so a client
                                         can just replace what it shows
                                         with this>"}
          {"status": "done", "response": "<final compiled answer>",
           "usage": {"prompt_tokens": N, "completion_tokens": N,
                      "total_tokens": N, "model": "..."} or None}
          {"status": "stopped", "response": "<partial answer so far>"}
        `session_id` is NOT included here -- the caller (the web
        service's /chat/stream route) adds it, since this method has no
        notion of a "web session" at all.

        A "stopped" event means POST /chat/<session_id>/stop (see
        build_web_app's own chat_stop route) reached into
        self.session.invocation_context.get_asyncio_executor() and
        cancelled this turn's in-flight tasks there -- NOT merely that the
        client gave up reading the stream (which alone would not stop the
        real model call, or its real token cost, from running to
        completion in the background). neuro-san's own
        DirectAgentSession.streaming_chat() explicitly documents this as
        the intended way to interrupt it (see its own "interrupted by
        caller-side 'close' method" comment in the installed neuro_san
        package).
        """
        # Held for this whole generator's lifetime (across every yield, not
        # just the setup below) -- same race as send() above, but a stream
        # is long-lived, so a second overlapping request for this session
        # must wait for the WHOLE turn, not just this method's setup, or it
        # could still interleave its own sly_data/chat_context read-modify-
        # write with this turn's eventual one at the bottom. Released
        # whenever this generator is exhausted, returns early, or is
        # closed/GC'd (GeneratorExit also unwinds through this `with`).
        with self._lock:
            turn_started = time.monotonic()
            self.last_accessed = turn_started
            attachments_directory = self._ingest_attachments(files)
            effective_text = _append_attachment_directory_marker(text, attachments_directory)
            processor = self.input_processor.get_message_processor()
            chat_filter = {"chat_filter_type": "MAXIMAL"}
            chat_request = self.input_processor.formulate_chat_request(
                effective_text, self.sly_data, self.chat_context or {}, chat_filter
            )
            self.input_processor.reset()

            last_compiled_answer = None
            try:
                try:
                    for chat_response in self.session.streaming_chat(chat_request):
                        response = chat_response.get("response") or {}
                        processor.process_message(response)

                        compiled_answer = processor.get_compiled_answer()
                        if compiled_answer and compiled_answer != last_compiled_answer:
                            last_compiled_answer = compiled_answer
                            yield {"status": "delta", "text": compiled_answer}
                            continue

                        # Not an answer-text update -- surface it as a lightweight
                        # progress note instead, same heartbeat filter
                        # LiveTraceMessageProcessor already uses (an AGENT_PROGRESS
                        # message with empty text and no structure is the server's own
                        # keepalive frame, not real progress).
                        #
                        # A message with a "structure" payload but no "text" (observed
                        # in practice: neuro-san's own token-accounting bookkeeping
                        # pings, which carry a {total_tokens, prompt_tokens, ...} dict)
                        # used to fall back to a synthetic "<structure: key1, key2,
                        # ...>" preview -- literally the dict's field NAMES, not its
                        # values, with zero conversational meaning -- and the web
                        # client renders every yielded "progress" event as a visible
                        # step in the turn's "Thinking" trace, so that leaked straight
                        # into the chat transcript as confusing noise. The real token
                        # totals already reach the client cleanly via this method's
                        # own "done" event ("usage", built from
                        # processor.get_token_accounting() below) -- this stream is
                        # only ever meant to preview genuine progress TEXT, so a
                        # structure-only message (no text) is simply skipped, the
                        # same as the heartbeat case.
                        text_field = response.get("text")
                        if not text_field:
                            continue
                        preview = text_field.strip().replace("\n", " ")
                        if not preview:
                            continue
                        if len(preview) > 160:
                            preview = preview[:159] + "…"
                        origin_str = Origination.get_full_name_from_origin(response.get("origin")) or "agent network"
                        yield {"status": "progress", "origin": origin_str, "text": preview}
                except asyncio.CancelledError:
                    if _trace_logger.isEnabledFor(logging.INFO):
                        _trace_logger.info(
                            "Chat stream turn stopped: duration=%.2fs", time.monotonic() - turn_started,
                        )
                    yield {"status": "stopped", "response": last_compiled_answer or ""}
                    return

                self.chat_context = processor.get_chat_context()
                returned_sly_data = processor.get_sly_data()
                if returned_sly_data is not None:
                    if self.sly_data is not None:
                        self.sly_data.update(returned_sly_data)
                    else:
                        self.sly_data = returned_sly_data.copy()

                token_accounting = processor.get_token_accounting()
                self.last_usage = _extract_usage(token_accounting)

                # Previously only logged AT ALL when token_accounting happened
                # to be present, and even then carried no duration or explicit
                # outcome -- a successful turn with no accounting data left no
                # trace whatsoever at INFO level, the level this project's own
                # logging_setup.py defaults LOGLEVEL to.
                if _trace_logger.isEnabledFor(logging.INFO):
                    _trace_logger.info(
                        "Chat stream turn completed: duration=%.2fs usage=%s",
                        time.monotonic() - turn_started,
                        json.dumps(token_accounting) if token_accounting else None,
                    )

                yield {"status": "done", "response": last_compiled_answer or "", "usage": self.last_usage}
            finally:
                _release_any_leftover_pipeline_lock(self.sly_data)


async def handle_logical_line(
    line: str, session_holder: List[ChatSession], agent_name: str, echo_input: bool = False,
) -> bool:
    """Processes one fully-assembled (continuation-joined) instruction
    line. Returns True if the caller should stop reading further lines.
    session_holder is a 1-element list so "clear" can rebind it in place.

    `echo_input`: whether to print the line back as "[user-file]: <line>"
    before submitting it. False by default (interactive mode) -- the
    terminal already echoed what was typed, so repeating it is redundant.
    process_file passes True: there's no terminal echo for lines read from
    a file, so without this nothing shows what's actually being submitted
    -- matching the ADK original's own file-mode-only echo.
    """
    if not line:
        return False

    lowered = line.lower()
    if lowered in ("exit", "quit", "stop"):
        display_text("Exiting Process Architect Orchestrator.")
        return True
    if lowered == "clear":
        display_text("[Action]: Clearing all histories and resetting session...")
        session_holder[0] = ChatSession(agent_name)
        return False
    if line.startswith("#"):
        display_text(f"[Comment]: {line}")
        return False
    if lowered.startswith("sleep") or lowered.startswith("wait"):
        parts = line.split()
        secs = float(parts[1]) if len(parts) > 1 else SLEEP_DEFAULT_SECONDS
        display_text(f"[Action]: Sleeping for {secs} seconds...")
        await asyncio.sleep(secs)
        return False
    if is_shell_command(line):
        run_shell_command(line)
        return False

    if echo_input:
        display_text(f"[user-file]: {line}")
    try:
        response = await asyncio.to_thread(session_holder[0].send, line)
        display_text(f"[ArchitectBot]: {response or '[No final response]'}")
    except Exception as e:
        display_text(f"An error occurred: {e}", kind="error")
    return False


async def process_file(file_path: str, agent_name: str) -> None:
    """-f <file> batch mode: reads `file_path` line by line and submits
    each logical line (honoring "\\" continuation) to the agent in turn,
    recognizing the same control lines as the interactive REPL."""
    try:
        with open(file_path, "r", encoding="utf-8-sig"):
            pass
    except Exception as e:
        display_text(f"Error opening file '{file_path}': {e}", kind="error")
        sys.exit(1)

    session_holder: List[ChatSession] = [ChatSession(agent_name)]

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            continuation_parts: List[str] = []
            for raw_line in f:
                bare = raw_line.rstrip("\n").rstrip("\r")
                if bare.rstrip().endswith("\\"):
                    continuation_parts.append(bare.rstrip()[:-1].strip())
                    continue
                continuation_parts.append(bare.strip())
                line = " ".join(part for part in continuation_parts if part)
                continuation_parts = []
                if await handle_logical_line(line, session_holder, agent_name, echo_input=True):
                    return
            if continuation_parts:
                line = " ".join(part for part in continuation_parts if part)
                await handle_logical_line(line, session_holder, agent_name, echo_input=True)
    except Exception as e:
        display_text(f"Error processing file: {e}", kind="error")
        sys.exit(1)


async def process_single_prompt(prompt: str, agent_name: str) -> None:
    """-i <text>: send one prompt, print the response, and return -- no
    REPL loop, no file parsing."""
    session = ChatSession(agent_name)
    try:
        response = await asyncio.to_thread(session.send, prompt)
        display_text(f"[ArchitectBot]: {response or '[No final response]'}")
    except Exception as e:
        display_text(f"An error occurred: {e}", kind="error")
        sys.exit(1)


async def start_local_chat(agent_name: str) -> None:
    display_text(f"Process Architect Orchestrator (local mode, agent={agent_name})")
    display_text("Type 'exit' to quit. Use '\\' at the end of a line to continue on a new line.")

    session_holder: List[ChatSession] = [ChatSession(agent_name)]

    while True:
        try:
            input_buffer: List[str] = []
            while True:
                prompt_prefix = "[user]: " if not input_buffer else "... "
                raw_line = input(prompt_prefix)
                if raw_line.rstrip().endswith("\\"):
                    input_buffer.append(raw_line.rstrip()[:-1].strip())
                else:
                    input_buffer.append(raw_line.strip())
                    break
            user_input = " ".join(part for part in input_buffer if part).strip()
        except (EOFError, KeyboardInterrupt):
            display_text("\nExiting Process Architect Orchestrator.")
            break

        if not user_input:
            continue
        if await handle_logical_line(user_input, session_holder, agent_name):
            break


# ---------------------------------------------------------
# WEB SERVICE MODE (Flask REST API, -d/--detached --flask)
# ---------------------------------------------------------
# Deliberately the SAME REST contract as the ADK original's own Flask web
# service (samples/GCP/ProcessEngineering/process_agents/common/agent.py's
# build_web_app/run_web_service) -- same routes, same request/response JSON
# shapes, same auth header conventions, same cookie name -- so a single web
# client (see samples/WebClient/ProcessEngineering) can talk to EITHER
# backend interchangeably. Plain -d/--detached (no --flask) still launches
# neuro-san's own `ns run` server/UI unchanged -- --flask selects this REST
# layer INSTEAD, for parity with the ADK original, not as a replacement.
#
# Session continuity works differently here than on the ADK side: instead
# of mapping a web session id to an (user_id, session_id) pair replayed
# through one shared Runner, each web session id maps directly to its own
# ChatSession instance (the same class the interactive/-i/-f modes use) --
# ChatSession already threads its own sly_data/chat_context forward between
# turns internally, so there is no separate "runner" to lazily share.
_web_sessions: Dict[str, ChatSession] = {}
_web_sessions_lock = threading.Lock()
WEB_SESSION_COOKIE = "process_architect_session"

# A client that creates a session and never calls DELETE /chat/<session_id>
# (closed tab, crash, forgotten cleanup) would otherwise leak its entry here
# -- and the live neuro-san DirectAgentSession/thinking-file directory
# under it -- for the life of the process. Entries idle longer than this
# are swept opportunistically by _get_or_create_web_session below.
# Generous relative to this project's own documented ~5-10 minute typical
# turn time, so a slow-but-active session is never evicted out from under
# a still-engaged user.
_WEB_SESSION_IDLE_TIMEOUT_SECONDS = float(os.environ.get("WEBSESSIONIDLETIMEOUTSECONDS", "3600"))
# Bounds how often the sweep below actually scans _web_sessions, independent
# of request volume -- a pure efficiency knob, not something a deployer
# needs to tune, so it's a plain constant rather than an env var.
_WEB_SESSION_SWEEP_INTERVAL_SECONDS = 300.0
_web_sessions_last_swept = 0.0

# web_session_id -> count of requests currently holding a reference to it,
# from the moment _get_or_create_web_session resolves/creates it through
# the moment the caller (the /chat or /chat/stream route) is fully done
# with it -- see _release_web_session. A COUNT, not a set/bool: two
# overlapping requests for the SAME session_id both pin it, and the sweep
# must keep excluding it until BOTH have released, not just whichever
# finishes first. Pinning happens in the SAME _web_sessions_lock-protected
# block as the lookup/creation itself, which is what closes a narrower
# race than last_accessed alone could: without it, a request could look up
# a session, then -- before it ever calls session.send()/send_streaming()
# (which only THEN acquires the session's own lock) -- a concurrent sweep
# could see that same session as idle and not yet pinned, and evict (close)
# it out from under the request about to use it.
_active_web_sessions: Dict[str, int] = {}

# ---------------------------------------------------------
# WEB SERVICE: AUTH + RATE LIMITING
# ---------------------------------------------------------
# Same opt-in posture as the ADK original: --flask defaults to HTTPS on
# 127.0.0.1 (loopback-only, see run_web_service) -- widening HOST beyond
# loopback with no WEBAPIKEY configured makes run_web_service refuse to
# start rather than silently exposing an unauthenticated, model-backed
# chat API to the network.
_web_rate_limit_lock = threading.Lock()
_web_rate_limit_state: Dict[str, List[float]] = {}  # client key -> timestamps within the current window
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
            return False
        timestamps.append(now)
        _web_rate_limit_state[client_key] = timestamps
        return True


def _get_or_create_web_session(existing_session_id: Optional[str], agent_name: str):
    """Resolve a web session id to its ChatSession, PINNING it against the
    idle-eviction sweep below in the same locked step (see
    _active_web_sessions's own comment for why that matters) -- the
    caller MUST call _release_web_session(web_session_id) once it is
    fully done with the returned session, including having called
    session.send()/send_streaming() to completion, or the session can
    never become eligible for eviction again. If existing_session_id is
    missing/unknown, a fresh (isolated -- see ChatSession's own
    docstring) ChatSession is created and registered under a new web
    session id, which is returned alongside it (also pinned)."""
    global _web_sessions_last_swept

    now = time.monotonic()
    evicted: List[tuple] = []
    session = None
    with _web_sessions_lock:
        if now - _web_sessions_last_swept >= _WEB_SESSION_SWEEP_INTERVAL_SECONDS:
            _web_sessions_last_swept = now
            stale_ids = [
                sid for sid, s in _web_sessions.items()
                if sid not in _active_web_sessions
                and now - s.last_accessed >= _WEB_SESSION_IDLE_TIMEOUT_SECONDS
            ]
            evicted = [(sid, _web_sessions.pop(sid)) for sid in stale_ids]
        if existing_session_id:
            session = _web_sessions.get(existing_session_id)
            if session is not None:
                _active_web_sessions[existing_session_id] = _active_web_sessions.get(existing_session_id, 0) + 1

    for stale_id, stale_session in evicted:
        _web_logger.info("Evicting idle web session %s after %.0fs of inactivity.",
                          stale_id, _WEB_SESSION_IDLE_TIMEOUT_SECONDS)
        try:
            stale_session.close()
        except Exception:
            _web_logger.exception("Error closing idle neuro-san session %s during eviction sweep.", stale_id)

    if session is not None:
        return existing_session_id, session

    # Constructed outside the lock -- ChatSession's own __init__ does real
    # I/O (neuro-san session setup, thinking-file creation), which would
    # otherwise serialize EVERY concurrent session creation (even for
    # unrelated users) behind this one lock.
    session = ChatSession(agent_name, isolated=True)
    web_session_id = str(uuid.uuid4())
    with _web_sessions_lock:
        _web_sessions[web_session_id] = session
        _active_web_sessions[web_session_id] = 1
    return web_session_id, session


def _release_web_session(web_session_id: str) -> None:
    """Unpins web_session_id -- see _get_or_create_web_session's own
    docstring for the contract. Also refreshes last_accessed to now: a
    turn that ran right up to (or past) _WEB_SESSION_IDLE_TIMEOUT_SECONDS
    would otherwise still carry its turn-START timestamp (see
    ChatSession.send/send_streaming) the instant it finishes, making it
    look just as idle as a genuinely abandoned session to the very next
    sweep, even though it just finished successfully."""
    with _web_sessions_lock:
        remaining = _active_web_sessions.get(web_session_id, 0) - 1
        if remaining > 0:
            _active_web_sessions[web_session_id] = remaining
        else:
            _active_web_sessions.pop(web_session_id, None)
        session = _web_sessions.get(web_session_id)
        if session is not None:
            session.last_accessed = time.monotonic()


def build_web_app(agent_name: str, https: bool = True):
    """
    Build (but do not run) the Flask REST app for -d/--detached --flask mode.

    Exposes the SAME routes/shapes as the ADK original's build_web_app:
      POST   /chat            {"query": "...", "session_id": "..." (optional),
                               "files": [{"name": "...", "mime_type": "...",
                               "data_base64": "..."}, ...] (optional, up to
                               ATTACHMENT_MAX_FILES entries, each up to
                               ATTACHMENT_MAX_BYTES decoded)}
                               -> {"status": "ok", "session_id": "...",
                                   "query": "...", "response": "...",
                                   "usage": {"prompt_tokens": N,
                                   "completion_tokens": N, "total_tokens": N,
                                   "model": "..."} or null}
                               Attached files are staged to this session's
                               fixed on-disk directory (see
                               _parse_attachments/stage_attachments_to_directory)
                               and that directory's path is appended to the
                               query text as a literal
                               "[ATTACHMENT DIRECTORY: ...]" marker, NOT sent
                               to the LLM as genuine multimodal content --
                               see ATTACHMENT_MAX_FILES's own comment for why.
      POST   /chat/stream      Same request body; response is
                               text/event-stream instead -- a live
                               sequence of `data: {...}\n\n` events
                               shaped like ChatSession.send_streaming's
                               own docstring describes, ending with a
                               {"status": "done", "response": "...",
                               "usage": {...same shape as /chat's above}}
                               event. See that method for why/how.
      POST   /chat/<session_id>/stop  Cancels that session's in-flight
                               /chat/stream turn, if any -> {"status": "ok",
                               "session_id": "...", "stopped": true|false}.
      DELETE /chat/<session_id>  Drops server-side state for that session.
      GET    /artifacts/<name>  "process" or "design" -> {"status": "ok",
                               "name": "...", "data": {...the parsed
                               output/<name>_data.json...}}, or 404 if
                               that pipeline hasn't produced one yet.
      GET    /status           Liveness probe. Unlike the ADK original,
                               does NOT report a model name -- neuro-san
                               can genuinely invoke different models per
                               turn (see "usage.model" above), so there is
                               no single static answer to report here.

    Sessions are tracked both by an explicit "session_id" JSON field (for
    plain REST/CLI clients) and by a cookie (for browser-based clients) --
    whichever is supplied wins; if neither resolves to a known session, a
    new one is created and handed back both ways.

    Every route except /status requires WEBAPIKEY (if configured, via the
    WEBAPIKEY env var -- this project has no properties-file config layer,
    see the module docstring's .env note) via an "Authorization: Bearer
    <key>" or "X-API-Key" header, and is capped at WEBRATELIMITPERMINUTE
    requests/minute per source IP -- see the AUTH + RATE LIMITING block
    above for why.

    CORS is enabled permissively (reflecting whatever Origin the browser
    sends, no credentials involved) -- this is a local sample tool, not a
    multi-tenant production service, and the web client authenticates each
    turn via an explicit session_id in the request body rather than a
    cross-origin cookie, so this doesn't widen the actual exposure beyond
    what WEBAPIKEY/rate-limiting already gate.
    """
    from flask import Flask, request, jsonify, make_response, Response

    web_app = Flask("ProcessArchitectWebServiceNS")
    web_app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    # Rejects an oversized request at the WSGI layer, before Flask reads any
    # of its body -- see MAX_REQUEST_BODY_BYTES's own comment for why this
    # has to happen before request.get_json(), not after.
    web_app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BODY_BYTES

    api_key = os.environ.get("WEBAPIKEY")
    if not api_key:
        display_text(
            "No WEBAPIKEY configured -- the web service is UNAUTHENTICATED. Anyone who can "
            "reach it can create sessions and trigger model calls that may incur cost or "
            "exhaust resources. Set the WEBAPIKEY env var (e.g. in this project's own .env "
            "file) before exposing this beyond localhost.",
            kind="warning",
        )
    rate_limit_per_minute = int(os.environ.get("WEBRATELIMITPERMINUTE", "30"))

    def _api_key_matches(candidate: Optional[str]) -> bool:
        # Constant-time comparison: a naive `==` leaks how many leading
        # characters matched via response-time differences, which is a
        # real (if slow) way to brute-force a shared secret over the
        # network.
        return isinstance(candidate, str) and hmac.compare_digest(candidate, api_key)

    @web_app.after_request
    def _add_cors_headers(response):
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

        web_session_id = None
        try:
            web_session_id, session = _get_or_create_web_session(session_id, agent_name)
            response_text = session.send(query.strip(), files=files)
        except Exception:
            _web_logger.exception("Web chat error")
            return jsonify({
                "status": "error",
                "error": "An internal error has occurred.",
            }), 500
        finally:
            # Unpins the session resolved above (see
            # _get_or_create_web_session's own docstring for the
            # pin/release contract) regardless of how this turn ended --
            # a leaked pin would make the session permanently ineligible
            # for the idle-eviction sweep.
            if web_session_id is not None:
                _release_web_session(web_session_id)

        resp = make_response(jsonify({
            "status": "ok",
            "session_id": web_session_id,
            "query": query,
            "response": response_text or "",
            "usage": session.last_usage,
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
        text/event-stream -- a live sequence of progress/delta/done
        events (see ChatSession.send_streaming's own docstring for their
        exact shape) instead of one blocking JSON body sent only once
        the whole turn is done. Added so a UI can show the agent network
        actually working turn-by-turn rather than a long silent wait;
        POST /chat is unchanged and still the right choice for any
        caller that just wants the final text (scripts, curl, server-to-
        server callers).
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
        # Resolved up front (not inside the generator below) so the
        # session id is known -- and its cookie set -- before the
        # streaming response even starts, exactly like POST /chat.
        web_session_id, session = _get_or_create_web_session(session_id, agent_name)

        def generate():
            try:
                try:
                    for update in session.send_streaming(query.strip(), files=files):
                        yield f"data: {json.dumps({**update, 'session_id': web_session_id})}\n\n"
                except Exception:
                    _web_logger.exception("Web chat stream error")
                    error_event = {
                        "status": "error", "session_id": web_session_id, "error": "An internal error has occurred.",
                    }
                    yield f"data: {json.dumps(error_event)}\n\n"
            finally:
                # Unpins the session resolved above (see
                # _get_or_create_web_session's own docstring for the
                # pin/release contract) whenever this generator ends --
                # normal completion, the in-band error event above, or the
                # client disconnecting mid-stream (GeneratorExit unwinds
                # through this finally the same as any other exception).
                _release_web_session(web_session_id)

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
        it is just burning tokens for nothing. Reaches directly into the
        underlying DirectAgentSession's own AsyncioExecutor and cancels
        its currently-submitted tasks -- a REAL cancellation of whatever
        model call is actually in flight, not merely the client giving up
        on the connection (which alone would not stop the real token cost
        from continuing to accrue in the background). See
        ChatSession.send_streaming's own docstring for the "stopped" event
        this produces on the SSE side.

        Always 200 -- "nothing was running" and "it was running and is
        now cancelled" are both unexceptional outcomes, not errors, for a
        caller that just wants "make sure nothing is still running".
        """
        with _web_sessions_lock:
            session = _web_sessions.get(session_id)
        if session is None:
            return jsonify({"status": "ok", "session_id": session_id, "stopped": False})

        invocation_context = getattr(session.session, "invocation_context", None)
        if invocation_context is None:
            # No turn has ever started on this session (or the session was
            # already closed) -- nothing in flight to cancel.
            return jsonify({"status": "ok", "session_id": session_id, "stopped": False})

        try:
            invocation_context.get_asyncio_executor().cancel_current_tasks(timeout=5.0)
            stopped = True
        except RuntimeError:
            # "Loop must be running to cancel remaining tasks" -- the
            # executor's own loop isn't active right now, which just means
            # there was nothing in flight to stop (e.g. between turns).
            stopped = False
        return jsonify({"status": "ok", "session_id": session_id, "stopped": stopped})

    @web_app.route("/chat/<session_id>", methods=["DELETE"])
    def chat_reset(session_id):
        with _web_sessions_lock:
            session = _web_sessions.pop(session_id, None)
        existed = session is not None
        # Popping _web_sessions only forgets the id -> ChatSession mapping;
        # the underlying neuro-san DirectAgentSession holds its own
        # server-side resources (invocation context) until explicitly
        # closed, or it leaks for the life of the process across repeated
        # create/delete cycles -- same reason ChatSession.close() also
        # cleans up any attachment-staging directory still on disk.
        if existed:
            try:
                session.close()
            except Exception:
                _web_logger.exception("Error closing neuro-san session %s", session_id)
        return jsonify({"status": "ok", "session_id": session_id, "cleared": existed})

    @web_app.route("/artifacts/<name>", methods=["GET"])
    def artifact(name):
        """
        Read-only access to this project's own output/process_data.json or
        output/design_data.json, for the web client's "Process / Design"
        tab -- a hierarchical viewer of whichever pipeline's current
        artifact. The ADK original's build_web_app has an identical
        route, and both keep these files at the identical relative path,
        so the client's fetch logic doesn't need to know which backend
        it's talking to.

        Deliberately a raw file read, NOT the existing
        load_master_process_json/load_master_design_json CodedTool
        helpers -- those silently fall back to a blank template when the
        file is missing (useful for a pipeline about to populate one, not
        for a debugging viewer that needs to tell "genuinely not generated
        yet" apart from "here's an empty template"), so this reports a
        real 404 instead.
        """
        filenames = {"process": "process_data.json", "design": "design_data.json"}
        filename = filenames.get(name)
        if filename is None:
            return jsonify({
                "status": "error",
                "error": f"Unknown artifact '{name}' -- use 'process' or 'design'.",
            }), 400

        path = os.path.join(_PROJECT_ROOT, "output", filename)
        if not os.path.exists(path):
            return jsonify({
                "status": "error",
                "error": f"No {filename} found yet -- run the {name} pipeline at least once, then try again.",
            }), 404

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            _web_logger.exception("Failed to read/parse %s", filename)
            return jsonify({
                "status": "error",
                "error": f"Could not read {filename} -- see server logs.",
            }), 500

        return jsonify({"status": "ok", "name": name, "data": data})

    @web_app.route("/status", methods=["GET"])
    def status():
        return jsonify({"status": "live"})

    return web_app


def run_web_service(agent_name: str, port: Optional[int], use_https: bool) -> None:
    """Build and serve the Flask REST app (-d/--detached --flask) until
    interrupted."""
    host = os.environ.get("HOST", "127.0.0.1")

    is_loopback = host in ("127.0.0.1", "localhost", "::1")
    api_key_configured = bool(os.environ.get("WEBAPIKEY"))
    allow_insecure = os.environ.get("ALLOWINSECUREWEBSERVICE", "").strip().lower() in ("1", "true", "yes", "on")
    if not is_loopback and not api_key_configured and not allow_insecure:
        display_text(
            f"Refusing to start: HOST={host!r} is reachable beyond localhost and no WEBAPIKEY "
            "is configured, which would expose the chat API (and the model calls/cost behind "
            "it) to any client that can reach this port. Fix one of: set the WEBAPIKEY env "
            "var; set HOST=127.0.0.1 to restrict this to local access only; or set "
            "ALLOWINSECUREWEBSERVICE=true to explicitly accept the risk.",
            kind="error",
        )
        sys.exit(1)

    web_app = build_web_app(agent_name, https=use_https)

    listen_port = port if port is not None else (443 if use_https else 8080)

    ssl_context = None
    if use_https:
        cert_file = os.environ.get("SSLCERTFILE")
        key_file = os.environ.get("SSLKEYFILE")
        if cert_file and key_file:
            ssl_context = (cert_file, key_file)
        else:
            try:
                import OpenSSL  # noqa: F401
                ssl_context = "adhoc"
                display_text(
                    "No SSLCERTFILE/SSLKEYFILE configured -- serving HTTPS with an ad-hoc, "
                    "self-signed certificate. Do not use this in production.",
                    kind="warning",
                )
            except ImportError:
                display_text(
                    "HTTPS requested but no SSLCERTFILE/SSLKEYFILE are configured and "
                    "'pyOpenSSL' is not installed (needed to generate an ad-hoc certificate). "
                    "Install pyOpenSSL, set SSLCERTFILE/SSLKEYFILE in the environment, or "
                    "rerun with --http.",
                    kind="error",
                )
                sys.exit(1)

    # SIGTERM (a `kill <pid>`, a container orchestrator's stop signal, etc.)
    # has no handler by default -- Python's default disposition for it is
    # immediate termination with no exception raised, so without this the
    # server would just vanish mid-request with no log line and no message
    # on the terminal. SIGINT (Ctrl+C) is deliberately NOT handled here --
    # it's already turned into a clean KeyboardInterrupt by the interpreter,
    # which the __main__ block at the bottom of this file catches.
    def _handle_sigterm(signum, frame):  # noqa: ARG001 -- signal handler signature
        _web_logger.warning("Received SIGTERM -- shutting down.")
        display_text("\nReceived SIGTERM -- shutting down.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    scheme = "https" if use_https else "http"
    display_text(f"Starting Process Architect REST API on {scheme}://{host}:{listen_port} (POST /chat)...")
    web_app.run(host=host, port=listen_port, ssl_context=ssl_context, threaded=True, debug=False)


def run_detached(port: Optional[int], use_http: bool) -> None:
    """-d/--detached: launches neuro-san's own server + nsflow UI (`ns
    run`) -- see module docstring for why this doesn't reimplement the
    ADK original's Flask layer."""
    display_text(
        "-d/--detached runs this project's native serving layer (`ns run`) -- neuro-san's own "
        "HTTP server + nsflow chat UI -- instead of the ADK original's custom Flask REST API. "
        "See README.md's 'Deliberate simplifications' for why that layer was not ported.",
        kind="warning",
    )
    args = ["ns", "run"]
    if port is not None:
        args += ["--server-http-port", str(port)] if use_http else ["--nsflow-port", str(port)]
    display_text(f"Starting: {' '.join(args)}")
    subprocess.run(args, check=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process Architect Orchestrator (neuro-san port)")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-f", "--file",
        dest="file", type=str, required=False,
        help="Process file instructions from a text file (one instruction per line). If not "
             "provided, starts in interactive chat mode.",
    )
    mode_group.add_argument(
        "-i", "--input",
        dest="input", type=str, required=False,
        help='Process a single prompt, print the response, and exit (no interactive loop). '
             'E.g.: -i "tell me what this process is about"',
    )
    mode_group.add_argument(
        "-d", "--detached",
        dest="detached", action="store_true",
        help="Run this project's native serving layer (`ns run`: HTTP server + nsflow UI) instead "
             "of the interactive/file/single-prompt CLI. Add --flask to run this project's own "
             "Flask REST API (same contract as the ADK original) instead. See --http and --port.",
    )
    parser.add_argument(
        "--flask", dest="flask", action="store_true",
        help="With --detached, run this project's own Flask REST API (POST /chat, "
             "DELETE /chat/<session_id>, GET /status -- same contract as the ADK original's "
             "-d mode) instead of `ns run`. See samples/WebClient/ProcessEngineering for a "
             "browser client that talks to this. Only valid with --detached.",
    )
    parser.add_argument(
        "--http", dest="http", action="store_true",
        help="With --detached --flask, serve plain HTTP on port 8080 instead of the default "
             "HTTPS on port 443 (matching the ADK original's own --http). With plain "
             "--detached (no --flask), --port overrides the agent server's HTTP port instead "
             "of the nsflow UI's port.",
    )
    parser.add_argument(
        "-p", "--port",
        dest="port", type=int, required=False,
        help="With --detached --flask, override the listening port (default: 443 for HTTPS, "
             "8080 for --http). With plain --detached (no --flask), override the listening "
             "port (nsflow UI by default; the agent server itself with --http).",
    )
    parser.add_argument(
        "--agent", dest="agent", type=str, default=AGENT_NAME_DEFAULT,
        help=f"Which served network to talk to (default: {AGENT_NAME_DEFAULT}, the top-level "
             "front-man). Pass any other registries/*.hocon network name to talk to it directly.",
    )
    return parser


async def run_cli() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.detached and (args.http or args.port is not None or args.flask):
        parser.error("--flask, --http, and --port only apply with -d/--detached.")

    if args.detached:
        if args.flask:
            run_web_service(agent_name=args.agent, port=args.port, use_https=not args.http)
        else:
            run_detached(port=args.port, use_http=args.http)
        return

    display_text(
        f"Process Architect Orchestrator (local mode, agent={args.agent})\n",
        kind="info",
    )

    if args.file:
        await process_file(args.file, args.agent)
        return

    if args.input:
        await process_single_prompt(args.input, args.agent)
        return

    display_text("Starting Process Architect Orchestrator in local chat mode...")
    await start_local_chat(args.agent)


if __name__ == "__main__":
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        # Ctrl+C in ANY mode -- interactive chat, -f/-i, or -d/--flask's
        # blocking Flask dev server loop. asyncio.run()'s own Runner
        # cancels the in-flight task on SIGINT and re-raises that as
        # KeyboardInterrupt once run_until_complete unwinds (see cpython's
        # asyncio/runners.py) -- left uncaught, that surfaces as a raw
        # CancelledError-then-KeyboardInterrupt traceback instead of a
        # clean exit, and a second Ctrl+C while that traceback is still
        # unwinding has also been observed to leave `uv run`'s own process
        # supervision confused (ESRCH trying to signal an already-exited
        # child). Exiting cleanly on the first Ctrl+C avoids needing a
        # second one at all.
        display_text("\nInterrupted -- shutting down.")
        sys.exit(0)
