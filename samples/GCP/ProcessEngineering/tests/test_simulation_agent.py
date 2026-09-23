import json
import sys
import types
import unittest
from unittest.mock import patch


def _install_adk_stubs():
    google = sys.modules.setdefault("google", types.ModuleType("google"))
    adk = sys.modules.setdefault("google.adk", types.ModuleType("google.adk"))
    models = sys.modules.setdefault(
        "google.adk.models", types.ModuleType("google.adk.models")
    )
    agents = sys.modules.setdefault(
        "google.adk.agents", types.ModuleType("google.adk.agents")
    )
    callback_context = sys.modules.setdefault(
        "google.adk.agents.callback_context",
        types.ModuleType("google.adk.agents.callback_context"),
    )
    tools = sys.modules.setdefault(
        "google.adk.tools", types.ModuleType("google.adk.tools")
    )
    tool_context = sys.modules.setdefault(
        "google.adk.tools.tool_context",
        types.ModuleType("google.adk.tools.tool_context"),
    )
    genai = sys.modules.setdefault("google.genai", types.ModuleType("google.genai"))

    models.LlmRequest = type("LlmRequest", (), {})
    models.LlmResponse = type("LlmResponse", (), {})
    callback_context.CallbackContext = type("CallbackContext", (), {})
    tool_context.ToolContext = type("ToolContext", (), {})
    agents.callback_context = callback_context
    tools.tool_context = tool_context
    adk.models = models
    adk.agents = agents
    adk.tools = tools
    google.adk = adk
    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    genai.types = types.SimpleNamespace(GenerateContentConfig=GenerateContentConfig)


_install_adk_stubs()
from process_agents import simulation_agent  # noqa: E402


def process(steps):
    return {"process_steps": steps}


class SimulationParsingTests(unittest.TestCase):
    def test_repair_removes_trailing_commas_and_bom(self):
        repaired = simulation_agent._attempt_json_repair(
            '\ufeff{"steps": [1,],}'
        )
        self.assertEqual(json.loads(repaired), {"steps": [1]})

    def test_extract_valid_json_prefers_largest_valid_object(self):
        value = simulation_agent._extract_valid_json(
            'comment {"ignored": } then {"result": {"ok": true}}'
        )
        self.assertEqual(value, {"result": {"ok": True}})

    def test_extract_valid_json_rejects_missing_object(self):
        with self.assertRaises(ValueError):
            simulation_agent._extract_valid_json("not json")

    def test_validate_repairs_dict_and_json_string_steps(self):
        document = process({"first": {"step_name": "A"}})
        simulation_agent._validate_process_json(document)
        self.assertEqual(document["process_steps"], [{"step_name": "A"}])

        document = process(json.dumps([{"step_name": "B"}]))
        simulation_agent._validate_process_json(document)
        self.assertEqual(document["process_steps"][0]["step_name"], "B")

    def test_validate_rejects_null_missing_and_bad_steps(self):
        for document, message in (
            ({}, "missing"),
            (process(None), "null"),
            (process([{"description": "missing name"}]), "step_name"),
        ):
            with self.subTest(message=message), self.assertRaises(ValueError):
                simulation_agent._validate_process_json(document)


class SimulationCoreTests(unittest.TestCase):
    def test_detect_cycles_rejects_circular_dependencies(self):
        with self.assertRaisesRegex(ValueError, "Circular dependency"):
            simulation_agent._detect_cycles(
                [{"name": "A", "deps": ["B"]}, {"name": "B", "deps": ["A"]}]
            )

    def test_core_simulation_is_deterministic_with_seed_and_tracks_bottleneck(self):
        data = process(
            [
                {"step_name": "Prepare", "estimated_duration": "2 hours"},
                {
                    "step_name": "Deploy",
                    "estimated_duration": "4 hours",
                    "dependencies": ["Prepare"],
                },
            ]
        )
        with patch.object(
            simulation_agent.random, "triangular", side_effect=lambda low, high, mode: mode
        ):
            result = simulation_agent._run_core_simulation(data, iterations=3)
        self.assertEqual(result["time_unit"], "hours")
        self.assertEqual(result["avg_cycle_time"], 6.0)
        self.assertEqual(result["bottlenecks"][0], "Deploy")
        self.assertEqual(result["per_step_avg"]["Prepare"], 2.0)

    def test_core_simulation_rejects_empty_process_and_cycles(self):
        with self.assertRaisesRegex(ValueError, "No valid"):
            simulation_agent._run_core_simulation(process([]), iterations=1)
        with self.assertRaisesRegex(ValueError, "Circular"):
            simulation_agent._run_core_simulation(
                process(
                    [
                        {"step_name": "A", "dependencies": ["B"]},
                        {"step_name": "B", "dependencies": ["A"]},
                    ]
                ),
                iterations=1,
            )

    def test_simulate_process_performance_returns_structured_error(self):
        result = json.loads(
            simulation_agent.simulate_process_performance('{"process_steps": null}')
        )
        self.assertEqual(result["error"], "simulation_failed")

    def test_simulate_scenario_applies_overrides_removals_and_parallelization(self):
        document = process(
            [
                {"step_name": "A", "estimated_duration": "10"},
                {
                    "step_name": "B",
                    "estimated_duration": "4",
                    "dependencies": ["A"],
                },
            ]
        )
        scenario = {
            "override_durations": {"A": "8"},
            "remove_dependencies": {"B": ["A"]},
            "parallelize": ["A"],
        }
        with patch.object(simulation_agent, "_run_core_simulation", return_value={"ok": True}) as run:
            result = simulation_agent.simulate_scenario(
                json.dumps(document), json.dumps(scenario)
            )
        self.assertEqual(json.loads(result), {"ok": True})
        modified = run.call_args.args[0]["process_steps"]
        self.assertEqual(modified[0]["estimated_duration"], "5.6")
        self.assertEqual(modified[1]["dependencies"], [])

    def test_sensitivity_analysis_ranks_step_savings(self):
        document = process(
            [
                {"step_name": "Short", "estimated_duration": "2"},
                {"step_name": "Long", "estimated_duration": "10"},
            ]
        )
        calls = []
        original_durations = {"Short": 2.0, "Long": 10.0}

        def fake_simulation(data, iterations):
            calls.append(data)
            if len(calls) == 1:
                avg = 100
            else:
                changed = next(
                    step for step in data["process_steps"]
                    if float(step["estimated_duration"]) != original_durations[step["step_name"]]
                )
                saving = original_durations[changed["step_name"]] - float(
                    changed["estimated_duration"]
                )
                avg = 100 - saving
            return {"avg_cycle_time": avg, "time_unit": "hours"}

        with patch.object(
            simulation_agent, "_run_core_simulation", side_effect=fake_simulation
        ):
            result = json.loads(simulation_agent.perform_sensitivity_analysis(document))
        self.assertEqual(result["top_leverage_step"], "Long")
        self.assertEqual(len(result["full_analysis"]), 2)


if __name__ == "__main__":
    unittest.main()
