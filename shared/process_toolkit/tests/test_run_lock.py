import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from process_toolkit import paths
from process_toolkit.run_lock import (
    DEFAULT_STALE_AFTER_SECONDS,
    acquire_pipeline_lock,
    release_pipeline_lock,
    PipelineLockedError,
)


def _write_lock(started_at: float, label: str = "an earlier run", token: str = "someone-elses-token") -> None:
    with open(paths.output_path("pipeline.lock"), "w", encoding="utf-8") as f:
        json.dump({"label": label, "started_at": started_at, "pid": 1, "token": token}, f)


def test_first_acquire_succeeds_with_no_existing_lock():
    token = acquire_pipeline_lock("my pipeline")
    assert token


def test_reacquiring_with_the_same_token_always_succeeds_regardless_of_elapsed_time():
    # Mirrors the real case this is for: a single pipeline run's own
    # startup sequence calls the acquire step more than once (e.g. two
    # separate early-stage tool calls in the same turn), potentially with
    # a real gap between them -- ownership, not timing, is what matters.
    token = acquire_pipeline_lock("my pipeline")
    time.sleep(0.05)
    assert acquire_pipeline_lock("my pipeline", token=token) == token


def test_a_different_token_is_rejected_even_moments_later():
    # Regression test: the previous time-based design let ANY second
    # acquire within a short grace window through, same-run or not. A
    # genuinely different run (different/no token) must be rejected
    # immediately -- not after some elapsed-time threshold.
    acquire_pipeline_lock("my pipeline")
    with pytest.raises(PipelineLockedError):
        acquire_pipeline_lock("a different pipeline")


def test_a_stale_lock_is_reclaimed():
    _write_lock(started_at=time.time() - (DEFAULT_STALE_AFTER_SECONDS + 1))
    acquire_pipeline_lock("a new pipeline")  # must not raise -- old lock has expired


def test_custom_stale_after_seconds_extends_the_staleness_window():
    age = DEFAULT_STALE_AFTER_SECONDS + 5
    _write_lock(started_at=time.time() - age)
    with pytest.raises(PipelineLockedError):
        acquire_pipeline_lock("a different pipeline", stale_after_seconds=age + 60)


def test_release_removes_a_lock_held_by_the_matching_token():
    token = acquire_pipeline_lock("my pipeline")
    release_pipeline_lock(token)
    acquire_pipeline_lock("a different pipeline")  # must not raise -- lock is gone


def test_release_with_a_non_matching_token_is_a_no_op():
    acquire_pipeline_lock("my pipeline")
    release_pipeline_lock("not-the-real-token")
    with pytest.raises(PipelineLockedError):
        acquire_pipeline_lock("a different pipeline")


def test_release_with_none_is_a_safe_no_op():
    release_pipeline_lock(None)  # must not raise, even with no lock present
    acquire_pipeline_lock("my pipeline")


def test_a_corrupt_lock_file_is_recovered_not_permanently_stuck():
    # Regression test: a crash mid-write (before this module wrote via
    # os.replace, or any other way a non-JSON/garbage file ends up at
    # this path) must not permanently block every future acquire --
    # there's no "started_at" to ever judge as stale, so it has to be
    # recognized as having no legitimate owner at all.
    with open(paths.output_path("pipeline.lock"), "w", encoding="utf-8") as f:
        f.write("{not valid json")

    acquire_pipeline_lock("a new pipeline")  # must not raise


def test_concurrent_stale_reclaim_attempts_let_exactly_one_caller_win():
    # Regression test: the previous design read a stale lock, then
    # unconditionally os.remove'd whatever was at that path -- if another
    # caller had already reclaimed it in the gap, the first caller's
    # remove would delete the NEW legitimate owner's lock too, and both
    # would believe they held it exclusively. Many callers racing to
    # reclaim the SAME stale lock must still produce exactly one winner.
    _write_lock(started_at=time.time() - (DEFAULT_STALE_AFTER_SECONDS + 1))

    results = []

    def _attempt(i):
        try:
            acquire_pipeline_lock(f"pipeline {i}")
            return ("ok", i)
        except PipelineLockedError:
            return ("locked", i)

    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(_attempt, range(16)):
            results.append(result)

    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) == 1, f"expected exactly one winner reclaiming the stale lock, got {successes}"


def test_concurrent_acquire_attempts_let_exactly_one_caller_win():
    # Directly exercises the race the time-based design couldn't rule
    # out: many callers hitting acquire_pipeline_lock at effectively the
    # same instant, with no existing lock, must still result in exactly
    # one winner -- not "whoever happened to write last" and not several
    # simultaneous "successes".
    results = []

    def _attempt(i):
        try:
            acquire_pipeline_lock(f"pipeline {i}")
            return ("ok", i)
        except PipelineLockedError:
            return ("locked", i)

    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(_attempt, range(16)):
            results.append(result)

    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) == 1, f"expected exactly one winner, got {successes}"
    assert len(results) == 16
