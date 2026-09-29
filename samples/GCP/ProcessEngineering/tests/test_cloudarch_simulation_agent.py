import unittest
from unittest.mock import patch

from test_grounding_agent import _install_dependency_stubs

_install_dependency_stubs()
from process_agents.common import utils  # noqa: E402
from process_agents.cloudarch import cloudarch_simulation_agent as sim  # noqa: E402


_SAMPLE_XML = """
<mxfile host="app.diagrams.net">
  <diagram id="d1" name="Page-1">
    <mxGraphModel dx="800" dy="600">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="box_layout" value="Layout Box" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F9FAFB;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="100" height="60" as="geometry" />
        </mxCell>
        <mxCell id="node_a" value="Lambda A" style="sketch=0;shape=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="node_b" value="RDS B" style="sketch=0;shape=mxgraph.aws4.rds;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="node_c" value="EC2 C" style="sketch=0;shape=mxgraph.aws4.ec2;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="48" height="48" as="geometry" />
        </mxCell>
        <mxCell id="edge_ab" value="calls" style="edgeStyle=orthogonalEdgeStyle;" edge="1" parent="1" source="node_a" target="node_b">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="edge_bc" value="calls" style="edgeStyle=orthogonalEdgeStyle;" edge="1" parent="1" source="node_b" target="node_c">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="edge_dangling" style="edgeStyle=orthogonalEdgeStyle;" edge="1" parent="1" source="node_c" target="">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


class ParseDrawioGraphTests(unittest.TestCase):
    def test_excludes_layout_boxes_and_dangling_edges(self):
        graph = utils.parse_drawio_graph(_SAMPLE_XML)
        vertex_ids = {v["id"] for v in graph["vertices"]}
        self.assertEqual(vertex_ids, {"node_a", "node_b", "node_c"})
        self.assertNotIn("box_layout", vertex_ids)

        edge_ids = {e["id"] for e in graph["edges"]}
        self.assertEqual(edge_ids, {"edge_ab", "edge_bc"})
        self.assertNotIn("edge_dangling", edge_ids)

    def test_shape_provider_and_slug_extracted(self):
        graph = utils.parse_drawio_graph(_SAMPLE_XML)
        node_a = next(v for v in graph["vertices"] if v["id"] == "node_a")
        self.assertEqual(node_a["shape_provider"], "aws4")
        self.assertEqual(node_a["shape_slug"], "lambda")

    def test_malformed_xml_returns_empty_graph(self):
        self.assertEqual(
            utils.parse_drawio_graph("<not><valid"), {"vertices": [], "edges": []}
        )


def _fixture_graph():
    return utils.parse_drawio_graph(_SAMPLE_XML)


class CloudArchSimulationTests(unittest.TestCase):
    def test_impacts_graph_and_blast_radius_follow_edges(self):
        graph = _fixture_graph()
        impacts = sim._build_impacts_graph(graph["vertices"], graph["edges"])
        # edge_ab: A -> B (A depends on B, so if B fails A is impacted)
        # edge_bc: B -> C (B depends on C, so if C fails B is impacted)
        self.assertEqual(impacts["node_b"], {"node_a"})
        self.assertEqual(impacts["node_c"], {"node_b"})
        self.assertEqual(
            sim._blast_radius({"node_c"}, impacts), {"node_c", "node_b", "node_a"}
        )

    def test_core_simulation_reports_single_point_of_failure(self):
        graph = _fixture_graph()
        with patch.object(sim.random, "random", return_value=0.0):
            result = sim._run_core_cloudarch_simulation(
                graph["vertices"], graph["edges"], risk_items=[], iterations=2
            )
        self.assertEqual(result["component_count"], 3)
        self.assertEqual(result["avg_blast_radius"], 1.0)
        self.assertEqual(result["single_points_of_failure"][0]["id"], "node_c")

    def test_core_simulation_requires_vertices(self):
        with self.assertRaises(ValueError):
            sim._run_core_cloudarch_simulation([], [], risk_items=[], iterations=1)

    def test_risk_enrichment_matches_labels_and_ignores_unrelated(self):
        risks = [{"description": "RDS B outage risk", "likelihood": "high", "impact": "high"}]
        self.assertGreater(sim._risk_added_probability("RDS B", risks), 0)
        self.assertEqual(sim._risk_added_probability("Unrelated Thing", risks), 0)

    def test_scalability_flags_fan_in_without_elastic_tech(self):
        vertices = [
            {"id": "a", "value": "Lambda A", "shape_provider": "aws4", "shape_slug": "lambda"},
            {"id": "b", "value": "RDS B", "shape_provider": "aws4", "shape_slug": "rds"},
            {"id": "c", "value": "EC2 C", "shape_provider": "aws4", "shape_slug": "ec2"},
        ]
        # a and c both depend on b (fan_in=2), b is not elastic -> bottleneck
        impacts = {"a": set(), "b": {"a", "c"}, "c": set()}
        result = sim._analyze_scalability(vertices, impacts)
        bottleneck_ids = {b["id"] for b in result["structural_bottlenecks"]}
        self.assertIn("b", bottleneck_ids)

    def test_scalability_does_not_flag_elastic_fan_in(self):
        vertices = [
            {"id": "a", "value": "A", "shape_provider": "aws4", "shape_slug": "ec2"},
            {"id": "lam", "value": "Lambda", "shape_provider": "aws4", "shape_slug": "lambda"},
            {"id": "c", "value": "C", "shape_provider": "aws4", "shape_slug": "ec2"},
        ]
        impacts = {"a": set(), "lam": {"a", "c"}, "c": set()}
        result = sim._analyze_scalability(vertices, impacts)
        bottleneck_ids = {b["id"] for b in result["structural_bottlenecks"]}
        self.assertNotIn("lam", bottleneck_ids)

    def test_latency_deepest_chain_and_budget_risk(self):
        graph = _fixture_graph()
        impacts = sim._build_impacts_graph(graph["vertices"], graph["edges"])
        result = sim._analyze_latency(graph["vertices"], impacts)
        self.assertEqual(result["deepest_dependency_chain_length"], 3)
        self.assertFalse(result["latency_budget_risk"])  # chain of 3 < threshold of 4


if __name__ == "__main__":
    unittest.main()
