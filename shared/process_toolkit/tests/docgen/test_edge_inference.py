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


def test_generate_clean_diagram_skips_proposal_response_without_touching_disk():
    # Same reasoning as the requirements no-op above: a proposal response
    # has no flow/architecture diagram at all either.
    import json
    import os

    from process_toolkit import paths
    from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME

    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"process_name": "X", "process_steps": []}, f)

    result = edge_inference.generate_clean_diagram(schema_type="proposal_response")

    assert result == "SKIPPED: Proposal responses have no flow/architecture diagram to generate."
    assert not os.path.exists(paths.output_path("X_flow.png"))


def test_generate_clean_diagram_skips_test_specification_without_touching_disk():
    # Same reasoning as the requirements/proposal_response no-ops: a test
    # specification has no flow/architecture diagram to generate.
    import json
    import os

    from process_toolkit import paths
    from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME

    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"process_name": "X", "process_steps": []}, f)

    result = edge_inference.generate_clean_diagram(schema_type="test_specification")

    assert result == "SKIPPED: Test specifications have no flow/architecture diagram to generate."
    assert not os.path.exists(paths.output_path("X_flow.png"))


def test_generate_clean_diagram_skips_togaf_without_touching_disk():
    # Same reasoning as the requirements/proposal_response no-ops above --
    # TOGAF documents render several independent diagrams inline
    # per-section (see docgen/togaf_sections.py), not one whole-document
    # overview diagram.
    import json
    import os

    from process_toolkit import paths
    from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME

    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({"process_name": "X", "process_steps": []}, f)

    result = edge_inference.generate_clean_diagram(schema_type="togaf")

    assert result.startswith("SKIPPED: TOGAF architecture documents")
    assert not os.path.exists(paths.output_path("X_flow.png"))


def test_design_architecture_diagram_renders_component_cards_and_connections():
    import json
    import os

    from process_toolkit import paths
    from process_toolkit.schema.process_json import DESIGN_JSON_FILENAME

    with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({
            "document_metadata": {"title": "Payment Platform"},
            "high_level_design": {
                "components": [
                    {"component_name": "Client Portal", "owner": "Experience"},
                    {"component_name": "Payment API", "owner": "Services"},
                ],
                "integration_points": [{"source": "Client Portal", "target": "Payment API"}],
            },
        }, f)

    result = edge_inference.generate_clean_diagram(schema_type="design")
    diagram_path = paths.output_path("payment_platform_flow.png")

    assert result == f"Diagram successfully generated at {diagram_path}"
    assert os.path.isfile(diagram_path)
    assert os.path.getsize(diagram_path) > 0


def test_process_flow_diagram_renders_step_cards_and_lanes():
    import json
    import os

    from process_toolkit import paths
    from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME

    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump({
            "process_name": "Client Onboarding",
            "process_steps": [
                {"step_number": 1, "step_name": "Submit application", "lane": "Client"},
                {"step_number": 2, "step_name": "Review application", "lane": "Operations"},
                {"step_number": 3, "step_name": "Activate account", "lane": "Operations"},
            ],
        }, f)

    result = edge_inference.generate_clean_diagram(schema_type="process")
    diagram_path = paths.output_path("client_onboarding_flow.png")

    assert result == f"Diagram successfully generated at {diagram_path}"
    assert os.path.isfile(diagram_path)
    assert os.path.getsize(diagram_path) > 0
