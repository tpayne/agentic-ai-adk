import json
import time

import pytest

from process_toolkit import paths
from process_toolkit.run_lock import (
    GRACE_SECONDS,
    acquire_pipeline_lock,
    PipelineLockedError,
)


def _write_lock(started_at: float, label: str = "an earlier run") -> None:
    with open(paths.output_path("pipeline.lock"), "w", encoding="utf-8") as f:
        json.dump({"label": label, "started_at": started_at, "pid": 1}, f)


def test_first_acquire_succeeds_with_no_existing_lock():
    acquire_pipeline_lock("my pipeline")  # must not raise


def test_reacquiring_within_the_grace_window_is_treated_as_the_same_run():
    # Mirrors the real case this is for: a single pipeline run's own
    # startup sequence calls the reset/acquire step more than once (e.g.
    # two separate early-stage tool calls in the same turn).
    acquire_pipeline_lock("my pipeline")
    acquire_pipeline_lock("my pipeline")  # must not raise


def test_a_lock_older_than_the_grace_window_blocks_a_different_run():
    _write_lock(started_at=time.time() - (GRACE_SECONDS + 1))
    with pytest.raises(PipelineLockedError) as excinfo:
        acquire_pipeline_lock("a different pipeline")
    assert "an earlier run" in str(excinfo.value)


def test_a_stale_lock_is_silently_reclaimed():
    from process_toolkit.run_lock import DEFAULT_STALE_AFTER_SECONDS
    _write_lock(started_at=time.time() - (DEFAULT_STALE_AFTER_SECONDS + 1))
    acquire_pipeline_lock("a new pipeline")  # must not raise -- old lock has expired


def test_custom_stale_after_seconds_extends_the_staleness_window():
    # A lock past the default staleness window would normally be reclaimed
    # silently -- a caller that knows its own runs can legitimately take
    # longer can pass a bigger stale_after_seconds to keep it honored.
    from process_toolkit.run_lock import DEFAULT_STALE_AFTER_SECONDS
    age = DEFAULT_STALE_AFTER_SECONDS + 5
    _write_lock(started_at=time.time() - age)

    acquire_pipeline_lock("a new pipeline")  # default window: reclaimed, no raise

    _write_lock(started_at=time.time() - age)
    with pytest.raises(PipelineLockedError):
        acquire_pipeline_lock("a different pipeline", stale_after_seconds=age + 60)
