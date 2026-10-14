"""Regression coverage for the pipeline-run lock (process_toolkit.run_lock)
wired into each create/update pipeline's existing "clear stale state" step
(acquire) and its own genuine last step (release). Verifies, without
needing a live LLM, that a genuinely concurrent second run is refused
instead of silently clobbering the first run's state, and that a run that
actually finishes releases its own lock rather than blocking the next one
for the full staleness window.
"""

import json
import os
import time
import uuid
from types import SimpleNamespace

import pytest

from process_toolkit import paths
from process_toolkit.run_lock import acquire_pipeline_lock


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    os.makedirs("output", exist_ok=True)
    yield tmp_path


def _fake_context(state=None, invocation_id=None):
    """Minimal stand-in for ADK's ToolContext/CallbackContext -- the lock
    wiring only ever does context.state.get(...)/[...] = ... (a plain
    dict satisfies exactly) and reads context.invocation_id. Defaults to
    a FRESH invocation_id per call, matching a new top-level run_async()
    per turn; pass a shared `state` dict (but a different invocation_id)
    to model two different turns in the SAME chat session."""
    return SimpleNamespace(state=state if state is not None else {}, invocation_id=invocation_id or uuid.uuid4().hex)


def _write_conflicting_lock(label: str = "an earlier run") -> None:
    with open(paths.output_path("pipeline.lock"), "w", encoding="utf-8") as f:
        json.dump({"label": label, "started_at": time.time(), "token": "someone-elses-token", "pid": 1}, f)


def test_process_analysis_log_metadata_refuses_when_locked():
    from process_agents.process.analysis_agent import log_analysis_metadata

    _write_conflicting_lock("the design document pipeline")
    result = log_analysis_metadata("Retail", 3, tool_context=_fake_context())
    assert result.startswith("ERROR:")
    assert "the design document pipeline" in result


def test_process_analysis_record_request_refuses_when_locked():
    from process_agents.process.analysis_agent import record_analysis_request

    _write_conflicting_lock("the cloud architecture pipeline")
    result = record_analysis_request("design a vendor onboarding process", tool_context=_fake_context())
    assert result.startswith("ERROR:")


def test_process_analysis_succeeds_with_no_conflicting_lock():
    from process_agents.process.analysis_agent import log_analysis_metadata

    result = log_analysis_metadata("Retail", 3, tool_context=_fake_context())
    assert not result.startswith("ERROR:")
    assert "Retail" in result


def test_process_analysis_reentrant_calls_share_one_token_via_tool_context_state():
    # Mirrors the real call pattern: record_analysis_request and
    # log_analysis_metadata both call the same reset step, moments apart,
    # within the SAME turn -- sharing one tool_context (and therefore one
    # invocation_id) means the second call recognizes the first's own
    # lock instead of conflicting with it.
    from process_agents.process.analysis_agent import log_analysis_metadata, record_analysis_request
    from process_agents.common.utils_agent import PIPELINE_LOCK_TOKEN_STATE_KEY

    ctx = _fake_context()
    first = record_analysis_request("design a vendor onboarding process", tool_context=ctx)
    assert not first.startswith("ERROR:")
    token_after_first = ctx.state[PIPELINE_LOCK_TOKEN_STATE_KEY]["token"]

    second = log_analysis_metadata("Retail", 3, tool_context=ctx)
    assert not second.startswith("ERROR:")
    assert ctx.state[PIPELINE_LOCK_TOKEN_STATE_KEY]["token"] == token_after_first


def test_a_second_overlapping_turn_in_the_same_session_does_not_inherit_the_first_turns_token():
    # Regression test for the actual concurrency bug: tool_context.state
    # is scoped to the whole chat SESSION, not to one request. If a
    # second, genuinely different turn starts in that SAME session while
    # the first turn's pipeline is still running, it must NOT silently
    # inherit the first turn's still-valid token from the shared state
    # dict and sail through as "the same run" -- it has to compete for
    # the real lock like any other concurrent request.
    from process_agents.process.analysis_agent import log_analysis_metadata

    shared_session_state = {}
    first_turn_ctx = _fake_context(state=shared_session_state)
    first = log_analysis_metadata("Retail", 3, tool_context=first_turn_ctx)
    assert not first.startswith("ERROR:")

    # A second, later turn in the SAME session (same state dict) but a
    # DIFFERENT invocation_id, arriving before the first turn's pipeline
    # has released its lock.
    second_turn_ctx = _fake_context(state=shared_session_state)
    second = log_analysis_metadata("Retail", 3, tool_context=second_turn_ctx)
    assert second.startswith("ERROR:")
    assert "the process pipeline" in second


