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
  - Atomic claim. The "nobody holds it yet" case is claimed with
    os.O_CREAT | os.O_EXCL, which is atomic on POSIX and Windows -- two
    callers racing to acquire with no existing lock can never both
    "win"; the loser immediately sees the winner's lock on its very next
    read and goes through the normal conflict/staleness path instead.
    Reclaiming an abandoned (stale) lock uses the same primitive (remove,
    then re-claim with O_EXCL) rather than an unconditional overwrite, so
    two callers racing to reclaim the SAME stale lock also can't both
    "win" silently.
  - Self-healing. A crashed or never-finished run's lock expires after
    DEFAULT_STALE_AFTER_SECONDS (comfortably above this project's own
    documented ~5-10 minute typical run time) and is then reclaimable by
    anyone, so a missed release call can never permanently wedge every
    future run.
"""

import json
import logging
import os
import time
import uuid
from typing import Optional

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.RunLock")

LOCK_FILENAME = "pipeline.lock"

# How long an unreleased lock is honored before it's treated as abandoned
# (a crashed process, an exception that skipped the release step) and
# reclaimable by anyone. Comfortably above this project's own documented
# typical run time (~5-10 minutes per the READMEs) so a normal run is
# never caught by its own lock; bounds the worst-case lockout a
# crashed/abandoned run can impose on everyone else.
DEFAULT_STALE_AFTER_SECONDS = 1200.0

# Bounds the "remove a stale lock, then re-claim it" retry loop below --
# only matters if multiple callers race to reclaim the exact same stale
# lock at once; one retry is enough for all but a pathological, repeated
# collision, which this caps rather than risking unbounded recursion.
_MAX_RECLAIM_ATTEMPTS = 3


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


def _try_claim(path: str, payload: dict) -> bool:
    """Atomically creates `path` with `payload` iff it doesn't already
    exist. Returns False (without raising) if it does -- the normal,
    expected outcome of losing a race, not an error."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        os.write(fd, json.dumps(payload).encode("utf-8"))
    finally:
        os.close(fd)
    return True


def _refresh(path: str, payload: dict) -> None:
    """Rewrites a lock this caller already confirmed it owns. Not the
    atomic claim primitive -- used only for a same-token refresh, where
    there is no "nobody else could have already claimed it" question to
    resolve, just a timestamp update."""
    try:
        tmp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, path)
    except Exception:
        logger.warning("Could not refresh pipeline lock -- continuing anyway.", exc_info=True)


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

    for _ in range(_MAX_RECLAIM_ATTEMPTS):
        payload = {"label": label, "token": my_token, "started_at": time.time(), "pid": os.getpid()}

        if _try_claim(path, payload):
            return my_token

        existing = _read_lock(path)
        if existing is None:
            # Unreadable/corrupt, or removed between our failed claim and
            # this read -- treat as absent and retry the atomic claim.
            continue

        if existing.get("token") == my_token:
            _refresh(path, payload)
            return my_token

        started_at = existing.get("started_at")
        age = time.time() - started_at if isinstance(started_at, (int, float)) else None
        if age is not None and age >= stale_after_seconds:
            # Abandoned by its original owner -- reclaim it via the same
            # atomic primitive (remove, then re-claim) rather than an
            # unconditional overwrite, so a second caller racing to
            # reclaim this exact same stale lock can't also "win".
            try:
                os.remove(path)
            except OSError:
                pass
            continue

        held_by = existing.get("label") or "another pipeline run"
        raise PipelineLockedError(
            f"Another pipeline run ({held_by}) is already in progress against this "
            "output/ directory. Running two generate/update pipelines concurrently "
            "against the same output/ directory can corrupt each other's state. "
            "Wait for it to finish, then retry."
        )

    # Exhausted retries racing other reclaimers -- fail safe (refuse)
    # rather than silently proceeding unlocked.
    raise PipelineLockedError(
        "Could not acquire the pipeline lock after repeated attempts -- another run "
        "may be starting at the same time. Please retry."
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
    existing = _read_lock(path)
    if existing is not None and existing.get("token") == token:
        try:
            os.remove(path)
        except OSError:
            pass
