"""Regression coverage for the Process_Architect_Orchestrator's own
clear_pipeline_lock tool -- the escape hatch for a pipeline lock stuck
because its owning run never reached its own release step (see
process_toolkit.run_lock.force_clear_pipeline_lock's own docstring)."""

from coded_tools.process_architect.clear_pipeline_lock_tool import ClearPipelineLockCodedTool
from process_toolkit.run_lock import acquire_pipeline_lock


def test_reports_nothing_to_clear_when_no_lock_is_held():
    result = ClearPipelineLockCodedTool().invoke({}, {})
    assert result == {
        "status": "OK", "cleared": False,
        "message": "No pipeline lock is currently held -- there was nothing to clear.",
    }


def test_clears_a_held_lock_and_reports_who_held_it():
    acquire_pipeline_lock("the design document pipeline")

    result = ClearPipelineLockCodedTool().invoke({}, {})

    assert result["status"] == "OK"
    assert result["cleared"] is True
    assert "the design document pipeline" in result["message"]

    # Genuinely released -- a different pipeline can now acquire cleanly.
    acquire_pipeline_lock("a different pipeline")
