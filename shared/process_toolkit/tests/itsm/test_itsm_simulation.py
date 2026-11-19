from process_toolkit.itsm.simulation import simulate_itsm_risk_and_coverage


def _valid_metadata():
    return {
        "document_id": "I-1", "system_name": "Checkout", "title": "Checkout",
        "version": "1.0", "status": "draft",
    }


def test_empty_document_reports_no_findings():
    result = simulate_itsm_risk_and_coverage({"document_metadata": _valid_metadata()})
    assert result == {
        "bottlenecks": [], "escalation_gaps": [], "sla_measurement_gaps": [],
        "high_blast_radius_cis": [], "raci_coverage_gaps": [],
    }


def test_flags_a_single_role_owning_every_step_in_a_process_area():
    data = {
        "document_metadata": _valid_metadata(),
        "incident_management": {
            "process_steps": [
                {"step_id": "INC-1", "step_name": "Log", "responsible_role": "Service Desk"},
                {"step_id": "INC-2", "step_name": "Triage", "responsible_role": "Service Desk"},
            ],
        },
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert len(result["bottlenecks"]) == 1
    assert "Incident Management" in result["bottlenecks"][0]
    assert "Service Desk" in result["bottlenecks"][0]


def test_does_not_flag_steps_spread_across_different_roles():
    data = {
        "document_metadata": _valid_metadata(),
        "incident_management": {
            "process_steps": [
                {"step_id": "INC-1", "step_name": "Log", "responsible_role": "Service Desk"},
                {"step_id": "INC-2", "step_name": "Resolve", "responsible_role": "Engineering"},
            ],
        },
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert result["bottlenecks"] == []


def test_flags_priorities_with_no_escalation_paths_at_all():
    data = {
        "document_metadata": _valid_metadata(),
        "incident_management": {
            "priority_matrix": [{"priority": "P1", "impact": "High", "urgency": "High"}],
            "escalation_paths": [],
        },
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert len(result["escalation_gaps"]) == 1
    assert "P1" in result["escalation_gaps"][0]


def test_does_not_flag_escalation_when_paths_are_defined():
    data = {
        "document_metadata": _valid_metadata(),
        "incident_management": {
            "priority_matrix": [{"priority": "P1", "impact": "High", "urgency": "High"}],
            "escalation_paths": [{"from_tier": "Tier 1", "to_tier": "Tier 2", "trigger_condition": "1 hour"}],
        },
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert result["escalation_gaps"] == []


def test_flags_an_sla_with_no_measurement_window():
    data = {
        "document_metadata": _valid_metadata(),
        "service_level_management": {
            "slas": [{"id": "SLA-001", "service_id": "SVC-001", "metric": "Uptime", "target": "99.9%"}],
        },
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert len(result["sla_measurement_gaps"]) == 1
    assert "SLA-001" in result["sla_measurement_gaps"][0]


def test_flags_a_ci_with_more_dependents_than_the_threshold():
    data = {
        "document_metadata": _valid_metadata(),
        "configuration_management": {
            "relationships": [
                {"source_ci": f"CI-{i}", "target_ci": "CI-CORE", "relationship_type": "depends_on"}
                for i in range(4)
            ],
        },
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert result["high_blast_radius_cis"] == [{"ci": "CI-CORE", "dependent_count": 4}]


def test_does_not_flag_a_ci_at_or_below_the_threshold():
    data = {
        "document_metadata": _valid_metadata(),
        "configuration_management": {
            "relationships": [
                {"source_ci": f"CI-{i}", "target_ci": "CI-CORE", "relationship_type": "depends_on"}
                for i in range(3)
            ],
        },
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert result["high_blast_radius_cis"] == []


def test_flags_a_process_area_with_content_but_no_raci_entry():
    data = {
        "document_metadata": _valid_metadata(),
        "incident_management": {
            "process_steps": [{"step_id": "INC-1", "step_name": "Log", "responsible_role": "Service Desk"}],
        },
        "raci_matrix": [],
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert len(result["raci_coverage_gaps"]) == 1
    assert "Incident Management" in result["raci_coverage_gaps"][0]


def test_does_not_flag_a_process_area_that_has_a_raci_entry():
    data = {
        "document_metadata": _valid_metadata(),
        "incident_management": {
            "process_steps": [{"step_id": "INC-1", "step_name": "Log", "responsible_role": "Service Desk"}],
        },
        "raci_matrix": [{
            "process_area": "Incident Management", "activity": "Log Incident",
            "responsible": "Service Desk", "accountable": "Incident Manager",
        }],
    }
    result = simulate_itsm_risk_and_coverage(data)
    assert result["raci_coverage_gaps"] == []


def test_loads_the_saved_baseline_when_no_data_argument_is_passed(monkeypatch):
    import process_toolkit.itsm.simulation as sim_module

    monkeypatch.setattr(sim_module, "load_master_itsm_json", lambda: {"document_metadata": _valid_metadata()})
    result = simulate_itsm_risk_and_coverage()
    assert result["bottlenecks"] == []
