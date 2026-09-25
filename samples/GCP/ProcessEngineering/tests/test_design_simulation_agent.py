import json
import unittest
from unittest.mock import patch

from test_grounding_agent import _install_dependency_stubs

_install_dependency_stubs()
from process_agents.design import design_simulation_agent  # noqa: E402


def design():
    return {
        "high_level_design": {
            "availability_and_resilience": {"availability_target": "99.9%"},
            "components": [
                {"component_name": "Database", "dependencies": []},
                {"component_name": "API Service", "dependencies": ["Database"]},
                {"component_name": "Web UI", "dependencies": ["API Service"]},
            ],
            "integration_points": [
                {"source": "Web UI", "target": "API Service"},
            ],
        },
        "risk_register": [
            {
                "id": "DB-1",
                "description": "Database outage",
                "likelihood": "high",
                "impact": "high",
            }
        ],
    }


class DesignSimulationTests(unittest.TestCase):
    def test_json_repair_and_extraction(self):
        repaired = design_simulation_agent._attempt_json_repair(
            "\ufeff{\"ok\": true,}"
        )
        self.assertEqual(json.loads(repaired), {"ok": True})
        self.assertEqual(
            design_simulation_agent._extract_valid_json("prefix {\"ok\": true} suffix"),
            {"ok": True},
        )

    def test_availability_target_parsing_has_safe_fallbacks(self):
        self.assertAlmostEqual(
            design_simulation_agent._availability_target_to_baseline_prob(
                design()["high_level_design"]
            ),
            0.001,
        )
        self.assertEqual(
            design_simulation_agent._availability_target_to_baseline_prob({}),
            0.01,
        )
        self.assertEqual(
            design_simulation_agent._availability_target_to_baseline_prob(
                {"availability_and_resilience": {"availability_target": "unknown"}}
            ),
            0.01,
        )

    def test_risk_collection_deduplicates_and_matches_component(self):
        data = design()
        data["high_level_design"]["risks_and_mitigations"] = [
            data["risk_register"][0]
        ]
        risks = design_simulation_agent._gather_risk_items(
            data, data["high_level_design"]
        )
        self.assertEqual(len(risks), 1)
        self.assertGreater(
            design_simulation_agent._risk_added_probability("Database", risks), 0
        )
        self.assertEqual(
            design_simulation_agent._risk_added_probability("Unrelated", risks), 0
        )

    def test_reference_resolution_rejects_ambiguous_alias(self):
        names = ["AWS Service A", "AWS Service B"]
        tokens = {name: design_simulation_agent._tokenize_name(name) for name in names}
        self.assertEqual(
            design_simulation_agent._resolve_component_reference(
                "AWS Service A", names, tokens
            ),
            "AWS Service A",
        )
        self.assertIsNone(
            design_simulation_agent._resolve_component_reference(
                "AWS Service", names, tokens
            )
        )

    def test_impacts_graph_and_blast_radius_follow_dependencies(self):
        data = design()
        components = data["high_level_design"]["components"]
        impacts, unresolved = design_simulation_agent._build_impacts_graph(
            [c["component_name"] for c in components],
            components,
            data["high_level_design"]["integration_points"],
        )
        self.assertEqual(unresolved, set())
        self.assertEqual(
            design_simulation_agent._blast_radius({"Database"}, impacts),
            {"Database", "API Service", "Web UI"},
        )

    def test_core_design_simulation_reports_single_point_and_unresolved_refs(self):
        data = design()
        with patch.object(design_simulation_agent.random, "random", return_value=0.0):
            result = design_simulation_agent._run_core_design_simulation(
                data, iterations=2
            )
        self.assertEqual(result["component_count"], 3)
        self.assertEqual(result["avg_blast_radius"], 1.0)
        self.assertEqual(result["single_points_of_failure"][0], "Database")

        data["high_level_design"]["components"][1]["dependencies"] = ["Missing"]
        result = design_simulation_agent._run_core_design_simulation(data, iterations=1)
        self.assertEqual(result["unresolved_references"], ["Missing"])

    def test_core_design_simulation_requires_hld_components(self):
        with self.assertRaises(ValueError):
            design_simulation_agent._run_core_design_simulation(
                {"high_level_design": {}}, iterations=1
            )


if __name__ == "__main__":
    unittest.main()
