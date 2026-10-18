import fcntl
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from process_toolkit import paths, run_lock
from process_toolkit.run_lock import (
    DEFAULT_STALE_AFTER_SECONDS,
    _MUTEX_SUFFIX,
    _lock_path,
    acquire_pipeline_lock,
    release_pipeline_lock,
    start_pipeline_lock_heartbeat,
    stop_pipeline_lock_heartbeat,
    PipelineLockedError,
)


@pytest.fixture(autouse=True)
def _stop_leftover_heartbeats():
    # A test that starts a heartbeat but asserts/raises before stopping it
    # would otherwise leave a daemon thread running (harmless to process
    # exit, but it would keep re-acquiring a lock tests after it no
    # longer exist for) -- clean up anything left in the registry after
    # every test regardless of how it ended.
    yield
    for token in list(run_lock._heartbeats):
        stop_pipeline_lock_heartbeat(token)


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


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_mutex_held_by_a_crashed_process_does_not_block_a_later_acquire():
    # Directly proves the crash-safety property the flock-based mutex
    # exists for: a process that dies mid-critical-section (simulated
    # here via os.fork + os._exit, which skips every Python-level
    # cleanup including the mutex's own "finally: flock(LOCK_UN)") must
    # not leave the mutex held -- the kernel releases it the instant the
    # holding process's file descriptors close, for any reason. A
    # sentinel-file-existence mutex (the design this replaced) would
    # instead leave a permanently-locked file here, recoverable only by
    # waiting out an arbitrary staleness window.
    mutex_path = _lock_path() + _MUTEX_SUFFIX

    pid = os.fork()
    if pid == 0:
        # Child: acquire the mutex and die without releasing it or
        # running any other cleanup.
        fd = os.open(mutex_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os._exit(0)

    os.waitpid(pid, 0)  # child has now fully exited

    start = time.time()
    acquire_pipeline_lock("a pipeline in the parent")  # must not raise or hang
    assert time.time() - start < 1.0, "acquire waited as if the mutex were still held"


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
    assert len(successes) == 1, f"expected exactly one winner, got {results}"
    assert len(results) == 16


def test_heartbeat_keeps_a_lock_from_going_stale(monkeypatch):
    # The whole reason this exists: between a pipeline's one-time reset
    # step (acquire) and its own finalize step (release), there is no
    # guarantee any tool call happens often enough on its own to refresh
    # started_at -- a long single generate/review phase, or a pause
    # awaiting the next piece of user input, could otherwise outlast
    # DEFAULT_STALE_AFTER_SECONDS. A fast interval here stands in for
    # that real, much longer gap.
    monkeypatch.setattr(run_lock, "_HEARTBEAT_INTERVAL_SECONDS", 0.05)
    token = acquire_pipeline_lock("a long-running pipeline")
    before = run_lock._read_lock(_lock_path())["started_at"]

    start_pipeline_lock_heartbeat("a long-running pipeline", token)
    time.sleep(0.2)

    after = run_lock._read_lock(_lock_path())["started_at"]
    assert after > before
    assert run_lock._read_lock(_lock_path())["token"] == token  # still this run's own lock


def test_starting_a_heartbeat_twice_for_the_same_token_is_idempotent(monkeypatch):
    monkeypatch.setattr(run_lock, "_HEARTBEAT_INTERVAL_SECONDS", 60.0)
    token = acquire_pipeline_lock("my pipeline")
    start_pipeline_lock_heartbeat("my pipeline", token)
    first = run_lock._heartbeats[token]

    start_pipeline_lock_heartbeat("my pipeline", token)  # reentrant re-acquire within the same run
    assert run_lock._heartbeats[token] is first  # no second thread/entry


def test_stop_heartbeat_actually_stops_refreshing(monkeypatch):
    monkeypatch.setattr(run_lock, "_HEARTBEAT_INTERVAL_SECONDS", 0.05)
    token = acquire_pipeline_lock("a pipeline")
    start_pipeline_lock_heartbeat("a pipeline", token)
    time.sleep(0.15)
    stop_pipeline_lock_heartbeat(token)
    assert token not in run_lock._heartbeats

    after_stop = run_lock._read_lock(_lock_path())["started_at"]
    time.sleep(0.15)
    still = run_lock._read_lock(_lock_path())["started_at"]
    assert still == after_stop  # no further refreshes once stopped


def test_stop_heartbeat_is_a_safe_noop_for_none_or_unknown_token():
    stop_pipeline_lock_heartbeat(None)  # must not raise
    stop_pipeline_lock_heartbeat("a-token-with-no-heartbeat")  # must not raise


def test_start_heartbeat_is_a_safe_noop_for_a_falsy_token():
    start_pipeline_lock_heartbeat("a pipeline", None)  # must not raise
    assert None not in run_lock._heartbeats
