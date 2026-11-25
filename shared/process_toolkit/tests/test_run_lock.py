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
    peek_pipeline_lock,
    force_clear_pipeline_lock,
    PipelineLockedError,
)


@pytest.fixture(autouse=True)
def _stop_leftover_heartbeats():
    # Clean up anything left in the registry after every test regardless of how it ended.
    yield
    for token in list(run_lock._heartbeats):
        stop_pipeline_lock_heartbeat(token)
    run_lock._session_locks.clear()


def _write_lock(started_at: float, label: str = "an earlier run", token: str = "someone-elses-token") -> None:
    key = run_lock.current_session_key()
    with run_lock._mem_lock:
        run_lock._session_locks[key] = {
            "label": label,
            "started_at": started_at,
            "pid": 1,
            "token": token,
            "session_key": key,
        }


def test_first_acquire_succeeds_with_no_existing_lock():
    token = acquire_pipeline_lock("my pipeline")
    assert token


def test_reacquiring_with_the_same_token_always_succeeds_regardless_of_elapsed_time():
    token = acquire_pipeline_lock("my pipeline")
    time.sleep(0.05)
    assert acquire_pipeline_lock("my pipeline", token=token) == token


def test_a_different_token_is_rejected_even_moments_later():
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


def test_a_corrupt_lock_is_recovered_not_permanently_stuck():
    key = run_lock.current_session_key()
    with run_lock._mem_lock:
        run_lock._session_locks[key] = {"label": "corrupt", "started_at": "not-a-number", "token": "corrupt"}
    acquire_pipeline_lock("a new pipeline")  # must not raise


def test_concurrent_stale_reclaim_attempts_let_exactly_one_caller_win():
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


def test_processes_do_not_share_lock_state_at_all():
    # CONFIRMED AS A REAL REGRESSION IN TEST COVERAGE (now fixed): this
    # test used to be test_mutex_held_by_a_crashed_process_does_not_block_
    # a_later_acquire, directly proving the OLD flock-based design's
    # cross-process crash-safety (the kernel releases a dead process's
    # flock immediately, so a crashed holder could never wedge a later
    # acquire). It was replaced with a version that only forked a child
    # doing nothing at all -- true, but trivially so, and it proved
    # nothing about THIS design's own actual behavior.
    #
    # The honest property of the CURRENT in-memory design is the opposite
    # of a safety guarantee: it's a documented LIMITATION (see run_lock.py's
    # own module docstring) that two processes share NO lock state
    # whatsoever. This proves that directly, via the literal mechanism
    # behind it -- os.fork() gives the child a private COPY of
    # _session_locks at fork time, so the child's own release() only ever
    # clears its own copy and can never reach back into the parent's.
    token = acquire_pipeline_lock("the parent's own pipeline")

    pid = os.fork()
    if pid == 0:
        # Child: inherited a snapshot of the parent's lock at fork time.
        # Releasing it here only clears the CHILD's own in-memory copy.
        release_pipeline_lock(token)
        os._exit(0)
    os.waitpid(pid, 0)

    # The parent's own lock is completely untouched by the child's
    # release -- a different token is still rejected here.
    start = time.time()
    with pytest.raises(PipelineLockedError):
        acquire_pipeline_lock("a different pipeline")
    assert time.time() - start < 1.0  # rejected immediately, not after waiting out a staleness window

    release_pipeline_lock(token)
    acquire_pipeline_lock("a different pipeline")  # now genuinely free


def test_concurrent_acquire_attempts_let_exactly_one_caller_win():
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


def test_peek_returns_none_when_nothing_is_held():
    assert peek_pipeline_lock() is None


def test_peek_returns_the_held_locks_info_without_releasing_it():
    acquire_pipeline_lock("a pipeline")
    info = peek_pipeline_lock()
    assert info["label"] == "a pipeline"
    # Still held -- peek must not have released it.
    with pytest.raises(PipelineLockedError):
        acquire_pipeline_lock("a different pipeline")


def test_force_clear_removes_a_held_lock_and_returns_its_info():
    acquire_pipeline_lock("a stuck pipeline")

    cleared = force_clear_pipeline_lock()

    assert cleared["label"] == "a stuck pipeline"
    acquire_pipeline_lock("a different pipeline")  # must not raise -- genuinely released


def test_force_clear_is_a_safe_noop_when_nothing_is_held():
    assert force_clear_pipeline_lock() is None


def test_force_clear_also_stops_the_lock_heartbeat():
    token = acquire_pipeline_lock("a pipeline")
    start_pipeline_lock_heartbeat("a pipeline", token)
    assert token in run_lock._heartbeats

    force_clear_pipeline_lock()

    assert token not in run_lock._heartbeats


def test_force_clear_does_not_check_which_token_holds_it():
    acquire_pipeline_lock("someone else's pipeline")
    cleared = force_clear_pipeline_lock()
    assert cleared["label"] == "someone else's pipeline"
    assert peek_pipeline_lock() is None


def test_different_web_sessions_do_not_block_each_other():
    with paths.use_session("session_1"):
        tok1 = acquire_pipeline_lock("pipeline in s1")
        assert tok1

    with paths.use_session("session_2"):
        tok2 = acquire_pipeline_lock("pipeline in s2")
        assert tok2


def test_same_web_session_rejects_concurrent_different_pipeline():
    with paths.use_session("session_1"):
        acquire_pipeline_lock("pipeline 1 in s1")
        with pytest.raises(PipelineLockedError):
            acquire_pipeline_lock("pipeline 2 in s1")


def test_cli_session_key_format(monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT_DIR", "output")
    key = run_lock.current_session_key()
    assert key.startswith("cli_")


def test_release_pipeline_lock_stops_heartbeat():
    token = acquire_pipeline_lock("a pipeline")
    start_pipeline_lock_heartbeat("a pipeline", token)
    assert token in run_lock._heartbeats

    release_pipeline_lock(token)
    assert token not in run_lock._heartbeats


def test_acquire_and_release_emits_logs(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="ProcessArchitect.RunLock"):
        token = acquire_pipeline_lock("test-logger-pipeline")
        assert any("acquire_pipeline_lock" in record.message for record in caplog.records)
        release_pipeline_lock(token)
        assert any("release_pipeline_lock" in record.message for record in caplog.records)


def test_refresh_pipeline_lock_extends_lease():
    token = acquire_pipeline_lock("a pipeline")
    assert run_lock.refresh_pipeline_lock(token) is True
    release_pipeline_lock(token)
    assert run_lock.refresh_pipeline_lock(token) is False


def test_heartbeat_stops_when_lock_released():
    token = acquire_pipeline_lock("a pipeline")
    start_pipeline_lock_heartbeat("a pipeline", token)
    heartbeat = run_lock._heartbeats.get(token)
    assert heartbeat is not None
    assert heartbeat._thread.is_alive()

    release_pipeline_lock(token)
    assert token not in run_lock._heartbeats
    assert not heartbeat._thread.is_alive()

