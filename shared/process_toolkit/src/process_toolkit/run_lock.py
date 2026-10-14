"""An atomic, ownership-based lock serializing pipeline runs against the
shared output/ directory.

Both backends' generate/review pipelines share plain files in output/
(approval.json, stop_counter.json, iteration_feedback*.json,
process_data.json/design_data.json) across many separate tool calls spread
over several LLM turns -- there is no single Python call spanning a whole
run that an in-process lock could wrap. Two pipelines running concurrently
against the same output/ directory (e.g. two ADK web sessions, or an ADK
and a neuro-san process pointed at the same directory) can interleave
their reads/writes of that shared state: one run's stop decision can read
another's approval marker, one run's feedback mailbox can get drained by
the wrong generator, one run's final JSON can overwrite another's.

This makes that fail loudly instead of silently corrupting data: every
pipeline's existing "clear stale state" step (already called once, at the
start of every create/update run, on both backends) acquires this lock; a
concurrent second run's own start-of-pipeline call sees it already held
and raises PipelineLockedError instead of proceeding. Each pipeline's own
genuine finalize step releases it.

Design notes:

  - Ownership, not elapsed time. acquire_pipeline_lock returns an opaque
    token; a caller that needs to re-acquire from a LATER, separate tool
    call within the SAME logical run (e.g. ADK's analysis agents make two
    separate tool calls early in one turn that both need to clear/claim
    state) passes that same token back in, so it's recognized as the same
    run's own refresh regardless of how much time has passed between the
    two calls -- not inferred from how close together they happened to
    run. A DIFFERENT token (or none) always means a different run, and is
    rejected unless the existing lock has gone stale.
  - A true OS-level mutex (fcntl.flock) serializes the read-decide-write
    sequence. Deciding "is the existing lock mine / stale / someone
    else's active one" and then writing a new state is NOT atomic as a
    single filesystem operation, so it's wrapped in _mutex_guard, which
    holds an exclusive flock on a separate sentinel file
    (LOCK_FILENAME + ".mutex") for the duration. flock is tied to the
    holding process's open file descriptor: the kernel releases it the
    instant that process exits or dies, for ANY reason, including a hard
    kill -- unlike a sentinel-file-existence mutex (an earlier version of
    this module used exactly that), there is no staleness window to
    judge and no "steal an abandoned mutex" logic needed at all, which
    means there's no equivalent of the very race this mutex exists to
    close one level up: two callers can never both end up believing they
    hold it. POSIX-only (this project's CI and Docker images are both
    Linux; no Windows target).
  - Every write to the real lock file goes through a temp-file-then-
    os.replace swap, which is atomic -- a crash mid-write can never leave
    the lock file itself observably truncated or holding half-written
    JSON for a later reader to choke on.
  - Self-healing. A crashed or never-finished run's lock expires after
    DEFAULT_STALE_AFTER_SECONDS (comfortably above this project's own
    documented ~5-10 minute typical run time) and is then reclaimable by
    anyone, so a missed release call can never permanently wedge every
    future run.
"""

import fcntl
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.RunLock")

LOCK_FILENAME = "pipeline.lock"
_MUTEX_SUFFIX = ".mutex"

# How long an unreleased lock is honored before it's treated as abandoned
# (a crashed process, an exception that skipped the release step) and
# reclaimable by anyone. Comfortably above this project's own documented
# typical run time (~5-10 minutes per the READMEs) so a normal run is
# never caught by its own lock; bounds the worst-case lockout a
# crashed/abandoned run can impose on everyone else.
DEFAULT_STALE_AFTER_SECONDS = 1200.0

# How long a caller waits to claim the mutex before giving up. The
# critical section it guards is pure local file I/O (microseconds to low
# milliseconds), so this only ever matters under heavy contention from
# many callers queued at once -- generous relative to that, tiny relative
# to DEFAULT_STALE_AFTER_SECONDS. Unlike a sentinel-file mutex, this bound
# is purely a safety margin, not a correctness mechanism -- a crashed
# holder's flock is released by the kernel immediately, so this timeout
# only ever fires under genuine, unexpected contention.
_MUTEX_ACQUIRE_TIMEOUT_SECONDS = 10.0
_MUTEX_POLL_INTERVAL_SECONDS = 0.02


class PipelineLockedError(RuntimeError):
    """Raised by acquire_pipeline_lock when a different, still-active
    pipeline run already holds the lock."""


