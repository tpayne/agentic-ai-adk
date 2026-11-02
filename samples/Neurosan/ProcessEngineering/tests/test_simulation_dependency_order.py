from coded_tools.process import simulation


def test_simulation_respects_dependencies_when_steps_are_unsorted(monkeypatch):
    monkeypatch.setattr(simulation.random, "triangular", lambda low, high, mode: mode)
    data = {
        "process_steps": [
            {
                "step_name": "Child",
                "estimated_duration": "1 hours",
                "dependencies": ["Parent"],
            },
            {
                "step_name": "Parent",
                "estimated_duration": "1 hours",
                "dependencies": [],
            },
        ],
    }

    result = simulation._run_core_simulation(data, iterations=1)

    assert result["avg_cycle_time"] == 2.0
