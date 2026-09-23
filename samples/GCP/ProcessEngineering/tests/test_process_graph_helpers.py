import sys
import types
import unittest


def _install_graph_stubs():
    google = sys.modules.setdefault("google", types.ModuleType("google"))
    genai = sys.modules.setdefault("google.genai", types.ModuleType("google.genai"))
    genai.types = types.SimpleNamespace()
    google.genai = genai

    networkx = sys.modules.setdefault("networkx", types.ModuleType("networkx"))

    class DiGraph:
        def __init__(self):
            self.edges = []

        def add_edges_from(self, edges):
            self.edges.extend(edges)

    networkx.DiGraph = DiGraph
    networkx.spring_layout = lambda graph, seed=None: {}

    pyplot = types.ModuleType("matplotlib.pyplot")
    pyplot.subplots = lambda **kwargs: (None, None)
    matplotlib = sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
    matplotlib.pyplot = pyplot
    sys.modules.setdefault("matplotlib.pyplot", pyplot)


_install_graph_stubs()
from process_agents import edge_inference_agent, step_diagram_agent  # noqa: E402


class EdgeInferenceHelperTests(unittest.TestCase):
    def test_order_steps_uses_numeric_priority_and_preserves_unusable_values(self):
        steps = [
            {"step_number": 2, "step_name": "two"},
            {"step_number": 1, "step_name": "one"},
            {"step_number": "unknown", "step_name": "unknown"},
        ]
        ordered = edge_inference_agent._order_steps(steps)
        self.assertEqual([step["step_name"] for step in ordered], ["one", "two", "unknown"])

    def test_lane_label_and_metrics_helpers(self):
        step = {
            "responsible_party": "Operations",
            "estimated_duration": "2 hours",
            "metrics": [{"metric_name": "SLA"}, {"metric_name": "Ignored"}],
        }
        self.assertEqual(edge_inference_agent._get_lane(step), "Operations")
        self.assertEqual(
            edge_inference_agent._build_enriched_label("Deploy", step),
            "Deploy\nDuration: 2 hours\nMetric: SLA",
        )
        self.assertEqual(edge_inference_agent._shorten("abcdefgh", 6), "abc...")

    def test_dependency_index_resolves_multiple_reference_styles(self):
        steps = [
            {"step_id": "A", "step_name": "Prepare"},
            {"step_number": 2, "step_name": "Deploy"},
        ]
        index = edge_inference_agent._build_id_index(steps)
        self.assertIs(edge_inference_agent._resolve_dependency("A", index), steps[0])
        self.assertIs(edge_inference_agent._resolve_dependency(2, index), steps[1])
        self.assertIsNone(edge_inference_agent._resolve_dependency("missing", index))

    def test_metric_extraction_deduplicates_and_limits_to_one(self):
        step = {"metrics": ["A", {"name": "A"}, {"name": "B"}]}
        self.assertEqual(edge_inference_agent._extract_step_metrics(step), ["A"])


class StepDiagramHelperTests(unittest.TestCase):
    def test_extract_substeps_supports_known_and_fallback_keys(self):
        self.assertEqual(
            step_diagram_agent._extract_substeps({"flow": [{"name": "A"}]}),
            [{"name": "A"}],
        )
        self.assertEqual(
            step_diagram_agent._extract_substeps({"other": [{"name": "B"}]}),
            [{"name": "B"}],
        )
        self.assertEqual(step_diagram_agent._extract_substeps(None), [])

    def test_lane_and_gateway_detection(self):
        self.assertEqual(
            step_diagram_agent._get_lane({"responsible_party": ["Ops"]}), "Ops"
        )
        self.assertTrue(step_diagram_agent._is_gateway({"condition": "approved"}))
        self.assertTrue(step_diagram_agent._is_gateway({"type": "decision"}))
        self.assertFalse(step_diagram_agent._is_gateway({"type": "task"}))


if __name__ == "__main__":
    unittest.main()
