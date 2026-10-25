import json
import os
import time

import pytest

from process_toolkit import paths, session_purge
from process_toolkit.session_purge import (
    purge_session,
    purge_stale_sessions,
    start_session_purge_thread,
    stop_session_purge_thread,
)


@pytest.fixture(autouse=True)
def _stop_leftover_purge_thread():
    yield
    stop_session_purge_thread()


def _make_session(session_id: str, last_active: float, extra_file: bool = True) -> str:
    session_dir = os.path.join(paths.OUTPUT_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    with open(os.path.join(session_dir, paths.SESSION_META_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"last_active": last_active}, f)
    if extra_file:
        with open(os.path.join(session_dir, "process_data.json"), "w", encoding="utf-8") as f:
            json.dump({"steps": []}, f)
    return session_dir


def test_a_fresh_session_is_kept():
    _make_session("fresh", last_active=time.time())
    removed = purge_stale_sessions(max_age_seconds=3600)
    assert removed == []
    assert os.path.isdir(os.path.join(paths.OUTPUT_DIR, "fresh"))


def test_a_stale_session_is_removed():
    _make_session("stale", last_active=time.time() - 10_000)
    removed = purge_stale_sessions(max_age_seconds=3600)
    assert removed == ["stale"]
    assert not os.path.isdir(os.path.join(paths.OUTPUT_DIR, "stale"))


def test_only_stale_sessions_are_removed_fresh_ones_survive():
    _make_session("stale", last_active=time.time() - 10_000)
    _make_session("fresh", last_active=time.time())
    removed = purge_stale_sessions(max_age_seconds=3600)
    assert removed == ["stale"]
    assert os.path.isdir(os.path.join(paths.OUTPUT_DIR, "fresh"))


def test_a_directory_with_no_metadata_file_is_skipped_not_purged():
    # Regression guard: a session directory mid-creation (use_session()
    # makes the dir and writes metadata back-to-back) must never look
    # safe-to-delete just because a sweep happened to run in that window.
    no_meta_dir = os.path.join(paths.OUTPUT_DIR, "mid-creation")
    os.makedirs(no_meta_dir, exist_ok=True)
    removed = purge_stale_sessions(max_age_seconds=0)
    assert removed == []
    assert os.path.isdir(no_meta_dir)


def test_a_directory_with_corrupt_metadata_is_skipped_not_purged():
    corrupt_dir = os.path.join(paths.OUTPUT_DIR, "corrupt")
    os.makedirs(corrupt_dir, exist_ok=True)
    with open(os.path.join(corrupt_dir, paths.SESSION_META_FILENAME), "w", encoding="utf-8") as f:
        f.write("{not valid json")
    removed = purge_stale_sessions(max_age_seconds=0)
    assert removed == []
    assert os.path.isdir(corrupt_dir)


def test_an_active_session_is_never_purged_regardless_of_staleness():
    _make_session("in-flight", last_active=time.time() - 10_000)
    removed = purge_stale_sessions(max_age_seconds=3600, is_session_active=lambda sid: sid == "in-flight")
    assert removed == []
    assert os.path.isdir(os.path.join(paths.OUTPUT_DIR, "in-flight"))


def test_is_session_active_only_protects_the_matching_session():
    _make_session("in-flight", last_active=time.time() - 10_000)
    _make_session("abandoned", last_active=time.time() - 10_000)
    removed = purge_stale_sessions(max_age_seconds=3600, is_session_active=lambda sid: sid == "in-flight")
    assert removed == ["abandoned"]
    assert os.path.isdir(os.path.join(paths.OUTPUT_DIR, "in-flight"))


def test_non_directory_entries_in_output_dir_are_ignored():
    with open(os.path.join(paths.OUTPUT_DIR, "pipeline.lock"), "w", encoding="utf-8") as f:
        f.write("{}")
    removed = purge_stale_sessions(max_age_seconds=0)
    assert removed == []  # must not try to treat a plain file as a session directory


def test_purge_stale_sessions_on_a_missing_output_dir_is_a_safe_noop(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    original = paths.OUTPUT_DIR
    paths.OUTPUT_DIR = missing
    try:
        assert purge_stale_sessions(max_age_seconds=0) == []
    finally:
        paths.OUTPUT_DIR = original


def test_purge_session_removes_an_existing_session_immediately_regardless_of_staleness():
    _make_session("just-created", last_active=time.time())
    assert purge_session("just-created") is True
    assert not os.path.isdir(os.path.join(paths.OUTPUT_DIR, "just-created"))


def test_purge_session_on_a_nonexistent_session_returns_false():
    assert purge_session("never-existed") is False


def test_purge_session_rejects_a_malicious_id_rather_than_escaping_output_dir():
    with pytest.raises(ValueError):
        purge_session("../../etc")


def test_purge_thread_sweeps_on_its_own_interval(monkeypatch):
    _make_session("stale", last_active=time.time() - 10_000)
    start_session_purge_thread(interval_seconds=0.05, max_age_seconds=3600)
    time.sleep(0.2)
    assert not os.path.isdir(os.path.join(paths.OUTPUT_DIR, "stale"))


def test_starting_the_purge_thread_twice_is_idempotent():
    start_session_purge_thread(interval_seconds=60, max_age_seconds=3600)
    first = session_purge._purge_thread
    start_session_purge_thread(interval_seconds=60, max_age_seconds=3600)
    assert session_purge._purge_thread is first


def test_stop_purge_thread_actually_stops_sweeping():
    start_session_purge_thread(interval_seconds=0.05, max_age_seconds=3600)
    stop_session_purge_thread()
    assert session_purge._purge_thread is None

    _make_session("stale", last_active=time.time() - 10_000)
    time.sleep(0.15)
    # No sweep should have run after stop -- directory survives.
    assert os.path.isdir(os.path.join(paths.OUTPUT_DIR, "stale"))


def test_stop_purge_thread_is_a_safe_noop_when_never_started():
    stop_session_purge_thread()  # must not raise
