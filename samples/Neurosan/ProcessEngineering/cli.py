#!/usr/bin/env python
"""Reinstates the ADK port's CLI surface
(samples/GCP/ProcessEngineering/process_agents/common/agent.py) against this
neuro-san port, talking to the top-level front-man (`process_architect` by
default) via neuro-san's own DIRECT (in-process) agent session -- no server
needs to be running for the default interactive/-i/-f modes.

Same flags as the ADK port:
    (no flags)         interactive chat REPL
    -i/--input TEXT    send one prompt, print the response, exit
    -f/--file PATH     submit each line of a file as a turn, in order
    -d/--detached      run this project's own server/UI (see below)
    --flask            with -d, run the Flask REST API below instead of `ns run`
    --http / -p/--port modify -d/--detached's listening port
    -s/--server HOST   with -d --flask, override the HOST env var the Flask API binds to

Logging mirrors the ADK port's own pipeline_*.log exactly: standard
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
refusal to start) as the ADK port's own -d mode -- see build_web_app's
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
import glob
import hashlib
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
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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

# --- Dynamic Model Lookup / Environment Fallback ---
# Automatically resolve and configure LLM provider settings dynamically based on runtime environment availability.
if not any(os.environ.get(k) for k in ["AZURE_OPENAI_ENDPOINT", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"]):
    os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    _target_ollama_model = os.environ.get("OLLAMA_MODEL") or os.environ.get("MODEL_NAME") or "llama3.2"
    os.environ.setdefault("DEFAULT_LLM_MODEL", f"ollama_chat/{_target_ollama_model}")
    os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "http://127.0.0.1:11434")
    os.environ.setdefault("OPENAI_API_KEY", "ollama-local-placeholder")

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
# *.docx, ...), this is this project's answer to the ADK port's own
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
# happens, not after. Mirrors the ADK port's own agent.py logging
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
from neuro_san.internals.graph.persistence.agent_network_restorer import AgentNetworkRestorer  # noqa: E402
from neuro_san.internals.journals.origination import Origination  # noqa: E402
from neuro_san.message.processors.message_processor import MessageProcessor  # noqa: E402
from neuro_san.message.types.chat_message_type import ChatMessageType  # noqa: E402
from neuro_san.message.types.chat_message_type_util import ChatMessageTypeUtil  # noqa: E402

from process_interface import paths  # noqa: E402
from process_interface.ingestion.extractors import stage_attachments_to_directory  # noqa: E402
from process_interface.run_lock import (  # noqa: E402
    force_clear_pipeline_lock,
    peek_pipeline_lock,
    release_pipeline_lock,
    stop_pipeline_lock_heartbeat,
)
from process_interface.session_purge import purge_session, start_session_purge_thread  # noqa: E402
from process_interface.session_logs import (  # noqa: E402
    get_session_log_entries,
    install_session_log_handler,
    record_session_log,
)
from coded_tools.common.artifact_downloads import (  # noqa: E402
    cloudarch_exists,
    copy_artifact_to_destination,
    list_output_documents,
    portfolio_backlog_workbook_exists,
    safe_output_file_path,
)
from process_interface.iac.generation import IAC_ZIP_FILENAME, iac_zip_exists  # noqa: E402
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY  # noqa: E402
from process_interface.agentic_web import (  # noqa: E402
    get_agent_card,
    get_agent_manifest,
    get_all_agent_cards,
    get_all_workflows,
    get_artifact_contract,
    get_workflow,
    list_agent_summaries,
    list_all_artifact_contracts,
    search_capabilities,
    wrap_artifact_envelope,
)
import network_publishing  # noqa: E402

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
# CONFIRMED, same limitation, checked directly against the installed
# neuro-san (0.7.7) and google-adk (2.14.0) packages' own source: a
# CodedTool's own return value is force-stringified in
# abstract_class_activation.py BEFORE any message-type/mime_data handling
# could ever apply, so there is no path -- unlike the ADK port's own
# _content_parts_for_turn/computer_use_tool.py-style FunctionResponsePart
# mechanism -- for an attached or imported image to reach this port's LLM
# as genuine vision input. What DID change: an attached image used to
# vanish ENTIRELY (load_directory_context's own "unsupported file type"
# skip path) once staged into the attachment directory above; it now
# contributes its OCR'd visible text instead (process_toolkit.ingestion.
# extractors._extract_image_file), the same way every other attached
# document already does. Text-only, not a description of the image's
# visual/structural layout -- see that extractor's own docstring.
#
# Attachments are staged to a FIXED, per-ChatSession on-disk directory
# (see ChatSession._attachments_directory/_ingest_attachments below) via
# stage_attachments_to_directory, and that directory's path is appended
# directly to the user's own message text as a literal
# "[ATTACHMENT DIRECTORY: <path>] (attached file(s): <names>)" marker (see
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
#
# The marker ALSO includes the original filename(s), not just the staging
# directory's own (randomly-named) path -- confirmed as a real production
# bug without this: process_architect.hocon's own router instructions tell
# it an attachment "literally named cloudarch_drawio.xml" is always a
# cloud-architecture-diagram signal, but the router never actually SAW
# that filename anywhere in its own input (only the opaque temp directory
# path) -- it had no way to apply its own rule, only to guess from prose
# wording, and that guessing failed in practice (e.g. "review this
# architecture and save for future use" was misrouted to Process_Import_
# Agent, not even the design-document domain the word-based fallback would
# predict). Including the real filename(s) here lets the router's own
# literal-filename check actually run as written, deterministically,
# instead of depending on the model's prose-based intuition every time.
ATTACHMENT_DIRECTORY_MARKER_TEMPLATE = "[ATTACHMENT DIRECTORY: {path}] (attached file(s): {filenames})"
_WEB_CHAT_STATE_FILENAME = ".web_chat_state.json"
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
    convention as the ADK port."""
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


def _append_attachment_directory_marker(
    text: str, directory: Optional[str], filenames: Optional[List[str]] = None,
) -> str:
    """Appends an "[ATTACHMENT DIRECTORY: <path>] (attached file(s): <names>)"
    marker (see ATTACHMENT_DIRECTORY_MARKER_TEMPLATE's own comment for why
    this is a literal text marker rather than a sly_data-only signal, and
    why the filenames are included, not just the path) onto the user's
    own message text, so the agent network's existing "request explicitly
    names a directory" handling picks it up exactly like a user who typed
    a path themselves. Returns `text` unchanged when `directory` is None
    (no attachment this turn)."""
    if not directory:
        return text
    marker = ATTACHMENT_DIRECTORY_MARKER_TEMPLATE.format(
        path=directory, filenames=", ".join(filenames) if filenames else "(unknown)",
    )
    return f"{text}\n\n{marker}" if text else marker


