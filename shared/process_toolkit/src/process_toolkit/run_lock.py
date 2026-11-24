"""In-memory, session-aware lock serializing pipeline runs within a session.

Pipeline runs generate/review shared artifacts (approval.json, stop_counter.json,
process_data.json, etc.) across multiple tool calls spread over LLM turns.

Locks are tracked entirely in server/process memory:
  - For web sessions: tracked by session ID (from paths.current_session_id()).
  - For CLI sessions: tracked by utime in seconds (e.g. f"cli_{_CLI_START_UTIME}").
  - Once the server or CLI process terminates, all session locks in memory are
    automatically wiped clean -- no lingering mutex or lock files on disk.
  - Re-acquiring with the same token within a session succeeds (reentrancy).
  - Acquiring with a different token while an active run is in flight raises PipelineLockedError.
  - Expired locks (older than stale_after_seconds) are safely reclaimed.
"""

import contextvars
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Dict, Optional

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.RunLock")

LOCK_FILENAME = "pipeline.lock"
_MUTEX_SUFFIX = ".mutex"

DEFAULT_STALE_AFTER_SECONDS = 1200.0
_HEARTBEAT_INTERVAL_SECONDS = DEFAULT_STALE_AFTER_SECONDS / 4

_session_locks: Dict[str, dict] = {}
_mem_lock = threading.Lock()
_cli_session_utime_var: "contextvars.ContextVar[Optional[int]]" = contextvars.ContextVar(
    "process_toolkit_cli_utime", default=None
)
_CLI_START_UTIME: int = int(time.time())


class PipelineLockedError(RuntimeError):
    """Raised by acquire_pipeline_lock when a different, still-active
    pipeline run already holds the lock."""


def _lock_path() -> str:
    return paths.output_path(LOCK_FILENAME)


def _read_disk_lock(path: Optional[str] = None) -> Optional[dict]:
    p = path or _lock_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def current_session_key() -> str:
    """Returns the active session key: session_id for web sessions,
    or cli_<utime> for CLI sessions."""
    sid = paths.current_session_id()
    if sid:
        return str(sid)
    if paths.OUTPUT_DIR != "output":
        return f"dir_{paths.OUTPUT_DIR}"
    utime = _cli_session_utime_var.get()
    if utime is None:
        utime = _CLI_START_UTIME
    return f"cli_{utime}"


def _read_lock(path: Optional[str] = None) -> Optional[dict]:
    """In-memory read accessor for lock info for the current session,
    falling back to disk for legacy fixture compatibility."""
    key = current_session_key()
    with _mem_lock:
        lock_info = _session_locks.get(key)
        if lock_info:
            return dict(lock_info)
        return _read_disk_lock(path)


def _atomic_write(path: str, payload: dict) -> None:
    """Legacy helper maintained for test compatibility; writes to in-memory state."""
    key = current_session_key()
    with _mem_lock:
        _session_locks[key] = dict(payload)


@contextmanager
def _mutex_guard(path: Optional[str] = None):
    """In-memory critical section serializer wrapping _mem_lock."""
    with _mem_lock:
        yield


