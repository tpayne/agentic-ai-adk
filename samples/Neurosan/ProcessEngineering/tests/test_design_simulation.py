import json

from coded_tools.design.simulation import perform_design_sensitivity_analysis, simulate_design_architecture

DESIGN_DOC = {
    "document_metadata": {
        "document_id": "D-1", "document_type": "HLD", "system_name": "Checkout",
        "title": "Checkout HLD", "version": "1.0", "status": "draft",
    },
    "high_level_design": {
        "components": [
            {"component_name": "API Gateway", "dependencies": []},
            {"component_name": "Checkout Service", "dependencies": ["API Gateway"]},
            {"component_name": "Payment Service", "dependencies": ["Checkout Service"]},
        ],
        "integration_points": [{"source": "Checkout Service", "target": "Payment Service"}],
        "availability_and_resilience": {"availability_target": "99.9%"},
        "risks_and_mitigations": [
            {"id": "R1", "description": "Payment Service outage", "likelihood": "high", "impact": "high", "mitigation": "failover"},
        ],
    },
}

NO_COMPONENTS_DOC = {
    "document_metadata": {
        "document_id": "D-2", "document_type": "LLD", "system_name": "Checkout",
        "title": "Checkout LLD", "version": "1.0", "status": "draft",
    },
    "low_level_design": {"components": [{"component_name": "Checkout Service"}]},
}


def test_simulate_design_architecture_returns_sane_composite_result():
    result = json.loads(simulate_design_architecture(DESIGN_DOC))
    assert "error" not in result
    assert result["overall_risk_rating"] in ("Low", "Medium", "High")
    assert "resilience" in result and "scalability" in result
    assert "security" in result and "latency" in result
    # Payment Service is the riskiest leaf (highest likelihood/impact risk
    # attached, deepest in the dependency chain) -- it must show up as a
    # single point of failure.
    assert "Payment Service" in result["resilience"]["single_points_of_failure"]


def test_simulate_design_architecture_errors_on_pure_lld_document():
    result = json.loads(simulate_design_architecture(NO_COMPONENTS_DOC))
    assert result.get("error") == "design_simulation_failed"
    assert "high_level_design.components" in result["detail"]


def test_sensitivity_analysis_identifies_the_highest_leverage_component():
    result = json.loads(perform_design_sensitivity_analysis(DESIGN_DOC))
    # Payment Service has by far the highest actual failure probability
    # (baseline + the high-likelihood/high-impact risk attached to it),
    # so it dominates the Monte Carlo average blast radius even though
    # API Gateway's OWN isolated blast radius (if it alone failed) is
    # larger -- API Gateway almost never actually fails in the
    # simulation, so "fixing" it barely moves the average. Fixing
    # Payment Service (driving its probability near zero) removes the
    # single biggest real contributor.
    assert result["top_leverage_component"] == "Payment Service"
    assert result["potential_blast_radius_reduction"] > 0


MESSAGING_DESIGN_DOC = {
    "document_metadata": {
        "document_id": "D-3", "document_type": "HLD", "system_name": "Checkout",
        "title": "Checkout HLD", "version": "1.0", "status": "draft",
    },
    "high_level_design": {
        "components": [
            {"component_name": "Checkout Orchestrator", "dependencies": []},
            {"component_name": "Message Broker", "dependencies": ["Checkout Orchestrator"], "technology_stack": ["Amazon MSK (Kafka)"]},
            {"component_name": "Inventory Worker", "dependencies": ["Message Broker"]},
            {"component_name": "Notification Worker", "dependencies": ["Message Broker"]},
            {"component_name": "Custom Rate Limiter", "dependencies": ["Checkout Orchestrator"], "technology_stack": ["In-house Go service"]},
            {"component_name": "Dependent A", "dependencies": ["Custom Rate Limiter"]},
            {"component_name": "Dependent B", "dependencies": ["Custom Rate Limiter"]},
        ],
        "availability_and_resilience": {"availability_target": "99.9%"},
    },
}


def test_a_managed_kafka_message_broker_is_not_flagged_as_a_structural_bottleneck():
    # Regression test: "Amazon MSK (Kafka)" previously matched none of
    # _ELASTIC_TECH_KEYWORDS despite being a fully-managed, provider-scaled
    # messaging service, so any multi-dependent Message Broker component
    # got flagged as a structural bottleneck on every real run.
    result = json.loads(simulate_design_architecture(MESSAGING_DESIGN_DOC))
    flagged_names = {b["component_name"] for b in result["scalability"]["structural_bottlenecks"]}
    assert "Message Broker" not in flagged_names


def test_a_custom_component_with_no_elastic_tech_is_still_flagged_as_a_bottleneck():
    # Same fixture, proving the kafka/msk keyword addition didn't
    # accidentally suppress the check entirely -- a genuinely non-elastic,
    # multi-dependent custom component must still be flagged.
    result = json.loads(simulate_design_architecture(MESSAGING_DESIGN_DOC))
    flagged_names = {b["component_name"] for b in result["scalability"]["structural_bottlenecks"]}
    assert "Custom Rate Limiter" in flagged_names