def _extract_usage(token_accounting: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Maps neuro-san's own token_accounting dict (see
    TokenAccountingMessageProcessor/LangChainTokenCounter in the installed
    neuro_san package -- "models" is a {provider_class: {model_name:
    {total_tokens, prompt_tokens, completion_tokens, ...}}} nested dict)
    onto the {prompt_tokens, completion_tokens, total_tokens, model} shape
    the web client's Token Usage tab expects -- the exact same keys the ADK
    port's own usage field uses, so the client doesn't need to know
    which backend it's talking to.

    Unlike the ADK port (one single statically-configured model,
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
    token = None
    if isinstance(sly_data, dict):
        sly_data.pop("_current_turn_id", None)
        sly_data.pop("_pipeline_lock_turn_id", None)
        token = sly_data.pop(PIPELINE_LOCK_TOKEN_KEY, None)
    if token:
        _web_logger.debug(
            "Turn ended with pipeline lock token %s still held in sly_data -- releasing it defensively.", token,
        )
        stop_pipeline_lock_heartbeat(token)
        release_pipeline_lock(token)
    # Defense-in-depth: unconditionally clear any leftover lock for this session
    held = peek_pipeline_lock()
    if held is not None:
        _web_logger.debug(
            "Turn ended with pipeline lock still held in memory for session (%s) -- force clearing defensively.", held,
        )
        force_clear_pipeline_lock()


def _dedupe_doubled_answer(text: Optional[str]) -> Optional[str]:
    """Defensive safety net for an occasionally-observed response quirk:
    the final compiled answer arrives as the exact same block of text
    repeated twice back-to-back with NO separator at all between the two
    copies -- confirmed directly against a real transcript (e.g. "...and
    performance targets (NFR-001 and NFR-005).The following coverage gap
    was identified..." with zero whitespace at the join). That specific
    signature -- byte-for-byte identical halves, zero separator -- only
    happens when something concatenated the same string with itself; a
    model genuinely restating its own answer would have SOME separator
    (a sentence break, a "to summarize", at minimum a newline). Neither
    this project's own ChatSession nor neuro-san's own BasicMessage
    Processor/AnswerMessageProcessor ever concatenate successive answer
    chunks (AnswerMessageProcessor.process_message does a plain `self.
    answer = text` overwrite, confirmed directly against its source) --
    so this already arrives doubled from upstream of this client. Rather
    than chase a root cause across a third-party streaming pipeline,
    detect and collapse the exact-doubled shape before it ever reaches
    the user -- a confusing repeated answer is strictly worse than this
    collapsing a rare, legitimate exact-duplicate-content answer (which
    would be a bizarre thing for an agent to say unprompted anyway)."""
    if not text:
        return text
    length = len(text)
    if length < 2 or length % 2 != 0:
        return text
    half = length // 2
    first, second = text[:half], text[half:]
    if first and first == second:
        return first
    return text


# Confirmed directly against a real run: neuro-san's own run_context_
# runnable.py catches a model-provider exception and returns it as a
# normal chat response string shaped "Error from <agent>: Agent stopped
# due to exception Error calling model '<model>' (RESOURCE_EXHAUSTED):
# 402 RESOURCE_EXHAUSTED. {'error': {... 'message': 'Your prepayment
# credits are depleted...'}}" -- a raw, nested, nearly-unreadable
# exception repr/JSON blob, not a raised Python exception, so neither
# this file's own `except Exception` turn-handlers nor the web routes'
# 500-error paths ever see it; it looks exactly like a normal answer to
# every caller downstream. The failure itself is real and the fix is
# always the same (go top up credits) -- there is nothing conversational
# an agent could usefully add on retry, so this is worth recognizing and
# replacing with one clear, actionable sentence instead of relaying the
# raw blob as if it were the agent's own reply.
_LLM_CREDITS_EXHAUSTED_MARKERS = ("prepayment credits are depleted",)


def _friendly_llm_failure_message(text: Optional[str]) -> Optional[str]:
    """Returns a clean, actionable message in place of a known,
    not-recoverable-by-retrying LLM-provider failure (billing/prepaid
    credits exhausted) buried inside one of neuro-san's own "Agent
    stopped due to exception ..." response strings. Returns None for
    anything else (a genuine answer, or a different kind of failure) so
    the caller falls back to displaying the original text unchanged --
    deliberately narrow (one confirmed, specific failure signature),
    not a general "this looks like an error" heuristic, which would risk
    mangling a legitimate answer that happens to mention one of these
    words in passing (e.g. a question about cloud resource exhaustion as
    an NFR topic)."""
    if not text or "Agent stopped due to exception" not in text:
        return None
    if any(marker in text for marker in _LLM_CREDITS_EXHAUSTED_MARKERS) or (
        "RESOURCE_EXHAUSTED" in text and "402" in text
    ):
        return (
            "The LLM provider account has run out of prepaid credits, so this turn could not "
            "complete. Top up credits at https://ai.studio/projects, then try again -- see "
            "https://ai.google.dev/gemini-api/docs/billing#prepay for details."
        )
    return None


class ChatSession:
    """One underlying neuro-san direct session against an agent network,
    plus the request/response state (chat_context, sly_data) that must be
    threaded from one turn to the next for the conversation to actually
    continue rather than looking like a fresh request every time. Mirrors
    the role of the ADK port's Runner+session_id pair -- "clear"
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
        self._web_session_id: Optional[str] = None
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

    def _ingest_attachments(
        self, files: Optional[List[Dict[str, Any]]],
    ) -> Optional[Tuple[str, List[str]]]:
        """
        Stages this turn's attached files (see _parse_attachments) into
        this session's FIXED self._attachments_directory
        (process_toolkit.ingestion.extractors.stage_attachments_to_directory
        clears any files already there first, so a later turn's set
        never mixes with an earlier one left behind in the same path).

        Returns (directory path, [original filenames]) if files were
        staged THIS turn, or None if `files` was empty. The caller
        (send()/send_streaming()) uses a non-None return to append an
        "[ATTACHMENT DIRECTORY: <path>] (attached file(s): <names>)"
        marker (see ATTACHMENT_DIRECTORY_MARKER_TEMPLATE) directly onto
        the user's own message text -- a literal, visible string every
        network's existing "request explicitly names a directory"
        handling already knows how to act on, rather than a side channel
        (sly_data plus a dedicated CodedTool) an agent has to remember to
        separately call before anything else, every single turn. The
        filenames are included alongside the path (not just the path
        alone) so the router's own ATTACHED-FILE OVERRIDE rule -- "an
        attachment literally named cloudarch_drawio.xml ... is always a
        signal" -- has something real to check; without them, the router
        only ever saw an opaque staging-directory path and had to guess
        the file's identity from prose alone, which failed in practice
        (confirmed: a real misroute to Process_Import_Agent for an
        attached cloud architecture diagram).

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
        return result["directory"], result["files_written"]

    def close(self) -> None:
        """Releases this session's resources: the attachment-staging
        directory, then the underlying neuro-san session. Called from
        both the web service's idle-eviction sweep and its DELETE
        /chat/<session_id> route -- centralized here so neither call
        site can forget the staging-directory half of cleanup."""
        self._cleanup_attachments_directory()
        self.session.close()

    def persist_web_state(self) -> None:
        """Atomically persist this web conversation for restart recovery."""
        web_session_id = getattr(self, "_web_session_id", None)
        if not web_session_id:
            return
        payload = {
            "version": 1,
            "agent_name": self.agent_name,
            "chat_context": self.chat_context,
            "sly_data": self.sly_data,
        }
        try:
            serialized = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("The neuro-san conversation state is not JSON serializable.") from exc

        with paths.use_session(web_session_id):
            state_path = paths.output_path(_WEB_CHAT_STATE_FILENAME)
            temporary_path = f"{state_path}.{uuid.uuid4().hex}.tmp"
            try:
                with open(temporary_path, "w", encoding="utf-8") as state_file:
                    state_file.write(serialized)
                    state_file.flush()
                    os.fsync(state_file.fileno())
                os.replace(temporary_path, state_path)
            finally:
                try:
                    os.remove(temporary_path)
                except FileNotFoundError:
                    pass

    def send(self, text: str, files: Optional[List[Dict[str, Any]]] = None) -> str:
        with self._lock:
            turn_started = time.monotonic()
            turn_id = uuid.uuid4().hex
            self.last_accessed = turn_started
            if self.sly_data is None:
                self.sly_data = {}
            self.sly_data["_current_turn_id"] = turn_id
            try:
                staged = self._ingest_attachments(files)
                attachments_directory, attachment_filenames = staged if staged else (None, None)
                effective_text = _append_attachment_directory_marker(
                    text, attachments_directory, attachment_filenames,
                )
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
                self.persist_web_state()

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

                raw_response = _dedupe_doubled_answer(state.get("last_chat_response")) or ""
                return _friendly_llm_failure_message(raw_response) or raw_response
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
            turn_id = uuid.uuid4().hex
            self.last_accessed = turn_started
            _web_logger.info("send_streaming: turn started (turn_id=%s, text_len=%d, attachments=%d)", turn_id, len(text), len(files) if files else 0)
            if self.sly_data is None:
                self.sly_data = {}
            self.sly_data["_current_turn_id"] = turn_id
            staged = self._ingest_attachments(files)
            attachments_directory, attachment_filenames = staged if staged else (None, None)
            effective_text = _append_attachment_directory_marker(
                text, attachments_directory, attachment_filenames,
            )
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
                        compiled_answer = _friendly_llm_failure_message(compiled_answer) or compiled_answer
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
                        _web_logger.debug("send_streaming progress [%s]: %s", origin_str, preview)
                        yield {"status": "progress", "origin": origin_str, "text": preview}
                except asyncio.CancelledError:
                    if _trace_logger.isEnabledFor(logging.INFO):
                        _trace_logger.info(
                            "Chat stream turn stopped: duration=%.2fs", time.monotonic() - turn_started,
                        )
                    _web_logger.info("send_streaming: turn stopped after %.2fs", time.monotonic() - turn_started)
                    yield {"status": "stopped", "response": _dedupe_doubled_answer(last_compiled_answer) or ""}
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
                self.persist_web_state()

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
                _web_logger.info(
                    "send_streaming: turn completed in %.2fs (usage=%s)",
                    time.monotonic() - turn_started, self.last_usage,
                )

                yield {
                    "status": "done",
                    "response": _dedupe_doubled_answer(last_compiled_answer) or "",
                    "usage": self.last_usage,
                }
            finally:
                if self.sly_data is None or PIPELINE_LOCK_TOKEN_KEY not in self.sly_data:
                    try:
                        proc_sly = processor.get_sly_data()
                        if proc_sly and PIPELINE_LOCK_TOKEN_KEY in proc_sly:
                            if self.sly_data is not None:
                                self.sly_data.update(proc_sly)
                            else:
                                self.sly_data = proc_sly.copy()
                    except Exception:
                        pass
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
    -- matching the ADK port's own file-mode-only echo.
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
    if lowered in ("list", "list documents", "ls"):
        _display_output_document_listing()
        return False
    if lowered == "download" or lowered.startswith("download "):
        _handle_download_control_line(line)
        return False

    if echo_input:
        display_text(f"[user-file]: {line}")
    try:
        response = await asyncio.to_thread(session_holder[0].send, line)
        display_text(f"[ArchitectBot]: {response or '[No final response]'}")
    except Exception as e:
        display_text(f"An error occurred: {e}", kind="error")
    return False


def _display_output_document_listing() -> None:
    """"list"/"ls" control line -- shows every generated .docx plus the
    cloud architecture diagram (if either exists), so "download <name>"
    has something concrete to copy from without the user having to go
    look inside output/ themselves."""
    lines: List[str] = []
    for doc in list_output_documents():
        lines.append(f"  {doc['filename']}  ({doc['size_bytes']:,} bytes, modified {doc['modified']})")
    if cloudarch_exists():
        cloudarch_path = os.path.join(paths.output_dir(), "cloudarch_drawio.xml")
        stat = os.stat(cloudarch_path)
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        lines.append(f"  cloudarch_drawio.xml  ({stat.st_size:,} bytes, modified {modified})")
    if portfolio_backlog_workbook_exists():
        backlog_path = os.path.join(paths.output_dir(), "portfolio_backlog.xlsx")
        stat = os.stat(backlog_path)
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        lines.append(f"  portfolio_backlog.xlsx  ({stat.st_size:,} bytes, modified {modified})")
    if iac_zip_exists():
        iac_path = os.path.join(paths.output_dir(), IAC_ZIP_FILENAME)
        stat = os.stat(iac_path)
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        lines.append(f"  {IAC_ZIP_FILENAME}  ({stat.st_size:,} bytes, modified {modified})")
    if lines:
        display_text("[Action]: Generated documents in output/:\n" + "\n".join(lines))
    else:
        display_text("[Action]: No generated documents yet.")


def _handle_download_control_line(line: str) -> None:
    """"download <filename> [destination]" control line -- a plain local
    file copy, since the interactive/-f CLI modes already run in-process
    against this project's own filesystem (no server round trip needed,
    unlike the web client's own download buttons, which DO need the
    /artifacts/.../download Flask routes below since a browser has no
    direct filesystem access). `filename` is whatever "list" just showed
    (a generated .docx, or "cloudarch_drawio.xml"); `destination`
    defaults to the current working directory. Existing folders and
    folder paths without a filename extension are created as needed; a
    destination with a filename extension is treated as a full target
    file path."""
    parts = line.split(maxsplit=2)
    if len(parts) < 2:
        display_text("Usage: download <filename> [destination]", kind="error")
        return
    filename = parts[1]
    destination = os.path.expanduser(parts[2]) if len(parts) > 2 else "."

    try:
        dest_path = copy_artifact_to_destination(filename, destination)
        display_text(f"[Action]: Downloaded '{os.path.basename(dest_path)}' to {dest_path}")
    except (ValueError, OSError) as e:
        display_text(f"Could not copy '{filename}' to '{destination}': {e}", kind="error")


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
# Deliberately the SAME REST contract as the ADK port's own Flask web
# service (samples/GCP/ProcessEngineering/process_agents/common/agent.py's
# build_web_app/run_web_service) -- same routes, same request/response JSON
# shapes, same auth header conventions, same cookie name -- so a single web
# client (see samples/WebClient/ProcessEngineering) can talk to EITHER
# backend interchangeably. Plain -d/--detached (no --flask) still launches
# neuro-san's own `ns run` server/UI unchanged -- --flask selects this REST
# layer INSTEAD, for parity with the ADK port, not as a replacement.
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

def _sso_allowed_redirect_origins() -> frozenset:
    """Opt-in allowlist for the post-SSO-login redirect destination
    (?redirect_uri= on /auth/login) when the web client lives on a
    different origin than this backend -- see _safe_client_return's own
    docstring for why an unvalidated absolute URL here is a real
    vulnerability. Empty by default (same-origin relative paths only);
    set SSO_ALLOWED_REDIRECT_ORIGINS to a comma-separated list of trusted
    origins (e.g. "https://my-webclient.example") to allow the web
    client's own cross-origin bridge redirect to work. Read fresh on
    every call (cheap, rarely called) rather than once at import time, so
    it can actually be exercised/overridden in tests without a module reload.
    """
    return frozenset(
        o.strip().rstrip("/") for o in os.environ.get("SSO_ALLOWED_REDIRECT_ORIGINS", "").split(",") if o.strip()
    )

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

# Each web session's own output/<session_id>/ directory (see
# process_toolkit.paths' own use_session() docstring) is swept by a
# background thread for as long as -d --flask is running -- a directory
# whose own SESSION_META_FILENAME hasn't been touched in SESSIONMAXAGEDAYS
# is removed, unless _active_web_sessions (above) says a request is
# currently in flight for it. Same naming convention as every other
# web-service env var here (WEBAPIKEY, WEBRATELIMITPERMINUTE, ...).
_SESSION_MAX_AGE_SECONDS = float(os.environ.get("SESSIONMAXAGEDAYS", "3")) * 86400.0
_SESSION_PURGE_INTERVAL_SECONDS = float(os.environ.get("SESSIONPURGEINTERVALSECONDS", "3600"))

# ---------------------------------------------------------
# WEB SERVICE: AUTH + RATE LIMITING
# ---------------------------------------------------------
# Same opt-in posture as the ADK port: --flask defaults to HTTPS on
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


def _load_persisted_web_chat_state(session_id: str, agent_name: str) -> Optional[Dict[str, Any]]:
    try:
        paths.sanitize_session_id(session_id)
    except ValueError:
        return None

    with paths.use_session(session_id):
        state_path = paths.output_path(_WEB_CHAT_STATE_FILENAME)
        if not os.path.isfile(state_path):
            return None
        try:
            with open(state_path, "r", encoding="utf-8") as state_file:
                payload = json.load(state_file)
        except (OSError, json.JSONDecodeError) as exc:
            _web_logger.exception("Could not read persisted chat state for session %s.", session_id)
            raise RuntimeError("The saved conversation state could not be loaded.") from exc

    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("agent_name") != agent_name
    ):
        raise RuntimeError("The saved conversation state is invalid or belongs to another agent.")
    if payload.get("chat_context") is not None and not isinstance(payload["chat_context"], dict):
        raise RuntimeError("The saved conversation context is invalid.")
    if payload.get("sly_data") is not None and not isinstance(payload["sly_data"], dict):
        raise RuntimeError("The saved conversation data is invalid.")
    return payload