def _lock_path() -> str:
    return paths.output_path(LOCK_FILENAME)


def _read_lock(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _atomic_write(path: str, payload: dict) -> None:
    """Writes `payload` to `path` via a temp-file-then-os.replace swap, so
    a reader can never observe `path` partially written -- it's always
    either the previous complete content or the new complete content."""
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


@contextmanager
def _mutex_guard(path: str):
    """Serializes the read-decide-write critical section in
    acquire_pipeline_lock/release_pipeline_lock across callers (processes
    or threads) -- see this module's own docstring for why that sequence
    isn't safe as plain, unsynchronized file operations, and why this
    uses a real OS advisory lock (fcntl.flock) rather than a second
    sentinel-file-existence mutex: a crashed holder's flock is released
    by the kernel the instant its process dies, so there's no staleness
    window to judge and nothing to "steal" -- the exact shape of race
    this mutex exists to close one level up for the real lock file."""
    mutex_path = path + _MUTEX_SUFFIX
    fd = os.open(mutex_path, os.O_CREAT | os.O_RDWR)
    try:
        deadline = time.time() + _MUTEX_ACQUIRE_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise PipelineLockedError(
                        "Could not acquire the pipeline lock's internal mutex -- the "
                        "system is under unusually heavy concurrent load. Please retry."
                    )
                time.sleep(_MUTEX_POLL_INTERVAL_SECONDS)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def acquire_pipeline_lock(
    label: str,
    token: Optional[str] = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> str:
    """Call at the start of a pipeline run -- its existing "clear stale
    state" step (reset_loop_state on the neuro-san side;
    _remove_previous_approval_logs / _reset_cloudarch_approval_state on
    the ADK side) is the right place, since every pipeline already calls
    one of those exactly once (or, for ADK's two create pipelines, twice
    in quick succession -- see `token` below) per run.

    Returns the token now holding the lock. If `token` is omitted, a new
    one is minted. If a LATER call from the same logical run needs to
    re-acquire (there is no single Python call spanning a whole pipeline
    run to hold a lock across), pass the token this function returned
    the first time -- e.g. via tool_context.state / neuro-san's sly_data,
    both of which persist across separate tool calls within one session.
    Re-acquiring with a matching token always succeeds, regardless of
    how much time has passed.

    Raises PipelineLockedError if a DIFFERENT, still-active run already
    holds the lock (no token given, or a token that doesn't match) --
    the caller should surface that message to the user rather than
    proceeding.
    """
    path = _lock_path()
    my_token = token or uuid.uuid4().hex
    payload = {"label": label, "token": my_token, "started_at": time.time(), "pid": os.getpid()}

    with _mutex_guard(path):
        existing = _read_lock(path)

        if existing is None:
            # Absent, or unreadable/corrupt (e.g. a crash mid-write from
            # before this module started writing via _atomic_write) --
            # either way there is no legitimate current owner, so this is
            # safe to (re)create. Safe under the mutex: no other caller
            # can be inside this same critical section concurrently.
            _atomic_write(path, payload)
            return my_token

        if existing.get("token") == my_token:
            _atomic_write(path, payload)
            return my_token

        started_at = existing.get("started_at")
        age = time.time() - started_at if isinstance(started_at, (int, float)) else None
        if age is not None and age >= stale_after_seconds:
            # Abandoned by its original owner -- safe to reclaim under
            # the mutex: no concurrent reader/writer of the real lock
            # file can observe or race this decision.
            _atomic_write(path, payload)
            return my_token

        held_by = existing.get("label") or "another pipeline run"
        raise PipelineLockedError(
            f"Another pipeline run ({held_by}) is already in progress against this "
            "output/ directory. Running two generate/update pipelines concurrently "
            "against the same output/ directory can corrupt each other's state. "
            "Wait for it to finish, then retry."
        )


def release_pipeline_lock(token: Optional[str]) -> None:
    """Removes the lock ONLY if it's currently held by `token`. Safe to
    call unconditionally (including with token=None, e.g. a network that
    never called acquire_pipeline_lock in the first place) -- a release
    that doesn't match whatever is actually on disk is a no-op, never a
    removal of a different, genuinely active run's lock."""
    if not token:
        return
    path = _lock_path()
    with _mutex_guard(path):
        existing = _read_lock(path)
        if existing is not None and existing.get("token") == token:
            try:
                os.remove(path)
            except OSError:
                pass
