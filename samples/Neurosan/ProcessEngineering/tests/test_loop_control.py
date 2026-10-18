"""The most important test in this suite: loop_control.py replaces ADK's
tool_context.actions.escalate, and its ordering (approval checked BEFORE
max-iterations) is exactly what the ADK original's own docstring calls out
as load-bearing -- a genuine approval on the final allowed iteration must
report as approved, not exhausted."""

import json

from coded_tools.common.loop_control import LoopControlCodedTool
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY
from process_toolkit.feedback.iteration_feedback import save_iteration_feedback
from process_toolkit.paths import output_path
from process_toolkit.run_lock import acquire_pipeline_lock, release_pipeline_lock


def test_continues_while_unapproved_and_under_max_iterations():
    tool = LoopControlCodedTool()
    required = {"cloudarch_status": "APPROVED"}

    result = tool.invoke({"required": required, "max_iterations": 3}, {})
    assert result == {"verdict": "CONTINUE", "iteration": 1, "max_iterations": 3}


def test_approval_on_the_final_allowed_iteration_reports_as_approved_not_exhausted():
    tool = LoopControlCodedTool()
    required = {"cloudarch_status": "APPROVED"}

    tool.invoke({"required": required, "max_iterations": 2}, {})  # iteration 1: CONTINUE
    save_iteration_feedback({"status": "CLOUDARCH APPROVED", "data": []})

    result = tool.invoke({"required": required, "max_iterations": 2}, {})  # iteration 2
    assert result == {"verdict": "STOP", "reason": "APPROVED"}


def test_hits_max_iterations_when_never_approved():
    tool = LoopControlCodedTool()
    required = {"cloudarch_status": "APPROVED"}

    tool.invoke({"required": required, "max_iterations": 2}, {})
    result = tool.invoke({"required": required, "max_iterations": 2}, {})
    assert result == {"verdict": "STOP", "reason": "MAX_ITERATIONS"}


def test_iteration_counter_resets_after_a_stop():
    import os

    tool = LoopControlCodedTool()
    required = {"cloudarch_status": "APPROVED"}

    tool.invoke({"required": required, "max_iterations": 1}, {})  # STOP (max_iterations)
    assert not os.path.exists(output_path("stop_counter.json"))


def test_hard_stop_env_var_overrides_everything(monkeypatch):
    monkeypatch.setenv("LOOP_HARD_STOP", "true")
    tool = LoopControlCodedTool()
    result = tool.invoke({"required": {"x": "APPROVED"}, "max_iterations": 10}, {})
    assert result == {"verdict": "STOP", "reason": "HARD_STOP"}


def test_independent_runs_do_not_leak_iteration_count():
    """loop_control's own STOP only resets the iteration counter, matching
    the ADK original's _reset_stop_counter exactly -- clearing approval
    state itself is a separate, front-man-level concern (reset_loop_state /
    the ADK original's _remove_previous_approval_logs), run once at the
    start of a genuinely NEW top-level request, not by loop_control itself
    on every stop. So a fresh "run" here must reset approval state too."""
    from process_toolkit.feedback.iteration_feedback import reset_approval_state

    tool = LoopControlCodedTool()
    required = {"cloudarch_status": "APPROVED"}

    first_run = tool.invoke({"required": required, "max_iterations": 5}, {})
    assert first_run["iteration"] == 1

    save_iteration_feedback({"status": "CLOUDARCH APPROVED", "data": []})
    tool.invoke({"required": required, "max_iterations": 5}, {})  # STOP: resets the counter only

    reset_approval_state()  # what a NEW top-level request's reset_loop_state call does
    second_run = tool.invoke({"required": required, "max_iterations": 5}, {})
    assert second_run["iteration"] == 1


def test_invoke_refreshes_an_existing_pipeline_lock_lease():
    """Regression test for a review finding: a review loop that genuinely
    runs long enough to cross process_toolkit.run_lock.
    DEFAULT_STALE_AFTER_SECONDS between reset_loop_state_tool.py's
    one-time acquire and this run's own finalize step must not have its
    lock reclaimed by an unrelated concurrent run just because no one
    refreshed its started_at in between. loop_control runs once per
    iteration, so it's the natural heartbeat."""
    token = acquire_pipeline_lock("a neuro-san pipeline")
    try:
        lock_path = output_path("pipeline.lock")
        with open(lock_path, encoding="utf-8") as f:
            before_started_at = json.load(f)["started_at"]

        tool = LoopControlCodedTool()
        tool.invoke(
            {"required": {"x": "APPROVED"}, "max_iterations": 5},
            {PIPELINE_LOCK_TOKEN_KEY: token},
        )

        with open(lock_path, encoding="utf-8") as f:
            after = json.load(f)
        assert after["started_at"] >= before_started_at
        assert after["token"] == token  # still this run's own lock, not a new one
    finally:
        release_pipeline_lock(token)


def test_invoke_with_no_token_in_sly_data_does_not_touch_any_lock():
    import os

    # No PIPELINE_LOCK_TOKEN_KEY at all (e.g. a direct unit-tested call, or
    # a pipeline that never ran its own reset step) -- must not mint a
    # lock on this call's behalf.
    tool = LoopControlCodedTool()
    result = tool.invoke({"required": {"x": "APPROVED"}, "max_iterations": 5}, {})
    assert result["verdict"] == "CONTINUE"
    assert not os.path.exists(output_path("pipeline.lock"))
