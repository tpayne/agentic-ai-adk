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
    --http / -p/--port modify -d/--detached's listening port

Same control lines recognized inside interactive/-f mode: "exit"/"quit"/
"stop", "clear" (reset the session), a leading "#" (comment, echoed but not
sent), "sleep <seconds>"/"wait <seconds>", a leading "$ ..." (run a raw
shell command instead of sending the line to the agent), and a trailing
"\\" to continue one logical line across multiple physical lines.

-d/--detached does NOT reimplement the ADK original's bespoke Flask REST
API with its own auth/rate-limiting -- that was hardening specific to the
ADK sample's custom web-service mode. neuro-san already ships its own
multi-session HTTP server + nsflow chat UI (`ns run`), which is what the
project's README calls out as the deliberate replacement for that layer.
-d here simply launches it, so the flag still "does something" rather than
silently no-op'ing, without re-building security-sensitive code neuro-san
already provides.

Must be run from this project's root directory (same requirement as
`uv run ns chat <network>` elsewhere in this project) -- neuro-san resolves
registries/manifest.hocon relative to the current working directory.
"""

import argparse
import asyncio
import os
import subprocess
import sys
from typing import List, Optional

# A direct (in-process) neuro-san session resolves agent names against
# AGENT_MANIFEST_FILE, not simply "registries/manifest.hocon relative to
# cwd" -- `ns chat`/`ns run` set this env var themselves before ever
# touching the client library; a bare script importing the client
# directly (as this one does) has to do the same, or it silently falls
# back to the neuro-san LIBRARY's own bundled example manifest instead of
# this project's. Set before importing anything from neuro_san.client so
# the very first manifest read already sees it. Uses this file's own
# directory rather than cwd, so `cli.py` works the same regardless of
# where it's invoked from.
os.environ.setdefault(
    "AGENT_MANIFEST_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "registries", "manifest.hocon"),
)

from neuro_san.client.agent_session_factory import AgentSessionFactory  # noqa: E402
from neuro_san.client.streaming_input_processor import StreamingInputProcessor  # noqa: E402

AGENT_NAME_DEFAULT = "process_architect"
SLEEP_DEFAULT_SECONDS = 0.5

ANSI_RESET = "\033[0m"
ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_CYAN = "\033[96m"


def display_text(text: str, kind: str = "info", end: str = "\n") -> None:
    colour = {"info": ANSI_GREEN, "warning": ANSI_CYAN, "error": ANSI_RED}.get(kind, ANSI_GREEN)
    prefix = {"warning": "[Warning]: ", "error": "[Error]: "}.get(kind, "")
    print(f"{colour}{prefix}{text}{ANSI_RESET}", end=end)
    sys.stdout.flush()


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


class ChatSession:
    """One underlying neuro-san direct session against an agent network,
    plus the request/response state (chat_context, sly_data) that must be
    threaded from one turn to the next for the conversation to actually
    continue rather than looking like a fresh request every time. Mirrors
    the role of the ADK original's Runner+session_id pair -- "clear"
    replaces one of these wholesale, exactly like the ADK's
    init_session_and_runner did.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        factory = AgentSessionFactory()
        self.session = factory.create_session("direct", agent_name, use_direct=True)
        self.input_processor = StreamingInputProcessor("DEFAULT", None, self.session, None)
        self.sly_data = None
        self.chat_context = None

    def send(self, text: str) -> str:
        state = {
            "last_chat_response": None,
            "user_input": text,
            "sly_data": self.sly_data,
            "chat_context": self.chat_context or {},
            "chat_filter": {"chat_filter_type": "MAXIMAL"},
            "num_input": 0,
        }
        state = self.input_processor.process_once(state)
        self.sly_data = state.get("sly_data")
        self.chat_context = state.get("chat_context")
        return state.get("last_chat_response") or ""


async def handle_logical_line(line: str, session_holder: List[ChatSession], agent_name: str) -> bool:
    """Processes one fully-assembled (continuation-joined) instruction
    line. Returns True if the caller should stop reading further lines.
    session_holder is a 1-element list so "clear" can rebind it in place."""
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

    display_text(f"[user]: {line}")
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
                if await handle_logical_line(line, session_holder, agent_name):
                    return
            if continuation_parts:
                line = " ".join(part for part in continuation_parts if part)
                await handle_logical_line(line, session_holder, agent_name)
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
             "of the interactive/file/single-prompt CLI. See --http and --port.",
    )
    parser.add_argument(
        "--http", dest="http", action="store_true",
        help="With --detached, --port overrides the agent server's HTTP port instead of the nsflow "
             "UI's port.",
    )
    parser.add_argument(
        "-p", "--port",
        dest="port", type=int, required=False,
        help="With --detached, override the listening port (nsflow UI by default; the agent "
             "server itself with --http).",
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

    if not args.detached and (args.http or args.port is not None):
        parser.error("--http and --port only apply with -d/--detached.")

    if args.detached:
        run_detached(port=args.port, use_http=args.http)
        return

    if args.file:
        await process_file(args.file, args.agent)
        return

    if args.input:
        await process_single_prompt(args.input, args.agent)
        return

    display_text("Starting Process Architect Orchestrator in local chat mode...")
    await start_local_chat(args.agent)


if __name__ == "__main__":
    asyncio.run(run_cli())