def acquire_pipeline_lock(
    label: str,
    token: Optional[str] = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    session_key: Optional[str] = None,
) -> str:
    """Call at the start of a pipeline run.

    Returns the token holding the lock. If `token` is omitted, a new
    one is minted. If a later call from the same run needs to re-acquire,
    pass the token returned the first time.

    Raises PipelineLockedError if a different, still-active run already
    holds the lock for this session.
    """
    key = session_key or current_session_key()
    my_token = token or uuid.uuid4().hex
    now = time.time()
    payload = {
        "label": label,
        "token": my_token,
        "started_at": now,
        "pid": os.getpid(),
        "session_key": key,
    }

    logger.info(
        "acquire_pipeline_lock: attempting acquire session_key=%s, label=%r, requested_token=%s, pid=%s, thread=%s",
        key, label, token, os.getpid(), threading.current_thread().name,
    )

    with _mem_lock:
        existing = _session_locks.get(key)
        if existing is None:
            disk_lock = _read_disk_lock()
            if disk_lock is not None:
                existing = disk_lock

        if existing is None:
            _session_locks[key] = payload
            logger.info(
                "acquire_pipeline_lock: SUCCESS (new lock) session_key=%s, label=%r, token=%s",
                key, label, my_token,
            )
            return my_token

        if existing.get("token") == my_token:
            prev_started = existing.get("started_at", now)
            existing["started_at"] = now
            existing["label"] = label
            logger.info(
                "acquire_pipeline_lock: SUCCESS (re-entrant refresh) session_key=%s, label=%r, token=%s (held for %.1fs)",
                key, label, my_token, (now - prev_started) if isinstance(prev_started, (int, float)) else 0.0,
            )
            return my_token

        started_at = existing.get("started_at")
        age = now - started_at if isinstance(started_at, (int, float)) else None
        if age is None or age >= stale_after_seconds:
            old_token = existing.get("token")
            logger.warning(
                "acquire_pipeline_lock: RECLAIMED STALE lock session_key=%s (held by %r with token=%s, age=%s >= %.1fs); new label=%r, new token=%s",
                key, existing.get("label"), old_token, f"{age:.1f}s" if age is not None else "None", stale_after_seconds, label, my_token,
            )
            if old_token:
                stop_pipeline_lock_heartbeat(old_token)
            _session_locks[key] = payload
            return my_token

        held_by = existing.get("label") or "another pipeline run"
        logger.warning(
            "acquire_pipeline_lock: DENIED for session_key=%s, requested_by=%r (token=%s); currently held by %r (token=%s, age=%.1fs < %.1fs)",
            key, label, my_token, held_by, existing.get("token"), age if age is not None else -1.0, stale_after_seconds,
        )
        raise PipelineLockedError(
            f"Another pipeline run ({held_by}) is already in progress against session {key}. "
            "Running two generate/update pipelines concurrently against the same session "
            "can corrupt each other's state. Wait for it to finish, then retry."
        )


def release_pipeline_lock(token: Optional[str]) -> None:
    """Removes the lock matching `token` across all active sessions in memory,
    and cleans up any lingering disk lock file."""
    if not token:
        logger.debug("release_pipeline_lock: called with empty/None token -- no-op")
        return

    # Unconditionally stop the heartbeat thread for this token
    stop_pipeline_lock_heartbeat(token)

    disk_p = _lock_path()
    if os.path.exists(disk_p):
        try:
            os.remove(disk_p)
            logger.info("release_pipeline_lock: removed legacy disk lock file %s", disk_p)
        except OSError as e:
            logger.warning("release_pipeline_lock: could not remove disk lock file %s: %s", disk_p, e)

    with _mem_lock:
        to_delete = [k for k, v in _session_locks.items() if v.get("token") == token]
        for k in to_delete:
            del _session_locks[k]
        if to_delete:
            logger.info(
                "release_pipeline_lock: SUCCESS released token=%s from sessions=%s (active sessions remaining: %s)",
                token, to_delete, list(_session_locks.keys()),
            )
        else:
            logger.info(
                "release_pipeline_lock: token=%s not found in active session locks %s (already released or expired)",
                token, list(_session_locks.keys()),
            )


_heartbeats: Dict[str, "_LockHeartbeat"] = {}
_heartbeats_lock = threading.Lock()


class _LockHeartbeat:
    """Background daemon thread keeping a lock token fresh."""

    def __init__(self, label: str, token: str, stale_after_seconds: float):
        self._label = label
        self._token = token
        self._stale_after_seconds = stale_after_seconds
        self._stop_event = threading.Event()
        ctx = contextvars.copy_context()
        self._thread = threading.Thread(
            target=ctx.run, args=(self._run,), daemon=True, name=f"pipeline-lock-heartbeat-{token[:8]}",
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS):
            try:
                acquire_pipeline_lock(self._label, token=self._token, stale_after_seconds=self._stale_after_seconds)
                logger.debug("Heartbeat tick refreshed lock for token=%s (label=%r)", self._token, self._label)
            except PipelineLockedError:
                logger.warning(
                    "Pipeline lock heartbeat for token %s could not refresh (lock held by another run) -- stopping thread.",
                    self._token,
                )
                return
            except Exception as e:
                logger.warning("Pipeline lock heartbeat error for token %s: %s", self._token, e)
                return

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=_HEARTBEAT_INTERVAL_SECONDS)


