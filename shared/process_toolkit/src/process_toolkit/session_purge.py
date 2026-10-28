"""Background cleanup for the per-session output directories paths.py's
use_session() creates (see that module's own docstring for the full
picture) -- a `-d`/detached web-service process can accumulate one
output/<session_id>/ directory per distinct browser/client that ever
connected, most of which are abandoned (closed tab, never returned)
rather than explicitly dropped via DELETE /chat/<session_id>. Left
alone forever, that's an unbounded disk leak for the life of the server
process.

purge_stale_sessions() does the actual sweep: anything under output/
holding a SESSION_META_FILENAME whose own "last_active" is older than
max_age_seconds is removed, UNLESS the caller's own is_session_active
callback says otherwise (see its own docstring for why that, not a
second on-disk flag). start_session_purge_thread()/
stop_session_purge_thread() run that sweep on a fixed interval for as
long as a -d process is up, modeled directly on run_lock.py's own
_LockHeartbeat -- same daemon=True + Event-based wait loop + bounded
join on stop, same idempotent-per-caller bookkeeping.
"""

import json
import logging
import os
import shutil
import threading
import time
from typing import Callable, List, Optional

from werkzeug.utils import safe_join

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.SessionPurge")


def _read_last_active(session_dir: str) -> Optional[float]:
    meta_path = os.path.join(session_dir, paths.SESSION_META_FILENAME)
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        last_active = data.get("last_active")
        return last_active if isinstance(last_active, (int, float)) else None
    except Exception:
        return None


def purge_stale_sessions(
    max_age_seconds: float,
    is_session_active: Optional[Callable[[str], bool]] = None,
) -> List[str]:
    """Removes every output/<session_id>/ directory whose own
    SESSION_META_FILENAME says it's been untouched for at least
    max_age_seconds, and returns the list of session ids actually
    removed.

    Two things make a directory SAFE from this sweep, independent of how
    stale its own timestamp looks:

    - is_session_active(session_id) returning True -- an in-memory check
      against whatever pin/active-session bookkeeping the calling port
      already maintains (e.g. a request currently mid-flight for that
      session). Deliberately NOT a second on-disk "active" flag: a
      process that crashes mid-turn would never flip an on-disk flag back
      off, permanently exempting that session from ever being purged. An
      in-memory callback has no such failure mode -- a crashed process
      holds no live pins, which is exactly the correct outcome.
    - A missing or unreadable SESSION_META_FILENAME -- the OPPOSITE of
      run_lock.py's own "missing/corrupt = no legitimate owner = safe to
      reclaim immediately" philosophy, which would be backwards here: a
      session directory that's just now being created (use_session()
      makes the directory and writes its metadata file back-to-back,
      before any caller code runs) must never look like a safe-to-delete
      one just because this sweep happened to run in that narrow window.
    """
    removed: List[str] = []
    try:
        entries = os.listdir(paths.OUTPUT_DIR)
    except OSError:
        return removed

    now = time.time()
    for name in entries:
        session_dir = os.path.join(paths.OUTPUT_DIR, name)
        if not os.path.isdir(session_dir):
            continue
        last_active = _read_last_active(session_dir)
        if last_active is None:
            continue  # unreadable/missing metadata -- skip, don't purge
        if now - last_active < max_age_seconds:
            continue  # still fresh
        if is_session_active is not None and is_session_active(name):
            continue  # a request is currently in flight for this session
        try:
            shutil.rmtree(session_dir)
            removed.append(name)
        except OSError:
            logger.warning("Could not remove stale session directory %s.", session_dir)

    if removed:
        logger.info("Purged %d stale session director%s: %s", len(removed), "y" if len(removed) == 1 else "ies", removed)
    return removed


def purge_session(session_id: str) -> bool:
    """Immediately removes one specific session's output directory,
    regardless of its own staleness -- for an explicit "drop this
    session" action (e.g. DELETE /chat/<session_id>) rather than waiting
    for the next scheduled sweep. Returns whether a directory actually
    existed to remove.

    sanitize_session_id's own regex check still runs first (raises
    ValueError on a genuinely malformed id, same contract callers already
    rely on), but the actual join below goes through werkzeug's own
    safe_join -- the library sanitizer CodeQL's path-injection query
    actually recognizes as a barrier, unlike a hand-rolled regex
    validation -- with a realpath + prefix containment check after it as
    defense in depth, matching the pattern both ports' own
    safe_output_file_path functions already use.
    """
    sanitized = paths.sanitize_session_id(session_id)
    output_dir = os.path.realpath(paths.OUTPUT_DIR)
    joined = safe_join(output_dir, sanitized)
    if joined is None:
        return False
    session_dir = os.path.realpath(joined)
    if session_dir != output_dir and not session_dir.startswith(output_dir + os.sep):
        return False
    if not os.path.isdir(session_dir):
        return False
    try:
        shutil.rmtree(session_dir)
        return True
    except OSError:
        logger.warning("Could not remove session directory %s.", session_dir)
        return False


_purge_thread: Optional["_PurgeThread"] = None
_purge_thread_lock = threading.Lock()


class _PurgeThread:
    """One background daemon thread that runs purge_stale_sessions on a
    fixed interval for as long as it's running. Not meant to be
    constructed directly -- see start_session_purge_thread/
    stop_session_purge_thread below."""

    def __init__(self, interval_seconds: float, max_age_seconds: float, is_session_active: Optional[Callable[[str], bool]]):
        self._interval_seconds = interval_seconds
        self._max_age_seconds = max_age_seconds
        self._is_session_active = is_session_active
        self._stop_event = threading.Event()
        # daemon=True: same reasoning as run_lock.py's own _LockHeartbeat --
        # a process that exits (clean or crashed) must not be kept alive by
        # this thread alone.
        self._thread = threading.Thread(target=self._run, daemon=True, name="session-purge")
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            try:
                purge_stale_sessions(self._max_age_seconds, self._is_session_active)
            except Exception:
                logger.exception("Session purge sweep failed -- will retry on the next interval.")

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=self._interval_seconds)


def start_session_purge_thread(
    interval_seconds: float,
    max_age_seconds: float,
    is_session_active: Optional[Callable[[str], bool]] = None,
) -> None:
    """Starts a background thread that sweeps for stale session
    directories every interval_seconds, removing any untouched for at
    least max_age_seconds. Idempotent -- a second call while one is
    already running is a no-op, since a -d process only ever needs one
    of these for its whole lifetime."""
    global _purge_thread
    with _purge_thread_lock:
        if _purge_thread is not None:
            return
        _purge_thread = _PurgeThread(interval_seconds, max_age_seconds, is_session_active)


def stop_session_purge_thread() -> None:
    """Stops the running purge thread, if any. Safe to call even if one
    was never started."""
    global _purge_thread
    with _purge_thread_lock:
        thread = _purge_thread
        _purge_thread = None
    if thread is not None:
        thread.stop()