def test_a_later_sequential_turn_in_the_same_session_is_not_blocked_by_an_earlier_finished_one(monkeypatch):
    # The legitimate counterpart to the regression test above: once the
    # first turn's pipeline has actually finished (released its lock), a
    # LATER turn in that same session (e.g. "now update the process")
    # must acquire cleanly -- being in the same session must never, by
    # itself, cause a false conflict either.
    import process_agents.common.doc_generation_agent as doc_generation_agent_module
    from process_agents.process.analysis_agent import log_analysis_metadata

    monkeypatch.setattr(
        doc_generation_agent_module, "_shared_create_standard_doc_from_file",
        lambda process_name, schema_type=None: "SUCCESS: mocked",
    )

    shared_session_state = {}
    first_turn_ctx = _fake_context(state=shared_session_state)
    assert not log_analysis_metadata("Retail", 3, tool_context=first_turn_ctx).startswith("ERROR:")
    assert doc_generation_agent_module.create_standard_doc_from_file(
        "Vendor Onboarding", tool_context=first_turn_ctx
    ).startswith("SUCCESS:")

    second_turn_ctx = _fake_context(state=shared_session_state)
    assert not log_analysis_metadata("Retail", 3, tool_context=second_turn_ctx).startswith("ERROR:")


def test_design_doc_analysis_log_metadata_refuses_when_locked():
    from process_agents.design.design_doc_analysis_agent import log_analysis_metadata

    _write_conflicting_lock("the process pipeline")
    result = log_analysis_metadata("Payments", 2, tool_context=_fake_context())
    assert result.startswith("ERROR:")
    assert "the process pipeline" in result


def test_design_doc_analysis_succeeds_with_no_conflicting_lock():
    from process_agents.design.design_doc_analysis_agent import log_analysis_metadata

    result = log_analysis_metadata("Payments", 2, tool_context=_fake_context())
    assert not result.startswith("ERROR:")


def test_cloudarch_reset_short_circuits_with_content_when_locked():
    from process_agents.cloudarch.cloudarch_pipeline_agent import _reset_cloudarch_approval_state

    _write_conflicting_lock("the process pipeline")
    result = _reset_cloudarch_approval_state(_fake_context())

    assert result is not None
    assert result.role == "model"
    assert "the process pipeline" in result.parts[0].text


def test_cloudarch_reset_proceeds_normally_with_no_conflicting_lock():
    from process_agents.cloudarch.cloudarch_pipeline_agent import _reset_cloudarch_approval_state

    assert _reset_cloudarch_approval_state(_fake_context()) is None


def test_cloudarch_release_after_reset_allows_a_different_pipeline_to_acquire():
    from process_agents.cloudarch.cloudarch_pipeline_agent import (
        _reset_cloudarch_approval_state,
        _release_cloudarch_pipeline_lock,
    )

    ctx = _fake_context()
    assert _reset_cloudarch_approval_state(ctx) is None

    with pytest.raises(Exception):
        acquire_pipeline_lock("a different pipeline")

    _release_cloudarch_pipeline_lock(ctx)
    acquire_pipeline_lock("a different pipeline")  # must not raise -- released


def test_process_pipeline_releases_its_lock_once_the_document_is_generated(monkeypatch):
    # End-to-end token round-trip across the two ADK-side wrapper
    # functions (one in process/analysis_agent.py, one in
    # common/doc_generation_agent.py) sharing one tool_context, mirroring
    # how the real pipeline threads it through tool_context.state. The
    # actual document/diagram build is mocked out -- it's already covered
    # by test_process_update_regenerates_documents.py and friends; this
    # test's only job is the lock round-trip around it.
    import process_agents.common.doc_generation_agent as doc_generation_agent_module
    from process_agents.process.analysis_agent import log_analysis_metadata

    monkeypatch.setattr(
        doc_generation_agent_module, "_shared_create_standard_doc_from_file",
        lambda process_name, schema_type=None: "SUCCESS: mocked",
    )

    ctx = _fake_context()
    assert not log_analysis_metadata("Retail", 3, tool_context=ctx).startswith("ERROR:")

    doc_result = doc_generation_agent_module.create_standard_doc_from_file("Vendor Onboarding", tool_context=ctx)
    assert doc_result.startswith("SUCCESS:")

    acquire_pipeline_lock("a different pipeline")  # must not raise -- released above


def test_two_different_pipelines_cannot_run_concurrently():
    # The actual risk this guards against: one pipeline's own first reset
    # call locks out a second, different pipeline's own first reset call
    # made moments later (simulating a second concurrent request), rather
    # than both proceeding and interleaving writes to the same output/
    # directory.
    from process_agents.process.analysis_agent import log_analysis_metadata as process_reset
    from process_agents.design.design_doc_analysis_agent import log_analysis_metadata as design_reset

    first = process_reset("Retail", 3, tool_context=_fake_context())
    assert not first.startswith("ERROR:")

    # A SEPARATE request gets its own, fresh tool_context (no shared
    # token) -- ownership, not elapsed time, is what rejects it.
    second = design_reset("Payments", 2, tool_context=_fake_context())
    assert second.startswith("ERROR:")
    assert "the process pipeline" in second
