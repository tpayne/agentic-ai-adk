import docx

from process_toolkit.docgen import togaf_sections


def _headings(doc) -> list:
    return [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]


class TestArchitectureVisionSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_architecture_vision_section(doc, {}) is False
        assert togaf_sections._add_architecture_vision_section(doc, None) is False

    def test_renders_stakeholders_scope_and_risks(self):
        doc = docx.Document()
        rendered = togaf_sections._add_architecture_vision_section(doc, {
            "problem_statement": "Manual onboarding is slow.",
            "vision_statement": "A self-service portal.",
            "business_goals": ["Reduce onboarding time"],
            "stakeholders": [{"name": "Jane", "role": "Sponsor", "concerns": ["Budget"]}],
            "scope": {"in_scope": ["Portal"], "out_of_scope": ["Legacy migration"]},
            "risks_and_mitigations": [{"id": "R-1", "description": "Data loss", "mitigation": "Backups"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "Jane" in table_texts
        assert "R-1" in table_texts


class TestArchitectureRequirementsSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_architecture_requirements_section(doc, {}) is False

    def test_renders_functional_and_non_functional_and_traceability(self):
        doc = docx.Document()
        rendered = togaf_sections._add_architecture_requirements_section(doc, {
            "functional_requirements": [{"id": "FR-001", "description": "Create a backup."}],
            "non_functional_requirements": [{"id": "NFR-001", "characteristic": "Security", "description": "Encrypted."}],
            "traceability_matrix": [{"requirement_id": "FR-001", "satisfied_by": ["APP-001"]}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "FR-001" in table_texts
        assert "NFR-001" in table_texts
        assert any("APP-001" in t for t in table_texts)


class TestArchitecturePrinciplesSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_architecture_principles_section(doc, []) is False

    def test_renders_one_card_per_principle(self):
        doc = docx.Document()
        rendered = togaf_sections._add_architecture_principles_section(doc, [
            {"id": "PRIN-001", "name": "Data is a shared asset", "statement": "Data is managed centrally.",
             "rationale": "Avoid silos.", "implications": ["Requires a data steward."]},
        ])
        assert rendered is True
        headings = _headings(doc)
        assert any("PRIN-001" in h for h in headings)


class TestBusinessArchitectureSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_business_architecture_section(doc, {}) is False

    def test_renders_capabilities_and_value_streams(self):
        doc = docx.Document()
        rendered = togaf_sections._add_business_architecture_section(doc, {
            "capabilities": [{"id": "CAP-001", "name": "Supplier Onboarding", "description": "Onboard suppliers."}],
            "value_streams": [{"name": "Onboard to Active", "description": "...", "stages": ["Apply", "Approve"]}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "CAP-001" in table_texts

    def test_renders_an_honest_fallback_note_when_the_diagram_has_no_drawable_data(self):
        doc = docx.Document()
        togaf_sections._add_business_architecture_section(doc, {
            "capability_map_diagram": {"diagram_id": "D-1", "title": "Capability Map"},
        })
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "not yet generated" in text


class TestDataArchitectureSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_data_architecture_section(doc, {}) is False

    def test_renders_entities_and_flows(self):
        doc = docx.Document()
        rendered = togaf_sections._add_data_architecture_section(doc, {
            "data_entities": [{"name": "Supplier", "description": "A supplier record."}],
            "data_flows": [{"source": "Portal", "target": "Finance System", "description": "Sync"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "Supplier" in table_texts
        assert "Finance System" in table_texts


class TestApplicationArchitectureSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_application_architecture_section(doc, {}) is False

    def test_renders_components_and_communications(self):
        doc = docx.Document()
        rendered = togaf_sections._add_application_architecture_section(doc, {
            "application_components": [{"name": "Portal", "realizes_capabilities": ["CAP-001"]}],
            "application_communications": [{"source": "Portal", "target": "Finance System", "protocol": "REST"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "Portal" in table_texts
        assert "REST" in table_texts


class TestTechnologyArchitectureSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_technology_architecture_section(doc, {}) is False

    def test_renders_the_technology_portfolio(self):
        doc = docx.Document()
        rendered = togaf_sections._add_technology_architecture_section(doc, {
            "technology_portfolio": [{"category": "Database", "technology": "PostgreSQL", "version": "15"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "PostgreSQL" in table_texts


class TestOpportunitiesAndSolutionsSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_opportunities_and_solutions_section(doc, []) is False

    def test_renders_a_row_per_gap(self):
        doc = docx.Document()
        rendered = togaf_sections._add_opportunities_and_solutions_section(doc, [
            {"id": "GAP-001", "gap_description": "No self-service portal.", "grounded_in": ["FR-001"]},
        ])
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "GAP-001" in table_texts


class TestMigrationPlanningSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_migration_planning_section(doc, {}) is False

    def test_renders_work_packages_with_no_dates_or_budget_fields(self):
        doc = docx.Document()
        rendered = togaf_sections._add_migration_planning_section(doc, {
            "work_packages": [{"id": "WP-001", "name": "Build Portal", "depends_on": [], "delivers": ["CAP-001"]}],
            "sequencing_notes": "WP-001 first, since nothing depends on it.",
        })
        assert rendered is True
        headings = _headings(doc)
        assert any("WP-001" in h for h in headings)
        text = "\n".join(p.text for p in doc.paragraphs)
        # Regression guard: Migration Planning must never render a date,
        # budget, or team-capacity figure -- the schema has no such field
        # at all, so this is really asserting the test fixture itself
        # carries none, but documents the invariant explicitly.
        assert "$" not in text


class TestArchitectureComplianceAssessmentSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_architecture_compliance_assessment_section(doc, {}) is False

    def test_renders_compliance_findings(self):
        doc = docx.Document()
        rendered = togaf_sections._add_architecture_compliance_assessment_section(doc, {
            "compliance_findings": [{"standard_or_requirement": "PCI-DSS", "status": "compliant", "reference": "RISK-002"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "PCI-DSS" in table_texts


class TestGlossaryAndReferencesSection:
    def test_empty_input_is_a_no_op(self):
        doc = docx.Document()
        assert togaf_sections._add_glossary_and_references_section(doc, {}) is False

    def test_renders_glossary_and_references(self):
        doc = docx.Document()
        rendered = togaf_sections._add_glossary_and_references_section(doc, {
            "glossary": [{"term": "ADM", "definition": "Architecture Development Method"}],
            "references": [{"title": "TOGAF Standard", "source": "The Open Group"}],
        })
        assert rendered is True
        table_texts = [c.text for t in doc.tables for row in t.rows for c in row.cells]
        assert "ADM" in table_texts
        assert "TOGAF Standard" in table_texts
