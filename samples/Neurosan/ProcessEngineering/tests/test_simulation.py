import json

from coded_tools.process.simulation import perform_sensitivity_analysis, simulate_process_performance

PROCESS_DOC = {
    "process_name": "Test",
    "process_steps": [
        {"step_name": "A", "estimated_duration": "1 hours", "dependencies": []},
        {"step_name": "B", "estimated_duration": "10 hours", "dependencies": ["A"]},
        {"step_name": "C", "estimated_duration": "1 hours", "dependencies": ["A"]},
    ],
}


def test_simulate_process_performance_returns_sane_metrics():
    result = json.loads(simulate_process_performance(PROCESS_DOC))
    assert "error" not in result
    assert result["avg_cycle_time"] > 0
    assert result["time_unit"] == "hours"
    # B is by far the longest step, so it must dominate the cycle time and
    # show up as a bottleneck.
    assert "B" in result["bottlenecks"]


def test_simulate_process_performance_detects_circular_dependencies():
    circular = {
        "process_name": "Test",
        "process_steps": [
            {"step_name": "A", "estimated_duration": "1 hours", "dependencies": ["B"]},
            {"step_name": "B", "estimated_duration": "1 hours", "dependencies": ["A"]},
        ],
    }
    result = json.loads(simulate_process_performance(circular))
    assert result.get("error") == "simulation_failed"
    assert "Circular dependency" in result["detail"]


def test_sensitivity_analysis_identifies_the_longest_step_as_top_leverage():
    result = json.loads(perform_sensitivity_analysis(PROCESS_DOC))
    assert result["top_leverage_step"] == "B"
    assert result["potential_saving"] > 0
