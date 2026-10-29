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


def test_generate_clean_diagram_skips_requirements_without_touching_disk():
    # A requirements register has no flow/architecture diagram at all.
    # Without this explicit no-op, "requirements" would fall into the
    # "process" branch (is_design is only ever true for "design") and
    # either error confusingly or silently render a stale, unrelated
    # process diagram -- confirmed as the exact risk even when a
    # process_data.json genuinely coexists, which this test asserts
    # against directly.
    import json
    import os

    from process_toolkit import paths
    from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME

    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"process_name": "X", "process_steps": []}, f)

    result = edge_inference.generate_clean_diagram(schema_type="requirements")

    assert result == "SKIPPED: Requirements summaries have no flow/architecture diagram to generate."
    assert not os.path.exists(paths.output_path("X_flow.png"))
