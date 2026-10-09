from process_toolkit.docgen import edge_inference


def test_order_steps_uses_numeric_priority_and_preserves_unusable_values():
    steps = [
        {"step_number": 2, "step_name": "two"},
        {"step_number": 1, "step_name": "one"},
        {"step_number": "unknown", "step_name": "unknown"},
    ]
    ordered = edge_inference._order_steps(steps)
    assert [step["step_name"] for step in ordered] == ["one", "two", "unknown"]


def test_lane_and_label_helpers():
    step = {
        "responsible_party": "Operations",
        "estimated_duration": "2 hours",
        "metrics": [{"metric_name": "SLA"}, {"metric_name": "Ignored"}],
    }
    assert edge_inference._get_lane(step) == "Operations"
    assert edge_inference._build_enriched_label("Deploy", step) == "Deploy\nDuration: 2 hours\nMetric: SLA"


def test_dependency_index_resolves_multiple_reference_styles():
    steps = [
        {"step_id": "A", "step_name": "Prepare"},
        {"step_number": 2, "step_name": "Deploy"},
    ]
    index = edge_inference._build_id_index(steps)
    assert edge_inference._resolve_dependency("A", index) is steps[0]
    assert edge_inference._resolve_dependency(2, index) is steps[1]
    assert edge_inference._resolve_dependency("missing", index) is None


def test_metric_extraction_deduplicates_and_limits_to_one():
    step = {"metrics": ["A", {"name": "A"}, {"name": "B"}]}
    assert edge_inference._extract_step_metrics(step) == ["A"]
