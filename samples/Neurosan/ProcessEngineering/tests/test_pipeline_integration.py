"""End-to-end simulations of what a front-man's orchestration does, calling
the real CodedTool classes in the same sequence the HOCON instructions
describe -- without needing a real LLM. Catches wiring bugs the individual
unit tests above wouldn't (e.g. a channel name typo between two tools)."""

import pytest

from process_toolkit import paths
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME

from coded_tools.cloudarch.load_drawio_tool import LoadDrawioCodedTool
from coded_tools.cloudarch.loop_control_tool import LoopControlCodedTool as CloudArchLoopControl
from coded_tools.cloudarch.reset_loop_state_tool import ResetLoopStateCodedTool as CloudArchReset
from coded_tools.cloudarch.save_drawio_structured_tool import SaveDrawioStructuredCodedTool
from coded_tools.cloudarch.save_iteration_feedback_tool import (
    SaveIterationFeedbackCodedTool as CloudArchSaveFeedback,
)
from coded_tools.process.load_iteration_feedback_tool import (
    LoadIterationFeedbackCodedTool as ProcessLoadFeedback,
)
from coded_tools.process.loop_control_tool import LoopControlCodedTool as ProcessLoopControl
from coded_tools.process.process_json_tool import (
    LoadMasterProcessJsonCodedTool,
    PersistFinalJsonCodedTool,
)
from coded_tools.design.reset_loop_state_tool import ResetLoopStateCodedTool as DesignReset
from coded_tools.process.reset_loop_state_tool import ResetLoopStateCodedTool as ProcessReset
from coded_tools.process.save_iteration_feedback_tool import (
    SaveIterationFeedbackCodedTool as ProcessSaveFeedback,
)
from coded_tools.process.doc_generation_tool import GenerateProcessDocumentCodedTool
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY
from process_toolkit import run_lock
from process_toolkit.run_lock import acquire_pipeline_lock, PipelineLockedError


def test_cloudarch_pipeline_approves_on_first_pass():
    CloudArchReset().invoke({}, {})

    save_drawio = SaveDrawioStructuredCodedTool()
    result = save_drawio.invoke({
        "title": "Checkout Service", "zones": [{"id": "edge", "label": "Edge"}],
        "components": [{"id": "waf", "zone_id": "edge", "label": "WAF"}], "edges": [],
    }, {})
    assert result["status"] == "OK"

    CloudArchSaveFeedback().invoke({"feedback": {"status": "CLOUDARCH APPROVED", "data": []}}, {})

    verdict = CloudArchLoopControl().invoke(
        {"required": {"cloudarch_status": "APPROVED"}, "max_iterations": 2}, {}
    )
    assert verdict == {"verdict": "STOP", "reason": "APPROVED"}
    assert LoadDrawioCodedTool().invoke({}, {})["status"] == "OK"


def test_cloudarch_pipeline_continues_then_stops_at_max_iterations_if_never_approved():
    CloudArchReset().invoke({}, {})
    loop_control = CloudArchLoopControl()
    required = {"cloudarch_status": "APPROVED"}

    first = loop_control.invoke({"required": required, "max_iterations": 2}, {})
    assert first["verdict"] == "CONTINUE"

    CloudArchSaveFeedback().invoke({"feedback": {"status": "REVISION REQUIRED", "data": ["fix the WAF placement"]}}, {})

    second = loop_control.invoke({"required": required, "max_iterations": 2}, {})
    assert second == {"verdict": "STOP", "reason": "MAX_ITERATIONS"}


def test_process_pipeline_approves_after_both_reviewers_write_to_their_own_channel():
    ProcessReset().invoke({}, {})

    doc = {
        "process_name": "Vendor Onboarding",
        "process_steps": [
            {
                "step_name": "KYC Check", "responsible_party": "Compliance",
                "description": (
                    "Verify the vendor's identity and compliance documents, cross-checking submitted "
                    "paperwork against regulatory watchlists and sanctions lists before approving the "
                    "vendor for onboarding into the procurement system."
                ),
                "dependencies": [],
            },
            {
                "step_name": "Contract Approval", "responsible_party": "Legal",
                "description": (
                    "Review and approve the vendor contract, confirming terms align with procurement "
                    "policy and escalating any deviations to Legal counsel for sign-off before the "
                    "contract is countersigned and filed."
                ),
                "dependencies": ["KYC Check"],
            },
        ],
    }
    persist_result = PersistFinalJsonCodedTool().invoke({"json_content": doc}, {})
    assert persist_result.startswith("SUCCESS:")

    save_feedback = ProcessSaveFeedback()
    # Both reviewers write feedback in the same pass -- on a single shared
    # mailbox this would be a lost-write race; per-channel mailboxes avoid it.
    save_feedback.invoke({"channel": "compliance", "feedback": {"status": "COMPLIANCE APPROVED", "notes": "ok"}}, {})
    save_feedback.invoke({"channel": "simulation", "feedback": {"status": "SIMULATION_ALL_APPROVED", "notes": "ok"}}, {})

    verdict = ProcessLoopControl().invoke(
        {"required": {"compliance_status": "APPROVED", "simulation_status": "APPROVED"}, "max_iterations": 2}, {}
    )
    assert verdict == {"verdict": "STOP", "reason": "APPROVED"}
    assert LoadMasterProcessJsonCodedTool().invoke({}, {})["process_name"] == "Vendor Onboarding"


def test_process_pipeline_continues_if_only_one_reviewer_has_approved():
    ProcessReset().invoke({}, {})
    ProcessSaveFeedback().invoke({"channel": "compliance", "feedback": {"status": "COMPLIANCE APPROVED", "notes": "ok"}}, {})
    # simulation channel never approved

    verdict = ProcessLoopControl().invoke(
        {"required": {"compliance_status": "APPROVED", "simulation_status": "APPROVED"}, "max_iterations": 2}, {}
    )
    assert verdict["verdict"] == "CONTINUE"


