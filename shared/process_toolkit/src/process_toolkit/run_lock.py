"""Advisory, self-healing lock serializing pipeline runs against the
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
and raises PipelineLockedError instead of proceeding.

Two deliberate simplifications, sized for this project's actual scale (a
single-process demo/sample service, not a distributed multi-tenant one):

  - No cross-call owner identity. A pipeline's own startup sequence can
    legitimately call the "clear stale state" step more than once (e.g.
    two separate early-stage tool calls in the same turn) -- re-acquiring
    within GRACE_SECONDS of the existing lock's own timestamp is treated
    as that same run refreshing its own lock, not a conflict. A SEPARATE,
    later acquire more than GRACE_SECONDS after the current lock was
    written IS treated as a conflict and rejected.
  - No explicit release call. The lock simply expires after
    DEFAULT_STALE_AFTER_SECONDS (comfortably above this project's own
    documented ~5-10 minute typical run time), so a crashed or
    never-finished run can never permanently block future ones. The
    trade-off: a fast-finishing run's successor may have to wait out the
    remainder of that window even though the first run already finished --
    accepted in exchange for never needing to find and wire a release call
    at every possible "a run just finished" point across both backends
    (which, unlike the single shared "clear stale state" start-of-run
    step, are NOT unified between the two backends today).
"""

import json
import logging
import os
import time

from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.RunLock")

LOCK_FILENAME = "pipeline.lock"

# How close together two lock-file writes have to be to be treated as the
# SAME run refreshing its own lock (see module docstring) rather than a
# genuine conflict. Comfortably above the sub-second-to-low-single-digit-
# second gap between a pipeline's own back-to-back "clear stale state"
# calls, comfortably below any realistic gap between two independently
# user-triggered requests.
GRACE_SECONDS = 15.0

# How long an unreleased lock is honored before it's treated as abandoned
# (a crashed process, an exception that skipped every later stage) and
# silently reclaimed by the next run. Comfortably above this project's own
# documented typical run time (~5-10 minutes per the READMEs) so a normal
# run is never caught by its own lock; bounds the worst-case lockout a
# crashed/abandoned run can impose on everyone else.
DEFAULT_STALE_AFTER_SECONDS = 1200.0


class PipelineLockedError(RuntimeError):
    """Raised by acquire_pipeline_lock when a different, still-active
    pipeline run already holds the lock."""


def _lock_path() -> str:
    return paths.output_path(LOCK_FILENAME)


def acquire_pipeline_lock(label: str, stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS) -> None:
    """Call once at the start of a pipeline run -- its existing "clear
    stale state" step (reset_loop_state on the neuro-san side;
    _remove_previous_approval_logs / _reset_cloudarch_approval_state on
    the ADK side) is the right place, since every pipeline already calls
    one of those exactly once per run.

    Raises PipelineLockedError if a different, still-active run already
    holds the lock -- the caller should surface that message to the user
    rather than proceeding. Otherwise (re)writes the lock with the
    current time and `label` (a short, human-readable description of
    this run, e.g. "process pipeline", surfaced in the message a
    conflicting run's own acquire call raises).
    """
    path = _lock_path()
    now = time.time()

    existing = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = None

    if isinstance(existing, dict):
        started_at = existing.get("started_at")
        if isinstance(started_at, (int, float)):
            age = now - started_at
            if GRACE_SECONDS < age < stale_after_seconds:
                held_by = existing.get("label") or "another pipeline run"
                raise PipelineLockedError(
                    f"Another pipeline run ({held_by}) is already in progress against this "
                    f"output/ directory (started {int(age)}s ago). Running two generate/update "
                    "pipelines concurrently against the same output/ directory can corrupt each "
                    "other's state. Wait for it to finish, then retry."
                )

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"label": label, "started_at": now, "pid": os.getpid()}, f)
    except Exception:
        logger.warning("Could not persist pipeline lock for %r -- continuing without it.", label, exc_info=True)
