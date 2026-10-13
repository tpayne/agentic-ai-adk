"""Regression coverage for the pipeline-run lock (process_toolkit.run_lock)
wired into each create/update pipeline's existing "clear stale state" step.
Verifies, without needing a live LLM, that a genuinely concurrent second
run is refused instead of silently clobbering the first run's state.
"""

import json
import os
import time

import pytest

from process_toolkit import paths
from process_toolkit.run_lock import GRACE_SECONDS


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    os.makedirs("output", exist_ok=True)
    yield tmp_path


def _write_conflicting_lock(label: str = "an earlier run") -> None:
    with open(paths.output_path("pipeline.lock"), "w", encoding="utf-8") as f:
        json.dump({"label": label, "started_at": time.time() - (GRACE_SECONDS + 1), "pid": 1}, f)


def test_process_analysis_log_metadata_refuses_when_locked():
    from process_agents.process.analysis_agent import log_analysis_metadata

    _write_conflicting_lock("the design document pipeline")
    result = log_analysis_metadata("Retail", 3)
    assert result.startswith("ERROR:")
    assert "the design document pipeline" in result


def test_process_analysis_record_request_refuses_when_locked():
    from process_agents.process.analysis_agent import record_analysis_request

    _write_conflicting_lock("the cloud architecture pipeline")
    result = record_analysis_request("design a vendor onboarding process")
    assert result.startswith("ERROR:")


def test_process_analysis_succeeds_with_no_conflicting_lock():
    from process_agents.process.analysis_agent import log_analysis_metadata

    result = log_analysis_metadata("Retail", 3)
    assert not result.startswith("ERROR:")
    assert "Retail" in result


def test_design_doc_analysis_log_metadata_refuses_when_locked():
    from process_agents.design.design_doc_analysis_agent import log_analysis_metadata

    _write_conflicting_lock("the process pipeline")
    result = log_analysis_metadata("Payments", 2)
    assert result.startswith("ERROR:")
    assert "the process pipeline" in result


def test_design_doc_analysis_succeeds_with_no_conflicting_lock():
    from process_agents.design.design_doc_analysis_agent import log_analysis_metadata

    result = log_analysis_metadata("Payments", 2)
    assert not result.startswith("ERROR:")


def test_cloudarch_reset_short_circuits_with_content_when_locked():
    from process_agents.cloudarch.cloudarch_pipeline_agent import _reset_cloudarch_approval_state

    _write_conflicting_lock("the process pipeline")
    result = _reset_cloudarch_approval_state()

    assert result is not None
    assert result.role == "model"
    assert "the process pipeline" in result.parts[0].text


def test_cloudarch_reset_proceeds_normally_with_no_conflicting_lock():
    from process_agents.cloudarch.cloudarch_pipeline_agent import _reset_cloudarch_approval_state

    assert _reset_cloudarch_approval_state() is None


def test_two_different_pipelines_cannot_run_concurrently_end_to_end():
    # The actual risk this guards against: one pipeline's own first reset
    # call locks out a second, different pipeline's own first reset call
    # made moments later (simulating a second concurrent request), rather
    # than both proceeding and interleaving writes to the same output/
    # directory.
    from process_agents.process.analysis_agent import log_analysis_metadata as process_reset
    from process_agents.design.design_doc_analysis_agent import log_analysis_metadata as design_reset

    first = process_reset("Retail", 3)
    assert not first.startswith("ERROR:")

    # Simulate enough elapsed time that the second call is unambiguously a
    # DIFFERENT, later request rather than the same run's own reentrant
    # reset -- see run_lock's GRACE_SECONDS.
    lock_path = paths.output_path("pipeline.lock")
    with open(lock_path, "r", encoding="utf-8") as f:
        lock_state = json.load(f)
    lock_state["started_at"] -= (GRACE_SECONDS + 1)
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(lock_state, f)

    second = design_reset("Payments", 2)
    assert second.startswith("ERROR:")
    assert "the process pipeline" in second