def _configure_persisted_web_session(session: ChatSession, session_id: str, payload: Optional[Dict[str, Any]]) -> None:
    session._web_session_id = session_id
    if payload is not None:
        session.chat_context = payload.get("chat_context")
        session.sly_data = payload.get("sly_data")


def _get_or_create_web_session(existing_session_id: Optional[str], agent_name: str):
    """Resolve a web session id to its ChatSession, PINNING it against the
    idle-eviction sweep below in the same locked step (see
    _active_web_sessions's own comment for why that matters) -- the
    caller MUST call _release_web_session(web_session_id) once it is
    fully done with the returned session, including having called
    session.send()/send_streaming() to completion, or the session can
    never become eligible for eviction again. If existing_session_id is
    missing, a fresh (isolated -- see ChatSession's own docstring)
    ChatSession is created under a new id. For an unknown but valid
    requested id, a fresh session reuses that id so the client remains
    pinned to its selected conversation. The returned session is pinned."""
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

    if existing_session_id:
        saved_state = _load_persisted_web_chat_state(existing_session_id, agent_name)
        if saved_state is not None:
            session = ChatSession(agent_name, isolated=True)
            _configure_persisted_web_session(session, existing_session_id, saved_state)
            with _web_sessions_lock:
                winner = _web_sessions.get(existing_session_id)
                if winner is None:
                    _web_sessions[existing_session_id] = session
                    _active_web_sessions[existing_session_id] = 1
                    return existing_session_id, session
                _active_web_sessions[existing_session_id] = _active_web_sessions.get(existing_session_id, 0) + 1
            session.close()
            return existing_session_id, winner

    # Constructed outside the lock -- ChatSession's own __init__ does real
    # I/O (neuro-san session setup, thinking-file creation), which would
    # otherwise serialize EVERY concurrent session creation (even for
    # unrelated users) behind this one lock.
    web_session_id = str(uuid.uuid4())
    try:
        paths.sanitize_session_id(existing_session_id)
        web_session_id = existing_session_id
    except (TypeError, ValueError):
        pass
    session = ChatSession(agent_name, isolated=True)
    _configure_persisted_web_session(session, web_session_id, None)
    with _web_sessions_lock:
        winner = _web_sessions.get(web_session_id)
        if winner is not None:
            _active_web_sessions[web_session_id] = _active_web_sessions.get(web_session_id, 0) + 1
        else:
            _web_sessions[web_session_id] = session
            _active_web_sessions[web_session_id] = 1
            return web_session_id, session
    session.close()
    return web_session_id, winner


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


# ---------------------------------------------------------
# Downloading generated artifacts (Word documents + the cloud architecture
# diagram) -- both the Flask routes below (for the web client) and the
# "list"/"download" control lines in handle_logical_line above (for the
# interactive/-f CLI) delegate to coded_tools.common.artifact_downloads,
# the single canonical implementation also used by the LLM-invokable
# download_artifact tool -- not a second copy of this logic, so a
# filename always resolves against whichever output/ directory (flat, or
# a web session's own output/<session_id>/) is actually active.
# ---------------------------------------------------------


_agent_instructions_index: Optional[Dict[str, Dict[str, Any]]] = None
_agent_instructions_index_lock = threading.Lock()

# These registries/*.hocon files are NOT agent networks (each file's own
# header comment says so explicitly) -- plain key/value substitution
# fragments (aaosa*.hocon's aaosa_instructions/aaosa_call, shared across
# whichever files still use the older AAOSA pattern -- this project's own
# networks don't, see TECHNICAL_NOTES.md) or the "what's served" manifest
# itself. AgentNetworkRestorer expects a real network shape (a top-level
# "tools" list), so attempting to restore one of these as one is a
# guaranteed, pointless failure -- skipped up front rather than caught
# per-file, so it doesn't also spam a "cannot include" warning to stderr
# for every server start.
_NON_NETWORK_HOCON_PREFIXES = ("aaosa", "manifest")


def _collect_agent_instructions(tools: List[Any], source_file: str, index: Dict[str, Dict[str, Any]]) -> None:
    """
    Recursively walks one network's "tools" list, indexing every entry
    that is an actual AGENT definition (a dict with both "name" and
    "instructions" -- a bare string entry is an external "/network"
    reference or a coded-tool name) under its own name, WITH the
    "instructions" text that actually drives it. Recurses into each
    entry's own nested "tools" list too -- sub-agents defined inline
    within another agent's own "tools" array (e.g. process.hocon's
    Subprocess_Driver_Agent -> Subprocess_Generator_Agent) are exactly as
    real an agent as a top-level one, just not directly reachable from
    the network's own top-level list.

    A dict entry with a "class" instead of "instructions" is a CodedTool
    (a plain Python class, e.g. download_artifact) -- it has no
    natural-language "instructions" at all, so its own function.
    description (the text the LLM actually sees describing when/how to
    call it) is indexed as the closest equivalent. Without this, every
    tool node in the web client's Agent Network tab -- not just every
    sub-agent node -- 404s on hover instead of showing something useful.

    First definition of a given name wins (does not overwrite) -- agent/
    tool names are expected to be unique across this project's own
    registries, but a silent overwrite on an unexpected collision would
    make the SAME node name resolve to different text than whichever one
    the running conversation actually invoked, which is worse than just
    keeping whichever one was found first.
    """
    for entry in tools or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if name and name not in index:
            instructions = entry.get("instructions")
            function_spec = entry.get("function")
            function_description = function_spec.get("description") if isinstance(function_spec, dict) else None
            if instructions:
                index[name] = {
                    "instructions": instructions,
                    "description": function_description,
                    "source_file": source_file,
                }
            elif entry.get("class") and function_description:
                index[name] = {
                    "instructions": function_description,
                    "description": None,
                    "source_file": source_file,
                }
        nested_tools = entry.get("tools")
        if isinstance(nested_tools, list):
            _collect_agent_instructions(nested_tools, source_file, index)


def _build_agent_instructions_index() -> Dict[str, Dict[str, Any]]:
    """
    Scans every registries/**/*.hocon file (skipping the non-network
    fragment files -- see _NON_NETWORK_HOCON_PREFIXES), parsing each with
    neuro-san's own AgentNetworkRestorer (the same loader `ns validate`
    and the real server use, so "include" directives and ${...}
    substitutions resolve exactly the way they do for a real run rather
    than via a bare pyhocon parse that doesn't know this project's own
    include conventions), and returns a flat {agent_name: {instructions,
    description, source_file}} map covering every agent defined anywhere
    in the project, regardless of which file or how deeply nested.

    ALSO indexes every file's own front-man (its first top-level "tools"
    entry -- this project's registries each have exactly one, per
    TECHNICAL_NOTES.md's own "Complete registry inventory") under
    "__<file-basename>" (e.g. "__cloudarch_simulation_query"), aliased to
    that SAME front-man entry already indexed under its own real name.
    This is neuro-san's own internal naming for a same-server external
    agent reference (a "/network_name" entry in another network's own
    "tools" list, e.g. process_architect.hocon's "/cloudarch_simulation_
    query") -- confirmed directly in neuro_san's own
    ExternalAgentParsing.get_safe_agent_name: "__" + the reference path,
    "/" replaced with "__" for a nested reference. Without this, a node
    in the web client's Agent Network tab for any CROSS-NETWORK call
    (routed through the top-level process_architect.hocon orchestrator,
    i.e. nearly every pipeline this project has) carries this "__"-
    prefixed safe-name, not the real agent name the plain index above is
    keyed by, and every hover on it 404s.

    A single bad/unparseable file is skipped (logged, not fatal) rather
    than failing the whole index -- one malformed registry must not take
    down the "show instructions on hover" feature for every OTHER
    network's own, perfectly valid agents.
    """
    index: Dict[str, Dict[str, Any]] = {}
    pattern = os.path.join(_PROJECT_ROOT, "registries", "**", "*.hocon")
    for abs_path in sorted(glob.glob(pattern, recursive=True)):
        basename = os.path.basename(abs_path)
        if basename.startswith(_NON_NETWORK_HOCON_PREFIXES):
            continue
        rel_path = os.path.relpath(abs_path, _PROJECT_ROOT)
        try:
            restorer = AgentNetworkRestorer(registry_dir=None)
            agent_network = restorer.restore(file_reference=abs_path)
            config = agent_network.get_config()
        except Exception:  # pylint: disable=broad-except
            _web_logger.warning("Could not parse %s for the agent-instructions index -- skipping.", rel_path)
            continue
        tools = config.get("tools") if isinstance(config, dict) else None
        if not isinstance(tools, list):
            continue
        _collect_agent_instructions(tools, rel_path, index)

        front_man = next((t for t in tools if isinstance(t, dict) and t.get("name") and t.get("instructions")), None)
        front_man_entry = index.get(front_man["name"]) if front_man is not None else None
        if front_man_entry is not None:
            file_basename = os.path.splitext(basename)[0]
            index.setdefault(f"__{file_basename}", front_man_entry)
    return index


def _get_agent_instructions_index() -> Dict[str, Dict[str, Any]]:
    """Lazily builds _build_agent_instructions_index's result ONCE per
    server process and reuses it -- the registries on disk don't change
    during a single server run, and re-parsing ~30 HOCON files on every
    single hover in the web client's Agent Network tab would be wasted
    work for an answer that's already known."""
    global _agent_instructions_index
    with _agent_instructions_index_lock:
        if _agent_instructions_index is None:
            _agent_instructions_index = _build_agent_instructions_index()
        return _agent_instructions_index


