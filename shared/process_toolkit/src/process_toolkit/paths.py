"""Single source of truth for where this library's functions write
generated artifacts (diagrams, documents). Defaults to a relative "output"
directory, matching the ADK sample's own long-standing convention -- a
caller that wants a different (e.g. absolute, test-isolated) location can
either monkeypatch OUTPUT_DIR directly (exactly how both ports' own test
suites isolate their output/ directory per test) or pass an explicit
output_dir to the functions that accept one.

Session-aware on top of that: both ports' `-d`/detached web-service modes
can serve many concurrent chat sessions, and every artifact a session
generates (process_data.json, generated .docx files, cloudarch_drawio.xml,
pipeline.lock, etc.) used to land in this one shared OUTPUT_DIR regardless
of which session produced it -- two concurrent sessions could silently
stomp on each other's files. use_session(session_id) scopes every
output_dir()/output_path() call made for the duration of its `with` block
to OUTPUT_DIR/<session_id>/ instead, via a contextvars.ContextVar (not a
plain module global or threading.local -- a ContextVar is the one
mechanism that stays correct across both an OS-thread-pool-based server
AND an asyncio-based one, including when a request hops from one to the
other, e.g. neuro-san's own AsyncioExecutor -> asyncio.to_thread chain).
Callers that never call use_session() (every non-daemon CLI mode, which
only ever has ONE session alive at a time; every existing test) see
EXACTLY today's behavior -- output_dir()/output_path()'s own signatures
are unchanged, and nothing resolves under a session subdirectory unless
something explicitly opted in.
"""

import contextvars
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from typing import Iterator, Optional

OUTPUT_DIR = "output"

SESSION_META_FILENAME = ".session_meta.json"

_session_id_var: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "process_toolkit_session_id", default=None
)

# Session ids are always this project's own server-minted uuid.uuid4() hex/
# dashed strings (see both ports' _get_or_create_web_session) -- this isn't
# guarding a currently-reachable attack (a client-supplied id that doesn't
# match a live session is discarded outright, never reaches here), it's
# cheap insurance against a future regression that DOES let an arbitrary
# string reach this function, since the result is used as a directory name.
_SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def sanitize_session_id(session_id: str) -> str:
    if not _SAFE_SESSION_ID_RE.match(session_id):
        raise ValueError(f"Refusing to use {session_id!r} as a session directory name.")
    return session_id


def _current_session_dir() -> Optional[str]:
    session_id = _session_id_var.get()
    if session_id is None:
        return None
    return os.path.join(OUTPUT_DIR, sanitize_session_id(session_id))


def _atomic_write_json(path: str, payload: dict) -> None:
    """Writes `payload` as JSON to `path` via a temp-file-then-os.replace
    swap, so a reader can never observe `path` partially written. Mirrors
    run_lock.py's own _atomic_write -- duplicated rather than imported
    from there (that one's private, and this module stays dependency-free
    of run_lock, which itself depends on this module)."""
    tmp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass  # normal case: os.replace already consumed it


def _touch_session_metadata(session_dir: str) -> None:
    """Records "this session was active just now" -- the signal
    purge_stale_sessions (session_purge.py) uses to decide what's safe to
    delete. Written atomically, and keyed off this timestamp rather than
    the session directory's own mtime: a write to an EXISTING file inside
    it does not bump the parent directory's mtime, only adding/removing a
    direct child does -- relying on directory mtime would risk purging a
    session that's being actively (re)used, just not via new files."""
    os.makedirs(session_dir, exist_ok=True)
    meta_path = os.path.join(session_dir, SESSION_META_FILENAME)
    _atomic_write_json(meta_path, {"last_active": time.time()})


@contextmanager
def use_session(session_id: Optional[str]) -> Iterator[None]:
    """Scopes every output_dir()/output_path() call made for the duration
    of this `with` block to OUTPUT_DIR/<session_id>/ instead of flat
    OUTPUT_DIR -- see this module's own docstring for why a ContextVar
    rather than a plain global.

    `session_id=None` is accepted and is a no-op (behaves exactly like
    never calling use_session() at all) -- lets a caller that doesn't
    always have a session id in hand (e.g. a non-daemon CLI path that
    happens to share code with the web path) call this unconditionally
    without an extra branch of its own.
    """
    if session_id is None:
        yield
        return
    _touch_session_metadata(os.path.join(OUTPUT_DIR, sanitize_session_id(session_id)))
    token = _session_id_var.set(session_id)
    try:
        yield
    finally:
        _session_id_var.reset(token)


def output_dir(*parts: str) -> str:
    """Returns (and ensures the existence of) the current session's
    OUTPUT_DIR/<session_id>/*parts (or plain OUTPUT_DIR/*parts, if no
    session is active) as a directory."""
    base = _current_session_dir() or OUTPUT_DIR
    path = os.path.join(base, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def output_path(*parts: str) -> str:
    """Returns the current session's OUTPUT_DIR/<session_id>/*parts (or
    plain OUTPUT_DIR/*parts, if no session is active) as a file path,
    ensuring its parent directory exists."""
    base = _current_session_dir() or OUTPUT_DIR
    path = os.path.join(base, *parts)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path