def start_pipeline_lock_heartbeat(
    label: str, token: Optional[str], stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> None:
    """Starts background thread keeping `token`'s lease fresh."""
    if not token:
        logger.debug("start_pipeline_lock_heartbeat: empty/None token passed -- no-op")
        return
    with _heartbeats_lock:
        if token in _heartbeats:
            logger.debug("start_pipeline_lock_heartbeat: heartbeat already running for token=%s", token)
            return
        logger.info(
            "start_pipeline_lock_heartbeat: STARTING heartbeat thread for token=%s, label=%r (interval=%.1fs)",
            token, label, _HEARTBEAT_INTERVAL_SECONDS,
        )
        _heartbeats[token] = _LockHeartbeat(label, token, stale_after_seconds)


def stop_pipeline_lock_heartbeat(token: Optional[str]) -> None:
    """Stops the heartbeat for `token` if one is running."""
    if not token:
        return
    with _heartbeats_lock:
        heartbeat = _heartbeats.pop(token, None)
    if heartbeat is not None:
        logger.info("stop_pipeline_lock_heartbeat: STOPPED heartbeat thread for token=%s", token)
        heartbeat.stop()
    else:
        logger.debug("stop_pipeline_lock_heartbeat: no running heartbeat for token=%s", token)


def peek_pipeline_lock(session_key: Optional[str] = None) -> Optional[dict]:
    """Read-only: returns the current lock info in memory if one is held,
    falling back to disk for legacy fixture compatibility."""
    key = session_key or current_session_key()
    with _mem_lock:
        existing = _session_locks.get(key)
        if existing is not None:
            logger.debug("peek_pipeline_lock: lock held in memory for session_key=%s: %s", key, existing)
            return dict(existing)
        if not paths.current_session_id() and _session_locks:
            res = dict(next(iter(_session_locks.values())))
            logger.debug("peek_pipeline_lock: fallback active lock found for session_key=%s: %s", key, res)
            return res
        disk_lock = _read_disk_lock()
        if disk_lock is not None:
            logger.debug("peek_pipeline_lock: disk lock found for session_key=%s: %s", key, disk_lock)
            return disk_lock
        logger.debug("peek_pipeline_lock: no lock held for session_key=%s", key)
        return None


def force_clear_pipeline_lock(session_key: Optional[str] = None) -> Optional[dict]:
    """Unconditionally removes the pipeline lock in memory and stops its heartbeat,
    also removing any disk lock file."""
    key = session_key or current_session_key()
    disk_p = _lock_path()
    disk_existing = None
    if os.path.exists(disk_p):
        disk_existing = _read_disk_lock(disk_p)
        try:
            os.remove(disk_p)
            logger.info("force_clear_pipeline_lock: removed disk lock %s", disk_p)
        except OSError:
            pass
    with _mem_lock:
        existing = _session_locks.pop(key, None)
        if existing is None and not paths.current_session_id() and _session_locks:
            popped_k, existing = _session_locks.popitem()
            logger.info("force_clear_pipeline_lock: no lock for key %s, popped active session %s", key, popped_k)
        target = existing or disk_existing
        if target is not None:
            tok = target.get("token")
            if tok:
                stop_pipeline_lock_heartbeat(tok)
            logger.warning(
                "force_clear_pipeline_lock: CLEARED lock for session_key=%s (held by %r, token=%s); remaining active sessions: %s",
                key, target.get("label"), tok, list(_session_locks.keys()),
            )
            return target
        logger.info("force_clear_pipeline_lock: no lock held for session_key=%s", key)
        return None