def build_web_app(agent_name: str, https: bool = True):
    """
    Build (but do not run) the Flask REST app for -d/--detached --flask mode.

    Exposes the SAME routes/shapes as the ADK port's build_web_app:
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
      GET    /artifacts/documents  Every generated .docx currently in
                               output/ -> {"status": "ok", "documents":
                               [{"filename": "...", "size_bytes": N,
                               "modified": "<ISO8601>"}, ...]}.
      GET    /artifacts/documents/<filename>/download  Downloads one
                               generated .docx (filename exactly as
                               returned above) as a real file attachment,
                               or 404 if no such file exists in output/.
      GET    /artifacts/cloudarch/download  Downloads
                               output/cloudarch_drawio.xml as a real file
                               attachment (vs. GET /artifacts/cloudarch's
                               JSON-wrapped string, for the client's own
                               renderer), or 404 if none exists yet.
      GET    /artifacts/cloudarch_iac/download  Downloads
                               output/cloudarch_iac.zip as a real file
                               attachment, or 404 if the IaC pipeline
                               hasn't produced one yet.
      GET    /artifacts/process_flow_vsdx/download  Downloads
                               output/process_flow.vsdx (see
                               /process_visio_export), or 404 if nothing
                               has been exported yet.
      GET    /artifacts/design_flow_vsdx/download  Same as above, for
                               output/design_flow.vsdx.
      GET    /artifacts/cloudarch_vsdx/download  Downloads
                               output/cloudarch_architecture.vsdx (see
                               /cloudarch_visio_export), or 404 if nothing
                               has been exported yet.
      GET    /.well-known/agent.json  This project's own Agent Discovery API
                               manifest, describing capabilities, endpoints,
                               and agents (NOT the external Open Agentic Web
                               standard -- see /agent-manifest.json below for
                               the route that genuinely implements that).
      GET    /agent-manifest.json     The REAL Open Agentic Web MVP spec manifest
                               (see network_publishing.py): {"networks": {<name>:
                               {name, description, front_man, hocon}}} for every
                               publicly-listed registries/*.hocon network.
      GET    /networks/<name>.network.json  The resolved (includes/substitutions
                               expanded) Neuro-San agent-network JSON for one
                               published network, referenced by the manifest
                               above's own "hocon" field. 404 if `name` isn't a
                               publicly-listed network.
      GET    /agents                  Machine-readable capability registry listing
                               all agent cards; supports ?category=, ?artifact=,
                               ?type=, ?query=, ?full=true, ?wrapped=true.
      GET    /agents/<name>           Full Agent Card metadata for an agent.
      GET    /capabilities            Searchable capability catalog.
      GET    /workflows               Engineering lifecycle workflow definitions.
      GET    /workflows/<name>        Detailed workflow definition.
      GET    /artifacts/contracts     Standardized artifact output schemas.
      GET    /artifacts/contracts/<type> Specific artifact schema contract.
      GET    /agents/<name>/instructions  `name` is an agent's own short
                               name (e.g. "CloudArch_Agent") -> {"status":
                               "ok", "name": "...", "instructions": "...",
                               "description": "..." or null, "source_file":
                               "registries/..."}, or 404 if no agent by
                               that name is defined anywhere in this
                               project's own registries/*.hocon files.
      GET    /status           Liveness probe. Unlike the ADK port,
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
    from flask import Flask, request, jsonify, make_response, Response, send_file, redirect, send_from_directory, abort
    import html
    from pathlib import Path

    web_app = Flask("ProcessArchitectWebServiceNS")
    install_session_log_handler()
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

    def _web_session_id_for_get_request() -> Optional[str]:
        """Resolves the requesting web session's own id for a plain GET
        route (the /artifacts/* routes below) -- these have no JSON body
        of their own the way POST /chat does, so a `session_id` QUERY
        parameter is checked first. That's what the web client actually
        sends (it tracks its own session id in JS state and passes it
        explicitly on every request, the same as the POST routes' own
        `payload.get("session_id")`) rather than relying on this cookie
        at all -- this server's own CORS handling above reflects back
        whatever Origin a browser sends, but never sets
        Access-Control-Allow-Credentials, so a cross-origin fetch() (the
        web client's own default deployment: a static page served from a
        different origin than this API) never actually sends OR receives
        this cookie, regardless of `secure`/`samesite`. The cookie is
        still checked second, for any OTHER same-origin caller that
        never passes the query parameter explicitly."""
        return request.args.get("session_id") or request.cookies.get(WEB_SESSION_COOKIE)

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

        if (
            request.path in (
                "/",
                "/index.html",
                "/style.css",
                "/app.js",
                "/favicon.ico",
                "/status",
                "/.well-known/agent.json",
                "/agent-manifest.json",
                "/agents",
                "/capabilities",
                "/workflows",
                "/artifacts/contracts",
            )
            or (request.path.startswith("/agents/") and not request.path.endswith("/instructions"))
            or request.path.startswith(("/workflows/", "/artifacts/contracts/", "/networks/", "/auth/"))
        ):
            return None  # liveness probe, discovery, and SSO auth/compliance endpoints stay open: no auth, no rate limit

        if api_key:
            auth_header = request.headers.get("Authorization", "")
            bearer_token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else None
            # Allow valid SSO session token or configured WEBAPIKEY
            sso_token = request.cookies.get("sso_token") or (bearer_token if bearer_token and bearer_token.startswith("sso_") else None)
            is_valid_sso = False
            if sso_token:
                try:
                    from process_interface.sso import get_sso_session_manager
                    is_valid_sso = get_sso_session_manager().get_session(sso_token) is not None
                except Exception:
                    pass

            if not (is_valid_sso or _api_key_matches(bearer_token) or _api_key_matches(request.headers.get("X-API-Key"))):
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
        _web_logger.info("POST /chat received (session=%s, query_len=%d)", session_id, len(query.strip()))

        web_session_id = None
        try:
            web_session_id, session = _get_or_create_web_session(session_id, agent_name)
            with paths.use_session(web_session_id):
                response_text = session.send(query.strip(), files=files)
            _web_logger.info("POST /chat completed (session=%s, resp_len=%d)", web_session_id, len(response_text or ""))
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
        _web_logger.info("POST /chat/stream received (session=%s, query_len=%d)", session_id, len(query.strip()))
        # Resolved up front (not inside the generator below) so the
        # session id is known -- and its cookie set -- before the
        # streaming response even starts, exactly like POST /chat.
        web_session_id, session = _get_or_create_web_session(session_id, agent_name)

        def generate():
            # paths.use_session wraps this whole generator body rather than
            # each individual tool call inside it -- safe ONLY because
            # Werkzeug's threaded=True (run_web_service) gives every
            # concurrent request its own brand-new OS thread (Python's
            # ThreadingMixIn never reuses/pools threads mid-request), and
            # each new thread starts with its own default contextvars
            # context. A plain (non-async) generator does NOT get its own
            # isolated context the way an asyncio Task does -- two
            # DIFFERENT generators' next() calls genuinely interleaved on
            # the SAME OS thread (confirmed empirically) would stomp on
            # each other's session id. That interleaving can't happen
            # under this server's own threading model; it WOULD become
            # possible under a cooperative/greenlet-based WSGI server
            # (gevent/eventlet), which this project does not use.
            try:
                try:
                    _web_logger.info("Chat stream session %s active: beginning event streaming", web_session_id)
                    with paths.use_session(web_session_id):
                        for update in session.send_streaming(query.strip(), files=files):
                            yield f"data: {json.dumps({**update, 'session_id': web_session_id})}\n\n"
                    _web_logger.info("Chat stream session %s ended cleanly", web_session_id)
                except Exception:
                    _web_logger.exception("Web chat stream error for session %s", web_session_id)
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
        # Removes this session's own output/<session_id>/ directory right
        # now rather than waiting for the next purge sweep -- an explicit
        # "drop this session" request is as clear a signal as it gets that
        # nothing will need those files again.
        try:
            persisted_state_removed = purge_session(session_id)
        except ValueError:
            persisted_state_removed = False
        return jsonify({
            "status": "ok", "session_id": session_id,
            "cleared": existed or persisted_state_removed,
        })

    @web_app.route("/logs", methods=["GET"])
    @web_app.route("/chat/<session_id>/logs", methods=["GET"])
    def get_logs(session_id=None):
        sid = session_id or _web_session_id_for_get_request()
        if not sid:
            return jsonify({
                "status": "error",
                "error": "session_id parameter is required",
            }), 400
        try:
            paths.sanitize_session_id(sid)
        except ValueError:
            return jsonify({
                "status": "error",
                "error": "Invalid session_id format",
            }), 400

        level = request.args.get("level", "all")
        search = request.args.get("search", "")
        limit_str = request.args.get("limit", "500")
        try:
            limit = int(limit_str)
        except (ValueError, TypeError):
            limit = 500

        res = get_session_log_entries(session_id=sid, level=level, search=search, limit=limit)
        return jsonify({
            "status": "ok",
            "session_id": sid,
            "level": level,
            "search": search,
            "total_count": res["total_count"],
            "logs": res["logs"],
        })

    # ---------------------------------------------------------
    # SSO AUTHENTICATION & US/EU REGULATORY COMPLIANCE ROUTES
    # ---------------------------------------------------------
    from process_interface.sso import (
        get_configured_providers,
        get_providers_metadata,
        get_sso_session_manager,
        get_notice_at_collection,
        get_privacy_policy_text,
        get_terms_of_service_text,
        COOKIE_CATEGORIES,
        generate_oauth_state,
        generate_pkce_pair,
        clear_cli_credentials,
    )

    def _json_for_script(value) -> str:
        """CONFIRMED AS A REAL BUG (CodeQL: reflected server-side XSS):
        json.dumps() alone is not safe to embed inside an HTML <script>
        block. It does not escape "<", ">", or "&" -- a value containing
        the literal substring "</script>" (e.g. an OAuth error_description
        query param, or the provider_id URL path segment, both attacker-
        reachable before any real OAuth round-trip happens) would
        prematurely close the surrounding script tag at the HTML PARSER
        level, which looks for that literal byte sequence before any JS
        ever runs -- turning whatever comes after it into real, browser-
        parsed HTML/script. Escaping those three characters to their
        \\uXXXX equivalents keeps the JSON valid (the JS engine decodes
        them right back to the same characters) while making it
        impossible for the embedded value to ever contain a literal
        HTML-significant sequence.
        """
        return (
            json.dumps(value)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )

    def _safe_client_return(raw: Optional[str]) -> str:
        """CONFIRMED AS A REAL BUG: ?redirect_uri was accepted verbatim from
        the request and later used, with no validation at all, as the
        post-login redirect destination -- including appending the
        freshly-minted real SSO session token as a URL query parameter when
        no popup opener was available. An attacker-crafted link
        (`/auth/login/google?redirect_uri=https://evil.example/steal`)
        would send a victim through a completely legitimate Google login
        and then hand their real, usable session token straight to
        evil.example via the final redirect -- full account takeover, with
        nothing about the flow looking suspicious to the victim.

        A same-origin relative path is always safe and always allowed. The
        web client legitimately needs an ABSOLUTE cross-origin redirect_uri
        too (it typically lives on a different origin than this backend,
        and sends its own page URL so the post-login bridge can navigate
        back to it when no popup opener is available) -- that's only
        honored if its origin is in the operator's own explicit
        SSO_ALLOWED_REDIRECT_ORIGINS allowlist. Unconfigured (the default)
        means only relative paths work -- secure by default, matching every
        other "set an env var to enable this" feature in this file.
        """
        if not raw:
            return "/"
        parsed = urllib.parse.urlparse(raw)
        if not parsed.scheme and not parsed.netloc:
            # Relative path. Still must be rejected if it's a protocol-
            # relative "//host" URL, or a "/\host" variant some browsers
            # still normalize to "//" -- urlparse alone doesn't catch
            # either (no scheme, and no netloc since there's no "//" by
            # its own parsing rules for the backslash variant).
            if raw.startswith("/") and not raw.startswith("//") and not raw.startswith("/\\"):
                return raw
            return "/"
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        # Also safe: an absolute URL that just spells out THIS SAME
        # server's own origin (e.g. this app's own /index.html route,
        # for a deployment where this backend also serves the web
        # client) -- functionally identical to a relative path, no
        # cross-origin leak at all.
        if origin in _sso_allowed_redirect_origins() or origin == request.host_url.rstrip("/"):
            return raw
        return "/"

    def _resolve_sso_token() -> Optional[str]:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            tok = auth_header[7:].strip()
            if tok.startswith("sso_"):
                return tok
        cookie_token = request.cookies.get("sso_token")
        if cookie_token and cookie_token.startswith("sso_"):
            return cookie_token
        return None

    @web_app.route("/auth/providers", methods=["GET"])
    def auth_providers():
        meta = get_providers_metadata()
        sso_enabled = any(bool(p.get("configured")) for p in meta)
        return jsonify({
            "status": "ok",
            "sso_enabled": sso_enabled,
            "providers": meta,
            "cookie_categories": COOKIE_CATEGORIES,
        })

    @web_app.route("/auth/login/<provider_id>", methods=["GET"])
    def auth_login(provider_id):
        providers = get_configured_providers()
        provider = providers.get(provider_id.lower())
        if not provider:
            return jsonify({"status": "error", "error": f"Unknown provider: {provider_id}"}), 404

        state = generate_oauth_state()
        verifier, challenge = generate_pkce_pair()

        client_return = _safe_client_return(request.args.get("redirect_uri"))
        host_url = request.host_url.rstrip("/")
        redirect_uri = f"{host_url}/auth/callback/{provider_id.lower()}"

        def _make_error_bridge(err_msg: str, client_ret: str, pid: str, status_code: int = 400):
            error_bridge = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Process Architect &mdash; Authentication Error</title>
  <script>
    const errorData = {{
      type: "SSO_AUTH_ERROR",
      error: {_json_for_script(err_msg)},
      provider: {_json_for_script(pid)}
    }};
    let handled = false;
    if (window.opener && !window.opener.closed) {{
      try {{
        window.opener.postMessage(errorData, "*");
        handled = true;
        setTimeout(() => window.close(), 400);
      }} catch (e) {{
        handled = false;
      }}
    }}
    if (!handled) {{
      try {{
        const dest = new URL({_json_for_script(client_ret)}, window.location.href);
        dest.searchParams.set("sso_error", {_json_for_script(err_msg)});
        window.location.href = dest.toString();
      }} catch (e) {{
        window.location.href = {_json_for_script(client_ret)};
      }}
    }}
  </script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #0f1117; color: #ef4444; text-align: center; padding-top: 50px; }}
    a {{ color: #6366f1; text-decoration: underline; }}
  </style>
</head>
<body>
  <h2>Authentication Error</h2>
  <p>{html.escape(err_msg)}</p>
  <p><a href="{html.escape(client_ret)}">Return to Login Screen</a></p>
</body>
</html>"""
            err_resp = make_response(error_bridge, status_code)
            err_resp.delete_cookie("sso_state")
            err_resp.delete_cookie("sso_pkce_verifier")
            err_resp.delete_cookie("sso_client_return")
            return err_resp

        if not provider.is_configured:
            err_msg = (
                f"{provider.display_name} Single Sign-On is not configured. "
                f"Real authentication requires {provider.provider_id.upper()}_CLIENT_ID and "
                f"{provider.provider_id.upper()}_CLIENT_SECRET in your environment or .env file."
            )
            want_json = request.args.get("json", "").lower() == "true" or request.headers.get("Accept") == "application/json"
            if want_json:
                return jsonify({"status": "error", "error": err_msg}), 400
            return _make_error_bridge(err_msg, client_return, provider_id)

        auth_url = provider.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
        )

        want_json = request.args.get("json", "").lower() == "true" or request.headers.get("Accept") == "application/json"
        if want_json:
            resp = make_response(jsonify({
                "status": "ok",
                "provider": provider_id,
                "auth_url": auth_url,
                "state": state,
            }))
        else:
            resp = make_response(redirect(auth_url))

        resp.set_cookie("sso_state", state, max_age=600, httponly=True, samesite="Lax", secure=https)
        # CodeQL (py/clear-text-storage-sensitive-data) flags this as
        # storing a password-like secret in clear text. Reviewed and
        # accepted: this is RFC 7636's own standard PKCE flow -- the code
        # verifier is a single-use, 600-second-TTL, cryptographically
        # random value (generate_pkce_pair) that MUST travel with the
        # browser from this redirect to the callback below so it can be
        # presented to the token endpoint; there is no way to avoid
        # holding the raw value somewhere for that round trip. The cookie
        # carries httponly (JS/XSS can't read it), secure (HTTPS-only
        # transport when enabled), and samesite=Lax (not sent cross-site)
        # -- the three protections this generic heuristic doesn't model.
        resp.set_cookie("sso_pkce_verifier", verifier, max_age=600, httponly=True, samesite="Lax", secure=https)  # lgtm[py/clear-text-storage-sensitive-data]
        if client_return:
            resp.set_cookie("sso_client_return", client_return, max_age=600, httponly=True, samesite="Lax", secure=https)
        return resp

    @web_app.route("/auth/login/token", methods=["POST"])
    def auth_login_token():
        """Authenticates directly via a real provider personal access token (e.g. GitHub PAT).
        
        Validates the token against the real provider userinfo API. Rejects invalid credentials.
        """
        data = request.get_json(silent=True) or {}
        provider_id = (data.get("provider") or "github").lower()
        token_str = (data.get("token") or "").strip()
        if not token_str:
            return jsonify({"status": "error", "error": "Missing token"}), 400

        providers = get_configured_providers()
        provider = providers.get(provider_id)
        if not provider:
            return jsonify({"status": "error", "error": f"Unknown provider: {provider_id}"}), 404

        verified = provider.verify_token(token_str)
        if "error" in verified:
            return jsonify({"status": "error", "error": f"Authentication failed with {provider.display_name}: {verified['error']}"}), 401

        manager = get_sso_session_manager()
        session_rec = manager.create_session(verified)
        token = session_rec["token"]

        resp = make_response(jsonify({
            "status": "ok",
            "authenticated": True,
            "token": token,
            "user": verified,
        }))
        # CONFIRMED AS A REAL BUG: this used to set the cookie under the
        # name WEB_SESSION_COOKIE ("process_architect_session") -- the
        # UNRELATED chat-session cookie used throughout the rest of this
        # file to track which ChatSession a request belongs to. That both
        # corrupted the caller's existing chat session (its cookie value
        # became an "sso_..." token, matching no real chat session) AND
        # meant _resolve_sso_token's own cookie lookup (which reads
        # "sso_token", matching every other successful-auth path in this
        # file) would never find it at all.
        resp.set_cookie("sso_token", token, max_age=30 * 86400, httponly=True, samesite="Lax", secure=https)
        return resp

    @web_app.route("/auth/callback/<provider_id>", methods=["GET"])
    def auth_callback(provider_id):
        providers = get_configured_providers()
        provider = providers.get(provider_id.lower())
        if not provider:
            return jsonify({"status": "error", "error": f"Unknown provider: {provider_id}"}), 404

        want_json = request.args.get("mode", "").lower() == "json" or request.headers.get("Accept") == "application/json"
        # Defense in depth: this cookie should only ever contain a value
        # /auth/login already sanitized (see _safe_client_return's own
        # docstring), but re-validate at the point of use too.
        client_return = _safe_client_return(request.cookies.get("sso_client_return"))

        def _make_error_resp(err_msg: str, status_code: int = 400):
            if want_json:
                return jsonify({"status": "error", "error": err_msg}), status_code
            error_bridge = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Process Architect &mdash; Authentication Error</title>
  <script>
    const errorData = {{
      type: "SSO_AUTH_ERROR",
      error: {_json_for_script(err_msg)},
      provider: {_json_for_script(provider_id)}
    }};
    let handled = false;
    if (window.opener && !window.opener.closed) {{
      try {{
        window.opener.postMessage(errorData, "*");
        handled = true;
        setTimeout(() => window.close(), 400);
      }} catch (e) {{
        handled = false;
      }}
    }}
    if (!handled) {{
      try {{
        const dest = new URL({_json_for_script(client_return)}, window.location.href);
        dest.searchParams.set("sso_error", {_json_for_script(err_msg)});
        window.location.href = dest.toString();
      }} catch (e) {{
        window.location.href = {_json_for_script(client_return)};
      }}
    }}
  </script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #0f1117; color: #ef4444; text-align: center; padding-top: 50px; }}
    a {{ color: #6366f1; text-decoration: underline; }}
  </style>
</head>
<body>
  <h2>Authentication Error</h2>
  <p>{html.escape(err_msg)}</p>
  <p><a href="{html.escape(client_return)}">Return to Login Screen</a></p>
</body>
</html>"""
            err_resp = make_response(error_bridge, status_code)
            err_resp.delete_cookie("sso_state")
            err_resp.delete_cookie("sso_pkce_verifier")
            err_resp.delete_cookie("sso_client_return")
            return err_resp

        err = request.args.get("error")
        if err:
            err_desc = request.args.get("error_description") or err
            return _make_error_resp(f"{provider.display_name} authentication failed: {err_desc}")

        received_state = request.args.get("state")
        expected_state = request.cookies.get("sso_state")
        if not received_state or not expected_state or not hmac.compare_digest(received_state, expected_state):
            return _make_error_resp("Anti-CSRF state verification failed")

        code = request.args.get("code")
        if not code:
            return _make_error_resp("Missing authorization code from provider")

        verifier = request.cookies.get("sso_pkce_verifier")
        host_url = request.host_url.rstrip("/")
        redirect_uri = f"{host_url}/auth/callback/{provider_id.lower()}"

        tokens = provider.exchange_code_for_token(code=code, redirect_uri=redirect_uri, code_verifier=verifier)
        if "error" in tokens:
            return _make_error_resp(f"Token exchange error: {tokens['error']}")
        access_token = tokens.get("access_token", "")
        if not access_token:
            return _make_error_resp("Provider did not return an access token")

        raw = provider.fetch_user_profile(access_token)
        if "error" in raw:
            return _make_error_resp(f"Failed to fetch profile: {raw['error']}")

        profile = provider.normalize_user_profile(raw)

        manager = get_sso_session_manager()
        session_rec = manager.create_session(profile)
        token = session_rec["token"]

        active_chat_sid = request.args.get("session_id") or request.cookies.get(WEB_SESSION_COOKIE)
        if active_chat_sid:
            manager.link_chat_session(token, active_chat_sid)

        if want_json:
            resp = make_response(jsonify({
                "status": "ok",
                "authenticated": True,
                "token": token,
                "user": profile,
            }))
        else:
            bridge_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Process Architect &mdash; Authentication Complete</title>
  <script>
    const authData = {{
      type: "SSO_AUTH_SUCCESS",
      token: {_json_for_script(token)},
      user: {_json_for_script(profile)}
    }};
    let handled = false;
    if (window.opener && !window.opener.closed) {{
      try {{
        window.opener.postMessage(authData, "*");
        handled = true;
        setTimeout(() => window.close(), 300);
      }} catch (e) {{
        handled = false;
      }}
    }}
    if (!handled) {{
      try {{
        const dest = new URL({_json_for_script(client_return)}, window.location.href);
        dest.searchParams.set("token", {_json_for_script(token)});
        window.location.href = dest.toString();
      }} catch (e) {{
        window.location.href = {_json_for_script(client_return)};
      }}
    }}
  </script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #0f1117; color: #fff; text-align: center; padding-top: 50px; }}
  </style>
</head>
<body>
  <h2>Authentication Complete</h2>
  <p>Returning to Process Architect...</p>
</body>
</html>"""
            resp = make_response(bridge_html)

        resp.set_cookie("sso_token", token, max_age=30 * 86400, httponly=True, samesite="Lax", secure=https)
        resp.delete_cookie("sso_state")
        resp.delete_cookie("sso_pkce_verifier")
        resp.delete_cookie("sso_client_return")
        return resp

    @web_app.route("/auth/session", methods=["GET"])
    @web_app.route("/auth/me", methods=["GET"])
    def auth_session():
        token = _resolve_sso_token()
        if not token:
            return jsonify({"status": "ok", "authenticated": False, "user": None})
        manager = get_sso_session_manager()
        sess = manager.get_session(token)
        if not sess:
            return jsonify({"status": "ok", "authenticated": False, "user": None})
        return jsonify({
            "status": "ok",
            "authenticated": True,
            "token": sess["token"],
            "user": sess["user"],
            "created_at": sess["created_at"],
        })

    @web_app.route("/auth/logout", methods=["POST"])
    def auth_logout():
        token = _resolve_sso_token()
        if token:
            get_sso_session_manager().revoke_session(token)
        clear_cli_credentials()
        resp = make_response(jsonify({"status": "ok", "authenticated": False, "message": "Logged out successfully"}))
        resp.delete_cookie("sso_token", samesite="Lax", secure=https, path="/")
        return resp

    @web_app.route("/auth/compliance/notice", methods=["GET"])
    def auth_compliance_notice():
        return jsonify({
            "status": "ok",
            "notice": get_notice_at_collection(),
            "cookie_categories": COOKIE_CATEGORIES,
        })

    @web_app.route("/auth/compliance/privacy-policy", methods=["GET"])
    def auth_privacy_policy():
        return jsonify({
            "status": "ok",
            "markdown": get_privacy_policy_text(),
        })

    @web_app.route("/auth/compliance/terms", methods=["GET"])
    def auth_terms():
        return jsonify({
            "status": "ok",
            "markdown": get_terms_of_service_text(),
        })

    @web_app.route("/auth/user/export", methods=["GET"])
    def auth_user_export():
        token = _resolve_sso_token()
        if not token:
            return jsonify({"status": "error", "error": "Unauthorized"}), 401
        manager = get_sso_session_manager()
        export_data = manager.export_user_data(token)
        if "error" in export_data:
            return jsonify({"status": "error", "error": export_data["error"]}), 401
        return jsonify({"status": "ok", **export_data})

    @web_app.route("/auth/user/data", methods=["DELETE"])
    def auth_user_delete():
        token = _resolve_sso_token()
        if not token:
            return jsonify({"status": "error", "error": "Unauthorized"}), 401
        manager = get_sso_session_manager()
        result = manager.delete_user_data(token)
        if "error" in result:
            return jsonify({"status": "error", "error": result["error"]}), 401
        clear_cli_credentials()
        resp = make_response(jsonify(result))
        resp.delete_cookie("sso_token")
        return resp

    @web_app.route("/.well-known/agent.json", methods=["GET"])
    def agent_manifest():
        """This project's own Agent Discovery API manifest (not the external Open
        Agentic Web standard -- see agent_network_manifest() below for that)."""
        base_url = request.host_url.rstrip("/")
        manifest = get_agent_manifest(base_url=base_url)
        return jsonify(manifest)

    @web_app.route("/agent-manifest.json", methods=["GET"])
    def agent_network_manifest():
        """The real Open Agentic Web MVP spec manifest -- see network_publishing.py's own
        module docstring for the spec section this implements."""
        base_url = request.host_url.rstrip("/")
        manifest = network_publishing.build_agent_network_manifest(base_url=base_url)
        return jsonify(manifest)

    @web_app.route("/networks/<name>.network.json", methods=["GET"])
    def published_network(name: str):
        """The resolved agent-network JSON a published manifest entry's own "hocon" field
        points to -- see network_publishing.py."""
        config = network_publishing.resolve_network(name)
        if config is None:
            return jsonify({"status": "error", "error": f"No published network named {name!r}."}), 404
        return jsonify(config)

    @web_app.route("/agents", methods=["GET"])
    def agents():
        """Capability registry listing all agent cards.
        Supports query filtering:
          ?category=architecture|process|cloud|testing|portfolio|proposals|togaf|itsm
          ?artifact=requirements_summary|cloud_architecture|drawio_xml|...
          ?type=pipeline|consultant|reviewer|simulation|iac|tester|finops|router
          ?query=<text>
          ?full=true|false (default false, returns summaries)
          ?wrapped=true|false (default false, returns direct JSON array)
        """
        category = request.args.get("category")
        artifact = request.args.get("artifact")
        agent_type = request.args.get("type")
        query = request.args.get("query")
        full_mode = request.args.get("full", "").strip().lower() in ("true", "1", "yes")
        wrapped = request.args.get("wrapped", "").strip().lower() in ("true", "1", "yes")

        results = search_capabilities(
            query=query,
            category=category,
            artifact=artifact,
            agent_type=agent_type,
        )

        if not full_mode:
            items = [
                {
                    "name": r["name"],
                    "description": r["description"],
                    "category": r["category"],
                    "agent_type": r["agent_type"],
                    "artifacts": r["artifacts"],
                    "version": r["version"],
                }
                for r in results
            ]
        else:
            items = results

        if wrapped:
            return jsonify({
                "status": "ok",
                "count": len(items),
                "agents": items,
            })
        return jsonify(items)

    @web_app.route("/agents/<name>", methods=["GET"])
    def agent_card(name):
        """Retrieve full Agent Card metadata for an agent by name."""
        card = get_agent_card(name)
        if card is None:
            return jsonify({
                "status": "error",
                "error": f"No agent card found for '{name}'.",
            }), 404
        wrapped = request.args.get("wrapped", "").strip().lower() in ("true", "1", "yes")
        if wrapped:
            return jsonify({"status": "ok", "agent": card})
        return jsonify(card)

    @web_app.route("/capabilities", methods=["GET"])
    def capabilities():
        """Searchable capability catalog. Allows filtering by query keyword,
        category, produced/consumed artifact, and agent type."""
        category = request.args.get("category")
        artifact = request.args.get("artifact")
        agent_type = request.args.get("type")
        query = request.args.get("query")
        wrapped = request.args.get("wrapped", "").strip().lower() in ("true", "1", "yes")

        results = search_capabilities(
            query=query,
            category=category,
            artifact=artifact,
            agent_type=agent_type,
        )
        if wrapped:
            return jsonify({
                "status": "ok",
                "count": len(results),
                "capabilities": results,
            })
        return jsonify(results)

    @web_app.route("/workflows", methods=["GET"])
    def workflows():
        """Expose engineering lifecycle workflows and network flows."""
        wfs = get_all_workflows()
        wrapped = request.args.get("wrapped", "").strip().lower() in ("true", "1", "yes")
        if wrapped:
            return jsonify({
                "status": "ok",
                "count": len(wfs),
                "workflows": wfs,
            })
        return jsonify(wfs)

    @web_app.route("/workflows/<workflow_name>", methods=["GET"])
    def workflow_detail(workflow_name):
        """Retrieve a specific engineering lifecycle workflow definition."""
        wf = get_workflow(workflow_name)
        if wf is None:
            return jsonify({
                "status": "error",
                "error": f"No workflow definition found for '{workflow_name}'.",
            }), 404
        wrapped = request.args.get("wrapped", "").strip().lower() in ("true", "1", "yes")
        if wrapped:
            return jsonify({"status": "ok", "workflow": wf})
        return jsonify(wf)

    @web_app.route("/artifacts/contracts", methods=["GET"])
    def artifact_contracts():
        """Expose standardized artifact contract schemas."""
        contracts = list_all_artifact_contracts()
        wrapped = request.args.get("wrapped", "").strip().lower() in ("true", "1", "yes")
        if wrapped:
            return jsonify({
                "status": "ok",
                "count": len(contracts),
                "contracts": contracts,
            })
        return jsonify(contracts)

    @web_app.route("/artifacts/contracts/<artifact_type>", methods=["GET"])
    def artifact_contract_detail(artifact_type):
        """Retrieve a specific standardized artifact contract."""
        contract = get_artifact_contract(artifact_type)
        if contract is None:
            return jsonify({
                "status": "error",
                "error": f"No artifact contract found for '{artifact_type}'.",
            }), 404
        wrapped = request.args.get("wrapped", "").strip().lower() in ("true", "1", "yes")
        if wrapped:
            return jsonify({"status": "ok", "contract": contract})
        return jsonify(contract)

    @web_app.route("/artifacts/<name>", methods=["GET"])
    def artifact(name):
        """
        Read-only access to this web session's own output/<session_id>/
        process_data.json, design_data.json, requirements_summary.json,
        proposal_response.json, test_specification.json,
        portfolio_backlog.json, togaf_data.json, itsm_data.json, or
        cloudarch_drawio.xml (or flat output/
        for a caller with no session id at all -- e.g. a direct API
        caller that never went through POST /chat first), resolved via a
        `session_id` query parameter (see _web_session_id_for_get_request's
        own docstring for why a query parameter, not just the session
        cookie, matters here) -- a plain GET has no JSON body of its own
        to carry a session_id in the way POST /chat does. Powers the web
        client's artifact browser and "Cloud Architecture" tab -- a
        hierarchical/diagram viewer of
        whichever pipeline's current artifact. The ADK port's
        build_web_app has an identical route, and both keep these files
        at the identical relative path, so the client's fetch logic
        doesn't need to know which backend it's talking to.

        Deliberately a raw file read, NOT the existing
        load_master_process_json/load_master_design_json CodedTool
        helpers -- those silently fall back to a blank template when the
        file is missing (useful for a pipeline about to populate one, not
        for a debugging viewer that needs to tell "genuinely not generated
        yet" apart from "here's an empty template"), so this reports a
        real 404 instead.

        "cloudarch" returns `data` as the raw XML STRING (not JSON-parsed)
        -- the client's own mxGraph-XML renderer parses it directly, the
        same way it already does for a saved .drawio file.

        The three "*_vsdx" names and two "*_project_plan" names power the
        same "Diagrams" tab's generalized graph/Gantt views -- `data` for
        those is neither raw text nor a plain JSON-file-load, but the
        PARSED structured shape (process_interface.docgen.vsdx_export.
        parse_vsdx_to_graph's {"vertices": [...], "edges": [...]}, or
        process_interface.docgen.project_plan_export.parse_mspdi_tasks's
        {"tasks": [...]}), since .vsdx is a binary zip format the client
        cannot parse itself and the project-plan XML is parsed server-side
        for consistency with it.
        """
        from process_interface.docgen.vsdx_export import (
            CLOUDARCH_VSDX_FILENAME, DESIGN_FLOW_VSDX_FILENAME, PROCESS_FLOW_VSDX_FILENAME,
            parse_vsdx_to_graph,
        )
        from process_interface.docgen.project_plan_export import (
            PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME, PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME,
            parse_mspdi_tasks, parse_mspdi_project,
        )

        graph_names = {
            "process_flow_vsdx": PROCESS_FLOW_VSDX_FILENAME,
            "design_flow_vsdx": DESIGN_FLOW_VSDX_FILENAME,
            "cloudarch_vsdx": CLOUDARCH_VSDX_FILENAME,
        }
        task_list_names = {
            "portfolio_backlog_project_plan": PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME,
            "proposal_response_project_plan": PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME,
        }
        # Raw mxGraph/draw.io XML text, returned as-is for the client's own
        # parseDrawioXml. The PERT/CPM network diagrams generated alongside
        # every project plan export are real PNG images, not XML -- they
        # have no entry here at all, only a /download route (binary,
        # below), same as every other binary artifact (.vsdx, .xlsx, .docx).
        raw_xml_names = {
            "cloudarch": "cloudarch_drawio.xml",
        }
        filenames = {
            "process": "process_data.json",
            "design": "design_data.json",
            "requirements": "requirements_summary.json",
            "proposal_response": "proposal_response.json",
            "test_specification": "test_specification.json",
            "portfolio_backlog": "portfolio_backlog.json",
            "togaf": "togaf_data.json",
            "itsm": "itsm_data.json",
            **raw_xml_names,
            **graph_names,
            **task_list_names,
        }
        filename = filenames.get(name)
        if filename is None:
            return jsonify({
                "status": "error",
                "error": (
                    f"Unknown artifact '{name}' -- use 'process', 'design', 'requirements', "
                    "'proposal_response', 'test_specification', 'portfolio_backlog', 'togaf', "
                    "'itsm', 'cloudarch', 'process_flow_vsdx', 'design_flow_vsdx', "
                    "'cloudarch_vsdx', 'portfolio_backlog_project_plan', or "
                    "'proposal_response_project_plan'. The PERT/CPM diagrams "
                    "('portfolio_backlog_pert_cpm'/'proposal_response_pert_cpm') are images -- "
                    "use their own /download route instead."
                ),
            }), 400

        session_id = _web_session_id_for_get_request()
        _web_logger.info("GET /artifacts/%s requested (session=%s)", name, session_id)
        with paths.use_session(session_id):
            path = os.path.join(paths.output_dir(), filename)
            if not os.path.exists(path):
                _web_logger.debug("GET /artifacts/%s: file not found at %s (session=%s)", name, path, session_id)
                missing_guidance = {
                    "cloudarch": "run the cloud architecture pipeline or ask to design a cloud architecture first.",
                    "process_flow_vsdx": "export the process flow to Visio first (e.g. 'export process flow to visio').",
                    "design_flow_vsdx": "export the technical design to Visio first (e.g. 'export design flow to visio').",
                    "cloudarch_vsdx": "export the cloud architecture to Visio first (e.g. 'export cloud architecture to visio').",
                    "portfolio_backlog_project_plan": "export the portfolio backlog as a project plan first (e.g. 'export project plan').",
                    "proposal_response_project_plan": "export the proposal response as a project plan first (e.g. 'export proposal project plan').",
                    "process": "run the process engineering pipeline at least once.",
                    "design": "run the technical design pipeline at least once.",
                    "requirements": "run requirements extraction at least once.",
                    "proposal_response": "run the proposal response pipeline at least once.",
                    "test_specification": "run the test specification pipeline at least once.",
                    "portfolio_backlog": "run the portfolio backlog pipeline at least once.",
                    "togaf": "run the TOGAF architecture pipeline at least once.",
                    "itsm": "run the ITSM pipeline at least once.",
                }
                hint = missing_guidance.get(name, f"run the {name} pipeline at least once, then try again.")
                return jsonify({
                    "status": "error",
                    "error": f"No {filename} found yet -- {hint}",
                }), 404

            try:
                if name in graph_names:
                    data = parse_vsdx_to_graph(path)
                elif name in task_list_names:
                    project_data = parse_mspdi_project(path)
                    data = project_data if project_data is not None else {"tasks": parse_mspdi_tasks(path) or []}
                elif name in raw_xml_names:
                    with open(path, "r", encoding="utf-8") as f:
                        data = f.read()
                else:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
            except Exception:
                _web_logger.exception("Failed to read/parse %s (session=%s)", filename, session_id)
                return jsonify({
                    "status": "error",
                    "error": f"Could not read {filename} -- see server logs.",
                }), 500

        _web_logger.info("GET /artifacts/%s: successfully served %s (session=%s)", name, filename, session_id)
        return jsonify({"status": "ok", "name": name, "data": data})

    @web_app.route("/artifacts/documents", methods=["GET"])
    def list_documents():
        """
        Every generated .docx currently in this web session's own
        output/<session_id>/ (or flat output/ for a caller with no
        session id), for the web client's own download picker -- see
        list_output_documents's own docstring for why this has to be a
        directory listing rather than a fixed, known filename the way
        process/design/cloudarch above are.
        """
        with paths.use_session(_web_session_id_for_get_request()):
            documents = list_output_documents()
        return jsonify({"status": "ok", "documents": documents})

    @web_app.route("/artifacts/documents/<filename>/download", methods=["GET"])
    def download_document(filename):
        """Downloads one generated .docx by its own filename (exactly as
        returned by GET /artifacts/documents) as a real file attachment,
        for the web client's download button -- see safe_output_file_path
        for how `filename` is kept from escaping output/. `path` is
        resolved to a concrete absolute string up front, so send_file's
        own (possibly deferred) streaming below doesn't depend on the
        session context still being active."""
        with paths.use_session(_web_session_id_for_get_request()):
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
        with paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(paths.output_dir(), "cloudarch_drawio.xml")
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
        CloudArch_IaC_Pipeline's own zip_iac_files tool produces."""
        from process_interface.iac.generation import IAC_ZIP_FILENAME

        with paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(paths.output_dir(), IAC_ZIP_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": "No cloudarch_iac.zip found yet -- run the IaC pipeline at least once, then try again.",
            }), 404
        return send_file(path, as_attachment=True, download_name=IAC_ZIP_FILENAME, mimetype="application/zip")

    @web_app.route("/artifacts/portfolio_backlog_workbook/download", methods=["GET"])
    def download_portfolio_backlog_workbook():
        """Downloads the generated Enterprise Agile Portfolio Backlog workbook for this web session."""
        filename = "portfolio_backlog.xlsx"
        with paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(paths.output_dir(), filename)
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": f"No {filename} found yet -- run the Enterprise Agile Portfolio Backlog pipeline first.",
            }), 404
        return send_file(
            path,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @web_app.route("/artifacts/process_flow_vsdx/download", methods=["GET"])
    def download_process_flow_vsdx():
        """Downloads this web session's own exported process flow diagram
        Visio (.vsdx) file -- see /process_visio_export's own
        ExportProcessDesignVsdxCodedTool for how it's produced. Structurally
        identical to download_cloudarch above, just for this artifact kind."""
        from process_interface.docgen.vsdx_export import PROCESS_FLOW_VSDX_FILENAME

        with paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(paths.output_dir(), PROCESS_FLOW_VSDX_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": f"No {PROCESS_FLOW_VSDX_FILENAME} found yet -- export the process flow diagram as Visio first.",
            }), 404
        return send_file(
            path, as_attachment=True, download_name=PROCESS_FLOW_VSDX_FILENAME,
            mimetype="application/vnd.ms-visio.drawing.main+xml",
        )

    @web_app.route("/artifacts/design_flow_vsdx/download", methods=["GET"])
    def download_design_flow_vsdx():
        """Downloads this web session's own exported design flow/
        architecture diagram Visio (.vsdx) file. Structurally identical to
        download_process_flow_vsdx above, just for the design domain."""
        from process_interface.docgen.vsdx_export import DESIGN_FLOW_VSDX_FILENAME

        with paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(paths.output_dir(), DESIGN_FLOW_VSDX_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": f"No {DESIGN_FLOW_VSDX_FILENAME} found yet -- export the design flow diagram as Visio first.",
            }), 404
        return send_file(
            path, as_attachment=True, download_name=DESIGN_FLOW_VSDX_FILENAME,
            mimetype="application/vnd.ms-visio.drawing.main+xml",
        )

    @web_app.route("/artifacts/cloudarch_vsdx/download", methods=["GET"])
    def download_cloudarch_vsdx():
        """Downloads this web session's own exported cloud architecture
        diagram Visio (.vsdx) file -- see /cloudarch_visio_export's own
        ExportCloudarchVsdxCodedTool for how it's produced. Structurally
        identical to download_cloudarch above (which downloads the
        underlying cloudarch_drawio.xml instead), just for the exported
        Visio copy."""
        from process_interface.docgen.vsdx_export import CLOUDARCH_VSDX_FILENAME

        with paths.use_session(_web_session_id_for_get_request()):
            path = os.path.join(paths.output_dir(), CLOUDARCH_VSDX_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            return jsonify({
                "status": "error",
                "error": f"No {CLOUDARCH_VSDX_FILENAME} found yet -- export the cloud architecture diagram as Visio first.",
            }), 404
        return send_file(
            path, as_attachment=True, download_name=CLOUDARCH_VSDX_FILENAME,
            mimetype="application/vnd.ms-visio.drawing.main+xml",
        )

    @web_app.route("/artifacts/portfolio_backlog_project_plan/download", methods=["GET"])
    def download_portfolio_backlog_project_plan():
        """Downloads this web session's own exported Portfolio Backlog
        project plan (MSPDI XML) file -- see /project_plan_export's own
        ExportProjectPlanCodedTool for how it's produced. Structurally
        identical to download_cloudarch above, just for this artifact kind."""
        from process_interface.docgen.project_plan_export import PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME

        session_id = _web_session_id_for_get_request()
        _web_logger.info("GET /artifacts/portfolio_backlog_project_plan/download requested (session=%s)", session_id)
        with paths.use_session(session_id):
            path = os.path.join(paths.output_dir(), PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            _web_logger.debug("GET /artifacts/portfolio_backlog_project_plan/download: not found at %s (session=%s)", path, session_id)
            return jsonify({
                "status": "error",
                "error": f"No {PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME} found yet -- export the portfolio backlog as a project plan first.",
            }), 404
        _web_logger.info("GET /artifacts/portfolio_backlog_project_plan/download: serving %s (session=%s)", path, session_id)
        return send_file(
            path, as_attachment=True, download_name=PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME,
            mimetype="application/xml",
        )

    @web_app.route("/artifacts/proposal_response_project_plan/download", methods=["GET"])
    def download_proposal_response_project_plan():
        """Downloads this web session's own exported Proposal Response
        project plan (MSPDI XML) file. Structurally identical to
        download_portfolio_backlog_project_plan above, just for the
        proposal response domain."""
        from process_interface.docgen.project_plan_export import PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME

        session_id = _web_session_id_for_get_request()
        _web_logger.info("GET /artifacts/proposal_response_project_plan/download requested (session=%s)", session_id)
        with paths.use_session(session_id):
            path = os.path.join(paths.output_dir(), PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            _web_logger.debug("GET /artifacts/proposal_response_project_plan/download: not found at %s (session=%s)", path, session_id)
            return jsonify({
                "status": "error",
                "error": f"No {PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME} found yet -- export the proposal response as a project plan first.",
            }), 404
        _web_logger.info("GET /artifacts/proposal_response_project_plan/download: serving %s (session=%s)", path, session_id)
        return send_file(
            path, as_attachment=True, download_name=PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME,
            mimetype="application/xml",
        )

    @web_app.route("/artifacts/portfolio_backlog_pert_cpm/download", methods=["GET"])
    def download_portfolio_backlog_pert_cpm():
        """Downloads this web session's own PERT/CPM network diagram -- a
        real PNG image (matplotlib, see docgen.pert_cpm_export's own
        generate_pert_cpm_diagram), generated alongside the Portfolio
        Backlog's project plan every time it's exported. A binary image,
        not text/JSON, so (unlike cloudarch/vsdx/project-plan artifacts)
        this has no corresponding entry in the main /artifacts/<name> view
        route above -- this download route is its only web exposure, the
        same way .docx/.xlsx documents work."""
        from process_interface.docgen.project_plan_export import PORTFOLIO_BACKLOG_PERT_CPM_FILENAME

        session_id = _web_session_id_for_get_request()
        _web_logger.info("GET /artifacts/portfolio_backlog_pert_cpm/download requested (session=%s)", session_id)
        with paths.use_session(session_id):
            path = os.path.join(paths.output_dir(), PORTFOLIO_BACKLOG_PERT_CPM_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            _web_logger.debug("GET /artifacts/portfolio_backlog_pert_cpm/download: not found at %s (session=%s)", path, session_id)
            return jsonify({
                "status": "error",
                "error": f"No {PORTFOLIO_BACKLOG_PERT_CPM_FILENAME} found yet -- export the portfolio backlog as a project plan first.",
            }), 404
        _web_logger.info("GET /artifacts/portfolio_backlog_pert_cpm/download: serving %s (session=%s)", path, session_id)
        return send_file(
            path, as_attachment=True, download_name=PORTFOLIO_BACKLOG_PERT_CPM_FILENAME,
            mimetype="image/png",
        )

    @web_app.route("/artifacts/proposal_response_pert_cpm/download", methods=["GET"])
    def download_proposal_response_pert_cpm():
        """Downloads this web session's own PERT/CPM network diagram PNG
        for the Proposal Response. Structurally identical to
        download_portfolio_backlog_pert_cpm above, just for the proposal
        response domain."""
        from process_interface.docgen.project_plan_export import PROPOSAL_RESPONSE_PERT_CPM_FILENAME

        session_id = _web_session_id_for_get_request()
        _web_logger.info("GET /artifacts/proposal_response_pert_cpm/download requested (session=%s)", session_id)
        with paths.use_session(session_id):
            path = os.path.join(paths.output_dir(), PROPOSAL_RESPONSE_PERT_CPM_FILENAME)
            exists = os.path.isfile(path)
        if not exists:
            _web_logger.debug("GET /artifacts/proposal_response_pert_cpm/download: not found at %s (session=%s)", path, session_id)
            return jsonify({
                "status": "error",
                "error": f"No {PROPOSAL_RESPONSE_PERT_CPM_FILENAME} found yet -- export the proposal response as a project plan first.",
            }), 404
        _web_logger.info("GET /artifacts/proposal_response_pert_cpm/download: serving %s (session=%s)", path, session_id)
        return send_file(
            path, as_attachment=True, download_name=PROPOSAL_RESPONSE_PERT_CPM_FILENAME,
            mimetype="image/png",
        )

    @web_app.route("/artifacts/<name>/download", methods=["GET"])
    def download_process_or_design_json(name):
        """Downloads this web session's own output/<session_id>/
        process_data.json, design_data.json, requirements_summary.json,
        proposal_response.json, test_specification.json, or
        portfolio_backlog.json as a real file attachment (as opposed
        to GET /artifacts/<name> above, which returns it JSON-wrapped for
        the client's own data-explorer viewer) -- structurally identical
        to download_cloudarch above, just for the other artifact kinds.
        The downloaded file can later be re-attached to a chat turn to
        resume working on it -- see Process_Import_Agent/Design_Import_Agent's
        own instructions for how an attachment literally named
        process_data.json/design_data.json is recognized and restored
        verbatim rather than re-extracted, and Requirements_Summary_Agent's/
        Proposal_Response_Pipeline's own literal-restore STEPs for the
        corresponding JSON files."""
        filenames = {
            "process": "process_data.json",
            "design": "design_data.json",
            "requirements": "requirements_summary.json",
            "proposal_response": "proposal_response.json",
            "test_specification": "test_specification.json",
            "portfolio_backlog": "portfolio_backlog.json",
            "togaf": "togaf_data.json",
            "itsm": "itsm_data.json",
        }
        filename = filenames.get(name)
        if filename is None:
            return jsonify({
                "status": "error",
                "error": (
                    f"Unknown artifact '{name}' -- use 'process', 'design', 'requirements', "
                    "'proposal_response', 'test_specification', 'portfolio_backlog', 'togaf', "
                    "or 'itsm'."
                ),
            }), 400
        session_id = _web_session_id_for_get_request()
        _web_logger.info("GET /artifacts/%s/download requested (session=%s)", name, session_id)
        with paths.use_session(session_id):
            path = os.path.join(paths.output_dir(), filename)
            exists = os.path.isfile(path)
        if not exists:
            _web_logger.debug("GET /artifacts/%s/download: not found at %s (session=%s)", name, path, session_id)
            return jsonify({
                "status": "error",
                "error": f"No {filename} found yet -- run the {name} pipeline at least once, then try again.",
            }), 404
        _web_logger.info("GET /artifacts/%s/download: serving %s (session=%s)", name, path, session_id)
        return send_file(path, as_attachment=True, download_name=filename, mimetype="application/json")

    @web_app.route("/agents/<name>/instructions", methods=["GET"])
    def agent_instructions(name):
        """
        Read-only lookup of one agent's real "instructions" (system
        prompt) text from this project's own registries/*.hocon files --
        for the web client's Agent Network tab, which otherwise only ever
        sees what's OBSERVABLE from the chat stream itself (an agent's
        dotted invocation path, how many times it's been called, its past
        queries/responses), never the actual prompt driving it.

        `name` is just the agent's own short name (the Agent Network
        tab's node "label" -- the LAST segment of a node's dotted id, e.g.
        "CloudArch_Agent" out of "CloudArch_Pipeline.CloudArch_Agent"),
        not the full dotted path -- agent names are unique across this
        project's own registries, and resolving a full dotted path back
        to a specific file/agent would also have to account for
        same-server external-agent references ("/network_name") crossing
        from one registry file into another, which this project's own
        node ids don't preserve enough information to reverse uniquely.
        A bare short name is both simpler and sufficient.
        """
        index = _get_agent_instructions_index()
        entry = index.get(name)
        if entry is None:
            return jsonify({
                "status": "error",
                "error": f"No agent named '{name}' found in this project's own registries.",
            }), 404
        return jsonify({
            "status": "ok",
            "name": name,
            "instructions": entry["instructions"],
            "description": entry["description"],
            "source_file": entry["source_file"],
        })

    @web_app.route("/status", methods=["GET"])
    def status():
        return jsonify({"status": "live"})

    webclient_dir = Path(__file__).resolve().parents[2] / "WebClient" / "ProcessEngineering" / "public"
    if webclient_dir.is_dir():
        @web_app.route("/", methods=["GET"])
        @web_app.route("/index.html", methods=["GET"])
        def serve_index():
            return send_from_directory(webclient_dir, "index.html")

        @web_app.route("/style.css", methods=["GET"])
        def serve_style():
            return send_from_directory(webclient_dir, "style.css")

        @web_app.route("/app.js", methods=["GET"])
        def serve_app_js():
            return send_from_directory(webclient_dir, "app.js")

        @web_app.route("/favicon.ico", methods=["GET"])
        def serve_favicon():
            return send_from_directory(webclient_dir, "favicon.ico")

    return web_app


def run_web_service(agent_name: str, port: Optional[int], use_https: bool, host: Optional[str] = None) -> None:
    """Build and serve the Flask REST app (-d/--detached --flask) until
    interrupted. `host` (set via -s/--server) overrides the HOST env var,
    the same way `port` (via -p/--port) already overrides listening-port
    defaults -- only used when explicitly passed, exactly like `port`."""
    host = host if host is not None else os.environ.get("HOST", "127.0.0.1")

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

    # One purge sweep thread for the life of this process -- see
    # process_toolkit.session_purge's own docstring. _active_web_sessions
    # (not a second on-disk flag) is what keeps a session currently
    # mid-request from being purged out from under it, regardless of how
    # stale its own last-activity timestamp looks.
    start_session_purge_thread(
        _SESSION_PURGE_INTERVAL_SECONDS,
        _SESSION_MAX_AGE_SECONDS,
        is_session_active=lambda session_id: session_id in _active_web_sessions,
    )

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
    ADK port's Flask layer."""
    display_text(
        "-d/--detached runs this project's native serving layer (`ns run`) -- neuro-san's own "
        "HTTP server + nsflow chat UI -- instead of the ADK port's custom Flask REST API. "
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
             "Flask REST API (same contract as the ADK port) instead. See --http, --port, and --server.",
    )
    parser.add_argument(
        "--flask", dest="flask", action="store_true",
        help="With --detached, run this project's own Flask REST API (POST /chat, "
             "DELETE /chat/<session_id>, GET /status -- same contract as the ADK port's "
             "-d mode) instead of `ns run`. See samples/WebClient/ProcessEngineering for a "
             "browser client that talks to this. Only valid with --detached.",
    )
    parser.add_argument(
        "--http", dest="http", action="store_true",
        help="With --detached --flask, serve plain HTTP on port 8080 instead of the default "
             "HTTPS on port 443 (matching the ADK port's own --http). With plain "
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
        "-s", "--server",
        dest="server", type=str, required=False,
        help="With --detached --flask, override the HOST env var (default: 127.0.0.1) the "
             "Flask REST API binds to. Only valid with --detached --flask -- plain --detached "
             "(`ns run`) has no equivalent host override.",
    )
    parser.add_argument(
        "--agent", dest="agent", type=str, default=AGENT_NAME_DEFAULT,
        help=f"Which served network to talk to (default: {AGENT_NAME_DEFAULT}, the top-level "
             "front-man). Pass any other registries/*.hocon network name to talk to it directly.",
    )
    parser.add_argument(
        "--login", "--sso-login",
        dest="sso_login", nargs="?", const="interactive", choices=["interactive", "google", "github", "microsoft", "outlook"],
        help="Perform Single Sign-On (SSO) login via Google, GitHub, Microsoft, or Outlook to authenticate CLI sessions.",
    )
    parser.add_argument(
        "--logout", "--sso-logout",
        dest="sso_logout", action="store_true",
        help="Log out of the active SSO session and remove stored local credentials.",
    )
    parser.add_argument(
        "--whoami",
        dest="whoami", action="store_true",
        help="Display currently authenticated SSO user profile.",
    )
    return parser


async def run_cli() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.sso_logout:
        from process_interface.sso import clear_cli_credentials
        if clear_cli_credentials():
            display_text("Logged out successfully. Local SSO credentials removed.\n", kind="info")
        else:
            display_text("No active SSO session credentials found.\n", kind="info")
        return

    if args.whoami:
        from process_interface.sso import load_cli_credentials
        creds = load_cli_credentials()
        if creds and creds.get("user"):
            user = creds["user"]
            display_text(
                f"\nAuthenticated SSO User:\n"
                f"  Name:     {user.get('name')}\n"
                f"  Email:    {user.get('email')}\n"
                f"  Provider: {str(user.get('provider')).upper()}\n"
                f"  User ID:  {user.get('id')}\n"
                f"  Token:    {creds.get('token', '')[:12]}...\n",
                kind="info",
            )
        else:
            display_text("Not logged in. Use --login to authenticate via Google, GitHub, Microsoft, or Outlook.\n", kind="info")
        return

    if args.sso_login:
        from process_interface.sso import perform_cli_sso_login
        provider = args.sso_login
        if provider == "interactive":
            print("\nSelect SSO Provider:")
            print("  1) Google")
            print("  2) GitHub")
            print("  3) Microsoft")
            print("  4) Outlook")
            try:
                choice = input("\nEnter choice (1-4, default 1): ").strip()
            except (EOFError, KeyboardInterrupt):
                choice = "1"
            mapping = {"1": "google", "2": "github", "3": "microsoft", "4": "outlook"}
            provider = mapping.get(choice, "google")

        res = perform_cli_sso_login(provider, open_browser_auto=True)
        if res.get("status") == "ok":
            user = res["user"]
            display_text(
                f"\nSuccessfully authenticated via {provider.upper()} SSO!\n"
                f"Logged in as: {user.get('name')} <{user.get('email')}>\n"
                f"Credentials saved to: {res.get('credentials_saved_to')}\n",
                kind="info",
            )
        else:
            display_text(f"\nSSO Login failed: {res.get('error')}\n", kind="error")
        return

    if not args.detached and (args.http or args.port is not None or args.flask or args.server is not None):
        parser.error("--flask, --http, --port, and --server only apply with -d/--detached.")
    if args.server is not None and not args.flask:
        parser.error("--server only applies with -d/--detached --flask (plain --detached/`ns run` has no host override).")

    if args.detached:
        if args.flask:
            run_web_service(agent_name=args.agent, port=args.port, use_https=not args.http, host=args.server)
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