def test_reset_loop_state_clears_stale_undrained_feedback_from_an_earlier_run():
    # Reproduces a real gap: a run that stops at MAX_ITERATIONS right after
    # a reviewer writes fresh feedback never has that feedback drained --
    # the generator is never called again once the loop decides to stop.
    # Simulate that leftover state here, then confirm reset_loop_state (the
    # very first thing a NEW, unrelated request calls) clears it, so the
    # next generator call can't load and apply someone else's stale review.
    ProcessSaveFeedback().invoke(
        {"channel": "compliance", "feedback": {"status": "REVISION REQUIRED", "data": ["stale, unrelated issue"]}}, {}
    )
    ProcessSaveFeedback().invoke(
        {"channel": "simulation", "feedback": {"status": "REVISION REQUIRED", "data": ["stale, unrelated issue"]}}, {}
    )

    ProcessReset().invoke({}, {})

    load_feedback = ProcessLoadFeedback()
    for channel in ("compliance", "simulation"):
        result = load_feedback.invoke({"channel": channel}, {})
        assert result.get("data") in (None, []), f"channel {channel!r} still has stale data: {result}"


def test_reset_loop_state_refuses_to_run_while_another_pipeline_is_still_in_flight():
    # Reproduces the concurrency risk directly: a run's own reset_loop_state
    # call must not clear another, still-active run's approval/feedback
    # state out from under it -- it should refuse instead.
    acquire_pipeline_lock("a design pipeline")
    ProcessSaveFeedback().invoke(
        {"channel": "compliance", "feedback": {"status": "REVISION REQUIRED", "data": ["in-flight run's own feedback"]}}, {}
    )

    result = ProcessReset().invoke({}, {})

    assert result["status"] == "ERROR"
    assert "a design pipeline" in result["error"]

    # The in-flight run's own feedback must survive untouched.
    load_feedback = ProcessLoadFeedback()
    assert load_feedback.invoke({"channel": "compliance"}, {})["data"] == ["in-flight run's own feedback"]


def test_a_second_overlapping_request_in_the_same_session_does_not_inherit_the_first_requests_token():
    # Regression test: sly_data is scoped to the whole chat SESSION, not
    # to one request. If reset_loop_state read back whatever token a
    # PRIOR request in that same session had already stashed there, a
    # second, genuinely different request arriving while the first's
    # pipeline is still running would silently inherit it and be waved
    # through as "the same run" instead of correctly conflicting.
    shared_session_sly_data = {}
    first = ProcessReset().invoke({}, shared_session_sly_data)
    assert first["status"] == "OK"

    second = DesignReset().invoke({}, shared_session_sly_data)
    assert second["status"] == "ERROR"
    assert "a neuro-san pipeline" in second["error"]


def test_process_pipeline_releases_its_lock_once_the_document_is_generated():
    # End-to-end token round-trip: reset_loop_state acquires and stashes a
    # token in sly_data; the pipeline's own genuine last step
    # (GenerateProcessDocumentCodedTool) reads that SAME sly_data and
    # releases it on success -- a later, different run must then be able
    # to acquire cleanly, rather than waiting out the staleness window.
    import json

    sly_data = {}
    assert ProcessReset().invoke({}, sly_data)["status"] == "OK"
    token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
    assert token
    # reset_loop_state starts a background heartbeat for this token --
    # there is no single tool call spanning the whole run to otherwise
    # keep the lease fresh between here and the release below (see
    # ResetLoopStateCodedTool's own docstring).
    assert token in run_lock._heartbeats

    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({
            "process_name": "Vendor Onboarding",
            "process_steps": [{"step_name": "KYC Check", "responsible_party": "Compliance", "dependencies": []}],
        }, f)

    doc_result = GenerateProcessDocumentCodedTool().invoke({}, sly_data)
    assert doc_result.startswith("SUCCESS:")
    assert token not in run_lock._heartbeats  # stopped alongside the release below

    acquire_pipeline_lock("a different pipeline")  # must not raise -- released above


def test_cloudarch_pipeline_releases_its_lock_only_once_the_loop_genuinely_stops():
    # Mirrors the process-pipeline round-trip above, but for cloudarch's
    # own shape: the release lives in loop_control (cloudarch's own
    # subclass), not in save_drawio_structured, since the latter is
    # called on EVERY loop iteration, not just the final one.
    sly_data = {}
    assert CloudArchReset().invoke({}, sly_data)["status"] == "OK"
    token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
    assert token
    assert token in run_lock._heartbeats

    # Mid-loop: a CONTINUE verdict must NOT release the lock, and must
    # leave the heartbeat running -- the loop could still have another,
    # possibly long, generate/review iteration ahead of it.
    continuing = CloudArchLoopControl().invoke({"required": {"cloudarch_status": "APPROVED"}, "max_iterations": 2}, sly_data)
    assert continuing["verdict"] == "CONTINUE"
    assert token in run_lock._heartbeats
    with pytest.raises(PipelineLockedError):
        acquire_pipeline_lock("a different pipeline")

    CloudArchSaveFeedback().invoke({"feedback": {"status": "CLOUDARCH APPROVED", "data": []}}, sly_data)
    stopped = CloudArchLoopControl().invoke({"required": {"cloudarch_status": "APPROVED"}, "max_iterations": 2}, sly_data)
    assert stopped["verdict"] == "STOP"
    assert token not in run_lock._heartbeats  # stopped alongside the release on STOP

    acquire_pipeline_lock("a different pipeline")  # must not raise -- released on STOP
