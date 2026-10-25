"""An atomic, ownership-based lock serializing pipeline runs against the
shared output/ directory.

Both backends' generate/review pipelines share plain files in output/
(approval.json, stop_counter.json, iteration_feedback*.json,
process_data.json/design_data.json) across many separate tool calls spread
over several LLM turns -- there is no single Python call spanning a whole
run that an in-process lock could wrap. Two pipeline runs sharing the same
output/ directory can interleave their reads/writes of that shared state:
one run's stop decision can read another's approval marker, one run's
feedback mailbox can get drained by the wrong generator, one run's final
JSON can overwrite another's.

Each `-d`/detached web session now gets its own output/<session_id>/
directory (see paths.py's own docstring for use_session()), which rules
out the original motivating case here -- two DIFFERENT web sessions can no
longer share a directory at all. What's left for this lock to guard is
narrower but still real: concurrent runs WITHIN one session (e.g. a
double-submitted request, or a retried tool call racing the first attempt
that's still in flight) against that one session's own directory.

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
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Dict, Optional

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
        if age is None:
            # A valid JSON dict (not caught by the `existing is None`
            # check above) but with a missing/non-numeric "started_at" --
            # this module always writes that field itself via
            # _atomic_write's own payload, so the only way it's absent is
            # external tampering or a future schema regression. There is
            # no legitimate way to judge this lock's age, and treating
            # "unknown age" as "never stale" would contradict this
            # module's own documented self-healing guarantee (a bad lock
            # could then wedge every future run forever, exactly the
            # failure mode this module exists to prevent) -- so an
            # unreadable age is treated the same as a confirmed-stale one.
            logger.warning(
                "Lock at %s has no usable 'started_at' -- treating as stale and reclaiming it.",
                path,
            )
            _atomic_write(path, payload)
            return my_token
        if age >= stale_after_seconds:
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


# A still-genuinely-running pipeline has no single acquire_pipeline_lock
# call spanning its whole duration to keep the lock fresh -- between the
# one-time reset step that acquires it and the one-time finalize step that
# releases it, there is no guarantee ANY tool call happens often enough (or
# at all, during a long single generate/review phase, or a pause awaiting
# the next piece of user input) to naturally refresh started_at before
# DEFAULT_STALE_AFTER_SECONDS elapses. A background heartbeat closes that
# gap directly: for as long as a run holds the lock, something re-acquires
# it with the same token well before it could ever go stale, regardless of
# what the run's own tool-call cadence looks like.
_HEARTBEAT_INTERVAL_SECONDS = DEFAULT_STALE_AFTER_SECONDS / 4

_heartbeats: Dict[str, "_LockHeartbeat"] = {}
_heartbeats_lock = threading.Lock()


class _LockHeartbeat:
    """One background daemon thread that re-acquires a single pipeline
    lock token on a fixed interval, for as long as it's running. Not
    meant to be constructed directly -- see start_pipeline_lock_heartbeat/
    stop_pipeline_lock_heartbeat below."""

    def __init__(self, label: str, token: str, stale_after_seconds: float):
        self._label = label
        self._token = token
        self._stale_after_seconds = stale_after_seconds
        self._stop_event = threading.Event()
        # daemon=True: a process that exits (clean or crashed) without
        # ever calling stop_pipeline_lock_heartbeat must not be kept alive
        # by this thread alone -- the lock's own staleness fallback is what
        # reclaims an abandoned run in that case, same as before this
        # heartbeat existed.
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"pipeline-lock-heartbeat-{token[:8]}",
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS):
            try:
                acquire_pipeline_lock(self._label, token=self._token, stale_after_seconds=self._stale_after_seconds)
            except PipelineLockedError:
                # The lock on disk no longer matches this token -- e.g. it
                # was already released and reclaimed by a different run
                # (a bug elsewhere) between heartbeats. Nothing left to
                # refresh; retrying on the next tick would only be noise.
                logger.warning(
                    "Pipeline lock heartbeat for token %s could not refresh -- stopping.", self._token,
                )
                return

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=_HEARTBEAT_INTERVAL_SECONDS)


def start_pipeline_lock_heartbeat(
    label: str, token: Optional[str], stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> None:
    """Starts a background thread that keeps `token`'s lease fresh until
    stop_pipeline_lock_heartbeat(token) is called. Idempotent per token --
    a caller that's reentrantly re-acquired the SAME token it already
    holds (see acquire_pipeline_lock_for_turn's own reentrancy check) gets
    a no-op here rather than a second, redundant heartbeat thread for the
    same lock. A falsy token is also a no-op, so callers can pass whatever
    acquire_pipeline_lock_for_turn-style helper returned without an extra
    truthiness check of their own."""
    if not token:
        return
    with _heartbeats_lock:
        if token in _heartbeats:
            return
        _heartbeats[token] = _LockHeartbeat(label, token, stale_after_seconds)


def stop_pipeline_lock_heartbeat(token: Optional[str]) -> None:
    """Stops and forgets the heartbeat for `token`, if one is running.
    Safe to call with token=None or a token that never had one (e.g.
    nothing was ever acquired, or start_pipeline_lock_heartbeat was never
    reached) -- a no-op in both cases, never an error."""
    if not token:
        return
    with _heartbeats_lock:
        heartbeat = _heartbeats.pop(token, None)
    if heartbeat is not None:
        heartbeat.stop()


def peek_pipeline_lock() -> Optional[dict]:
    """Read-only: returns the current lock's raw info (label/token/
    started_at/pid) if output/ currently has one, or None if it
    doesn't. Never acquires, releases, or otherwise changes anything."""
    return _read_lock(_lock_path())


def force_clear_pipeline_lock() -> Optional[dict]:
    """Unconditionally removes the current pipeline lock (if any) and
    stops its background heartbeat, regardless of which token holds it
    or how old it is. Unlike every other function in this module, this
    does NOT check ownership first.

    Exists for an operator -- or an agent acting on an explicit, direct
    user request -- to recover from a lock that's stuck for a reason
    this module's own self-healing (DEFAULT_STALE_AFTER_SECONDS) hasn't
    caught: a still-running server process whose own background
    heartbeat (start_pipeline_lock_heartbeat) keeps re-acquiring the
    lock every few minutes for as long as that process keeps running,
    which keeps it looking fresh forever if its own release call never
    ran (e.g. a pipeline run that stopped early -- see
    process_agents.common.utils_agent.release_pipeline_lock_after_run's
    own docstring for a confirmed real case of exactly this).

    Returns the lock's info (whatever peek_pipeline_lock would have
    returned) if one was actually cleared, or None if there was nothing
    to clear -- callers should surface that info (label, age) back to
    the user, so clearing a lock is never a silent, invisible action.

    SAFETY: this does NOT check whether a pipeline genuinely still has
    an active run in flight against this lock -- that judgment call
    belongs to whoever invokes this (ultimately the user, on their own
    explicit request), not to this function. Clearing a lock a
    genuinely still-running pipeline holds can let two runs interleave
    their writes to the same output/ directory, exactly the corruption
    this module's own locking exists to prevent in the first place.
    """
    path = _lock_path()
    with _mutex_guard(path):
        existing = _read_lock(path)
        if existing is None:
            return None
        stop_pipeline_lock_heartbeat(existing.get("token"))
        try:
            os.remove(path)
        except OSError:
            pass
        return existing
