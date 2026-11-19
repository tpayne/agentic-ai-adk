import docx

from process_toolkit.docgen import itsm_sections


def _headings(doc) -> list:
    return [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]


class TestServiceCatalogSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_service_catalog_section(doc, {}) is False
        assert itsm_sections._add_service_catalog_section(doc, None) is False

    def test_renders_services(self):
        doc = docx.Document()
        rendered = itsm_sections._add_service_catalog_section(doc, {
            "services": [{"id": "SVC-001", "name": "Email", "category": "Productivity", "business_criticality": "High"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "SVC-001" in table_texts
        assert "Email" in table_texts


class TestStakeholdersAndRolesSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_stakeholders_and_roles_section(doc, []) is False

    def test_renders_roles(self):
        doc = docx.Document()
        rendered = itsm_sections._add_stakeholders_and_roles_section(doc, [
            {"role": "Incident Manager", "responsibilities": ["Owns P1/P2 incidents"], "escalation_tier": "Tier 2"},
        ])
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "Incident Manager" in table_texts


class TestIncidentManagementSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_incident_management_section(doc, {}) is False

    def test_renders_priority_matrix_steps_and_escalation_paths(self):
        doc = docx.Document()
        rendered = itsm_sections._add_incident_management_section(doc, {
            "priority_matrix": [{"priority": "P1", "impact": "High", "urgency": "High"}],
            "process_steps": [
                {"step_id": "INC-1", "step_name": "Log Incident", "responsible_role": "Service Desk"},
                {"step_id": "INC-2", "step_name": "Triage", "responsible_role": "Service Desk"},
            ],
            "escalation_paths": [{"from_tier": "Tier 1", "to_tier": "Tier 2", "trigger_condition": "No resolution in 1 hour"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "P1" in table_texts
        assert "Log Incident" in table_texts
        assert "Tier 2" in table_texts

    def test_renders_an_honest_fallback_note_when_the_diagram_has_no_drawable_data(self):
        doc = docx.Document()
        itsm_sections._add_incident_management_section(doc, {
            "process_flow_diagram": {"diagram_id": "D-1", "title": "Incident Flow"},
        })
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "not yet generated" in text


class TestProblemManagementSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_problem_management_section(doc, {}) is False

    def test_renders_steps_and_known_errors(self):
        doc = docx.Document()
        rendered = itsm_sections._add_problem_management_section(doc, {
            "process_steps": [{"step_id": "PRB-1", "step_name": "Identify Root Cause"}],
            "known_errors": [{"id": "KE-001", "description": "DNS misconfiguration", "linked_incidents": ["INC-1001"]}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "Identify Root Cause" in table_texts
        assert "KE-001" in table_texts


class TestChangeManagementSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_change_management_section(doc, {}) is False

    def test_renders_change_types_steps_cab_members_and_risk_criteria(self):
        doc = docx.Document()
        rendered = itsm_sections._add_change_management_section(doc, {
            "change_types": [{"type": "standard", "approval_path": "Pre-approved"}],
            "process_steps": [{"step_id": "CHG-1", "step_name": "Submit RFC"}],
            "cab_members": [{"role": "Change Manager", "name_or_title": "Head of IT Ops"}],
            "risk_assessment_criteria": [{"risk_level": "High", "criteria": "Production outage possible", "required_approvals": ["CAB"]}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "Submit RFC" in table_texts
        assert "Head of IT Ops" in table_texts
        assert "High" in table_texts


class TestRequestFulfillmentSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_request_fulfillment_section(doc, {}) is False

    def test_renders_request_types_and_steps(self):
        doc = docx.Document()
        rendered = itsm_sections._add_request_fulfillment_section(doc, {
            "request_types": [{"type": "New Laptop", "target_fulfillment_time": "3 business days"}],
            "process_steps": [{"step_id": "REQ-1", "step_name": "Submit Request"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "New Laptop" in table_texts
        assert "Submit Request" in table_texts


class TestServiceLevelManagementSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_service_level_management_section(doc, {}) is False

    def test_renders_slas_olas_and_underpinning_contracts(self):
        doc = docx.Document()
        rendered = itsm_sections._add_service_level_management_section(doc, {
            "slas": [{"id": "SLA-001", "service_id": "SVC-001", "metric": "Uptime", "target": "99.9%"}],
            "olas": [{"id": "OLA-001", "internal_team": "Network Ops", "metric": "Response time", "target": "15 min"}],
            "underpinning_contracts": [{"id": "UC-001", "vendor": "Acme ISP", "linked_sla": "SLA-001"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "SLA-001" in table_texts
        assert "Network Ops" in table_texts
        assert "Acme ISP" in table_texts


class TestConfigurationManagementSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_configuration_management_section(doc, {}) is False

    def test_renders_configuration_items_and_relationships(self):
        doc = docx.Document()
        rendered = itsm_sections._add_configuration_management_section(doc, {
            "configuration_items": [{"id": "CI-001", "name": "Checkout API", "type": "Application"}],
            "relationships": [{"source_ci": "CI-001", "target_ci": "CI-002", "relationship_type": "depends_on"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "Checkout API" in table_texts
        assert "depends_on" in table_texts


class TestRaciMatrixSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_raci_matrix_section(doc, []) is False

    def test_renders_a_row_per_activity(self):
        doc = docx.Document()
        rendered = itsm_sections._add_raci_matrix_section(doc, [
            {
                "process_area": "Incident Management", "activity": "Log Incident",
                "responsible": "Service Desk", "accountable": "Incident Manager",
                "consulted": "", "informed": "Customer",
            },
        ])
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert any("Log Incident" in t for t in table_texts)
        assert "Service Desk" in table_texts
        assert "Incident Manager" in table_texts


class TestToolingAndPlatformSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_tooling_and_platform_section(doc, []) is False

    def test_renders_tooling(self):
        doc = docx.Document()
        rendered = itsm_sections._add_tooling_and_platform_section(doc, [
            {"category": "ITSM Platform", "tool_name": "ServiceNow", "purpose": "Incident/change ticketing"},
        ])
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "ServiceNow" in table_texts


class TestRisksAndControlsSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_risks_and_controls_section(doc, []) is False

    def test_renders_risks(self):
        doc = docx.Document()
        rendered = itsm_sections._add_risks_and_controls_section(doc, [
            {"risk": "Unauthorized change", "control": "CAB approval required for all normal/emergency changes"},
        ])
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert any("Unauthorized change" in t for t in table_texts)

    def test_no_cost_or_date_figure_ever_renders(self):
        # Regression guard, same shape as togaf_sections.py's own migration-
        # planning test -- the schema has no cost/date field anywhere, so
        # this documents the invariant explicitly.
        doc = docx.Document()
        itsm_sections._add_risks_and_controls_section(doc, [
            {"risk": "Budget overrun", "control": "Monthly spend review"},
        ])
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "$" not in text


class TestGlossaryAndReferencesSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert itsm_sections._add_glossary_and_references_section(doc, {}) is False

    def test_renders_glossary_and_references(self):
        doc = docx.Document()
        rendered = itsm_sections._add_glossary_and_references_section(doc, {
            "glossary": [{"term": "CAB", "definition": "Change Advisory Board"}],
            "references": [{"title": "ITIL 4 Foundation", "source": "AXELOS"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "CAB" in table_texts
        assert "ITIL 4 Foundation" in table_texts
