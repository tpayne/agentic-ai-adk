"""The most important test in this suite: loop_control.py replaces ADK's
tool_context.actions.escalate, and its ordering (approval checked BEFORE
max-iterations) is exactly what the ADK original's own docstring calls out
as load-bearing -- a genuine approval on the final allowed iteration must
report as approved, not exhausted."""

from coded_tools.common.iteration_feedback import save_iteration_feedback
from coded_tools.common.loop_control import LoopControlCodedTool
from process_toolkit.paths import output_path


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
    from coded_tools.common.iteration_feedback import reset_approval_state

    tool = LoopControlCodedTool()
    required = {"cloudarch_status": "APPROVED"}

    first_run = tool.invoke({"required": required, "max_iterations": 5}, {})
    assert first_run["iteration"] == 1

    save_iteration_feedback({"status": "CLOUDARCH APPROVED", "data": []})
    tool.invoke({"required": required, "max_iterations": 5}, {})  # STOP: resets the counter only

    reset_approval_state()  # what a NEW top-level request's reset_loop_state call does
    second_run = tool.invoke({"required": required, "max_iterations": 5}, {})
    assert second_run["iteration"] == 1
