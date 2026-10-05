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
