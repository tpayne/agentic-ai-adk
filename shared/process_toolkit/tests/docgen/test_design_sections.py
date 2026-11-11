import types

import docx

from process_toolkit.docgen import design_sections


def test_low_level_design_intro_never_assumes_a_companion_hld_document_exists_by_default():
    # Regression guard: design generation now always produces the HLD and
    # LLD as two SEPARATE documents (see generation.py's _build_hld_
    # document/_build_lld_document), not one combined file with a "Part I"/
    # "Part II" split -- this section's own intro must not reference
    # "Part I" unconditionally the way it used to when it was always
    # nested after an HLD part in the same document.
    doc = docx.Document()
    design_sections._add_low_level_design_section(
        doc, {"components": [{"component_name": "X"}]}, heading="1.0 Low-Level Design",
    )
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Part I" not in text
    assert "companion" not in text.lower()


def test_low_level_design_intro_mentions_the_companion_hld_document_when_told_one_exists():
    doc = docx.Document()
    design_sections._add_low_level_design_section(
        doc, {"components": [{"component_name": "X"}]}, heading="1.0 Low-Level Design",
        has_hld_companion=True,
    )
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "companion" in text.lower()
    assert "Part I" not in text  # the old "(Part I)" phrasing is gone even in this mode


def test_requirements_table_shows_na_for_a_missing_id():
    # Regression test: a requirement record missing "id" (confirmed
    # directly against a real generated design document whose
    # non_functional_requirements were missing it entirely) previously
    # rendered as a BLANK cell in the generated Word document's ID
    # column -- indistinguishable from a rendering bug -- rather than
    # something that's clearly intentional/notable.
    doc = docx.Document()
    design_sections._add_requirements_table(
        doc,
        [{"description": "Backups are encrypted.", "priority": "high", "acceptance_criteria": ["x"]}],
        include_category=False,
    )

    table = doc.tables[0]
    assert table.rows[1].cells[0].text == "N/A"


def test_priority_and_natural_sort_keys():
    assert design_sections._priority_sort_key("high") < design_sections._priority_sort_key("low")
    assert design_sections._natural_sort_key("Requirement 12") == ["requirement ", 12, ""]


def test_bulleted_group_handles_empty_and_values():
    class FakeDoc:
        def __init__(self):
            self.paragraphs = []
            self.runs = []

        def add_paragraph(self, text="", style=None):
            self.paragraphs.append((text, style))

            def add_run(run_text="", **kwargs):
                self.runs.append(run_text)
                return types.SimpleNamespace(bold=None)

            return types.SimpleNamespace(
                paragraph_format=types.SimpleNamespace(
                    left_indent=None, space_before=None, space_after=None
                ),
                add_run=add_run,
            )

    doc = FakeDoc()
    design_sections._add_bulleted_group(doc, "Controls", ["one", "two"], 0.25)
    assert doc.paragraphs
    assert doc.runs[0] == "Controls:"


class TestViewpointsAndViewsSection:
    """Confirmed as a real gap via a live-generated document: Viewpoints
    and Views rendered as two separate, generic tables with no structural
    link between them, even though the schema's own views[].viewpoint_ref
    field exists precisely to express which viewpoint each view realizes.
    _add_viewpoints_and_views_section groups each view under its matching
    viewpoint instead."""

    VIEWPOINTS = [
        {"viewpoint_name": "Governance Viewpoint", "description": "Focus on control.",
         "concerns_addressed": ["Centralized control"], "stakeholders_addressed": ["Security Team"]},
        {"viewpoint_name": "Operational Viewpoint", "description": "Focus on day-to-day running.",
         "concerns_addressed": ["Restore latency"]},
    ]
    VIEWS = [
        {"view_name": "Logical View", "viewpoint_ref": "Governance Viewpoint", "description": "Shows accounts."},
        {"view_name": "Deployment View", "viewpoint_ref": "Operational Viewpoint", "description": "Shows regions."},
    ]

    def _text(self, doc):
        return [p.text for p in doc.paragraphs]

    def test_each_view_is_grouped_under_its_matching_viewpoint(self):
        doc = docx.Document()
        assert design_sections._add_viewpoints_and_views_section(doc, self.VIEWPOINTS, self.VIEWS) is True
        texts = self._text(doc)

        gov_idx = texts.index("Governance Viewpoint")
        op_idx = texts.index("Operational Viewpoint")
        logical_idx = texts.index("Logical View")
        deployment_idx = texts.index("Deployment View")

        # Logical View (ref'd to Governance) appears between the
        # Governance and Operational headings, not after Deployment's own.
        assert gov_idx < logical_idx < op_idx
        assert op_idx < deployment_idx
        assert "Other Views" not in texts

    def test_a_view_with_no_matching_viewpoint_still_renders_under_other_views(self):
        doc = docx.Document()
        views = self.VIEWS + [
            {"view_name": "Orphan View", "viewpoint_ref": "Nonexistent Viewpoint", "description": "No match."}
        ]
        design_sections._add_viewpoints_and_views_section(doc, self.VIEWPOINTS, views)
        texts = self._text(doc)
        assert "Other Views" in texts
        assert "Orphan View" in texts
        assert "No match." in texts
        # Still correctly grouped, not accidentally dumped into Other Views.
        assert "Logical View" in texts[:texts.index("Other Views")]

    def test_a_view_with_no_viewpoints_at_all_still_renders_everything_as_other_views(self):
        doc = docx.Document()
        assert design_sections._add_viewpoints_and_views_section(doc, [], self.VIEWS) is True
        texts = self._text(doc)
        assert "Logical View" in texts
        assert "Deployment View" in texts

    def test_no_op_when_both_are_empty(self):
        doc = docx.Document()
        assert design_sections._add_viewpoints_and_views_section(doc, [], []) is False
        assert not doc.paragraphs

    def test_the_shorter_key_shape_a_live_model_actually_used_also_groups_correctly(self):
        # Confirmed as a real bug via a live-generated document: this
        # function's FIRST version only checked design_document_schema.
        # json's own verbose key names (viewpoint_name/concerns_addressed/
        # stakeholders_addressed/view_name/viewpoint_ref) -- a live model
        # instead used the shorter name/concerns/stakeholders/name/
        # viewpoint for the exact same content, so every viewpoint
        # rendered as a bare "Viewpoint" placeholder and every view fell
        # through to "Other Views" with no match at all.
        doc = docx.Document()
        viewpoints = [
            {"concerns": ["Centralized control"], "name": "Governance Viewpoint",
             "stakeholders": ["Security Team"]},
        ]
        views = [
            {"description": "Shows accounts.", "name": "Logical View", "viewpoint": "Governance Viewpoint"},
        ]
        design_sections._add_viewpoints_and_views_section(doc, viewpoints, views)
        texts = self._text(doc)

        assert "Governance Viewpoint" in texts
        assert texts.count("Viewpoint") == 0  # the generic fallback placeholder never fires
        assert "Centralized control" in "\n".join(texts)
        assert "Security Team" in "\n".join(texts)
        gov_idx = texts.index("Governance Viewpoint")
        logical_idx = texts.index("Logical View")
        assert gov_idx < logical_idx
        assert "Other Views" not in texts

    def test_view_name_renders_as_a_real_heading_not_a_bold_paragraph_run(self):
        # Confirmed as a real readability gap via a live-generated
        # document: view names used to render as a bold paragraph RUN,
        # visually and structurally inconsistent with every other
        # navigational element in this document, which uses a real
        # Heading style.
        doc = docx.Document()
        design_sections._add_view_entry(doc, {"name": "Logical View", "description": "d"})
        heading_paragraph = next(p for p in doc.paragraphs if p.text == "Logical View")
        assert heading_paragraph.style.name.startswith("Heading")

    def test_a_view_with_elements_gets_a_real_generated_diagram(self):
        doc = docx.Document()
        design_sections._add_view_entry(
            doc, {"name": "Logical View", "elements": ["Management Account", "Workload Account", "Backup Account"]},
        )
        assert len(doc.inline_shapes) == 1

    def test_a_view_with_no_diagram_renders_no_placeholder_note(self):
        # Confirmed via direct user feedback: a cluster of "[Diagram not
        # yet generated]" notes across several views in the same short
        # section reads as broken/unfinished, not honest -- no note
        # renders when there's no diagram, but the view's own real
        # name/description still always do.
        doc = docx.Document()
        design_sections._add_view_entry(doc, {"name": "Logical View", "description": "d"})
        texts = [p.text for p in doc.paragraphs]
        assert not doc.inline_shapes
        assert not any("not yet generated" in t for t in texts)
        assert "Logical View" in texts
        assert "d" in texts

    # Confirmed as a real gap via a live-generated document: a generating
    # agent never populates a view's own elements[]/diagrams[], so EVERY
    # view fell through to the honest-but-unhelpful fallback note, even
    # for a "Logical View"/"Deployment View" whose own content already
    # exists elsewhere in the same design JSON (high_level_design's own
    # integration_points / deployment_topology.environments) and is
    # ALREADY drawn once for the overall Architecture Flow Diagram.
    # _infer_view_context_from_high_level_design closes this gap by
    # choosing WHICH of that real data to visualize, based on the view's
    # own name -- never fabricating anything new.

    def test_a_logical_view_with_no_own_data_draws_from_integration_points(self):
        doc = docx.Document()
        high_level_design = {
            "integration_points": [{"source": "A", "target": "B", "protocol": "HTTPS"}],
        }
        design_sections._add_view_entry(
            doc, {"name": "Logical View", "description": "d"}, high_level_design=high_level_design,
        )
        assert len(doc.inline_shapes) == 1
        texts = [p.text for p in doc.paragraphs]
        assert not any("not yet generated" in t for t in texts)

    def test_a_deployment_view_with_no_own_data_draws_from_deployment_topology(self):
        doc = docx.Document()
        high_level_design = {
            "deployment_topology": {"environments": [{"name": "Production", "infrastructure": "AWS"}]},
        }
        design_sections._add_view_entry(
            doc, {"name": "Deployment View", "description": "d"}, high_level_design=high_level_design,
        )
        assert len(doc.inline_shapes) == 1

    def test_an_infrastructure_view_with_component_dependencies_draws_from_components_not_environments(self):
        # Regression test: "infrastructure" used to match the "deployment"
        # bucket FIRST, so an "Infrastructure View" whose own description
        # named concrete components (VPC, subnets, RDS instances, security
        # services) still drew a bare single-box "Production" diagram from
        # deployment_topology.environments instead of the far richer
        # multi-node components graph -- confirmed directly against a real
        # generated document. "components" (with real dependencies) must
        # win over a thin one-environment deployment_topology here.
        doc = docx.Document()
        high_level_design = {
            "components": [
                {"component_name": "RDS Instance", "dependencies": ["VPC Private Subnets", "KMS Key"]},
                {"component_name": "VPC Private Subnets", "dependencies": []},
                {"component_name": "KMS Key", "dependencies": []},
            ],
            "deployment_topology": {"environments": [{"name": "Production", "infrastructure": "AWS Cloud"}]},
        }
        design_sections._add_view_entry(
            doc,
            {
                "name": "Infrastructure View",
                "description": "Visual representation of the VPC, subnets, RDS instances, and security services.",
            },
            high_level_design=high_level_design,
        )
        assert len(doc.inline_shapes) == 1

    def test_an_infrastructure_view_with_no_component_dependencies_falls_back_to_environments(self):
        doc = docx.Document()
        high_level_design = {
            "deployment_topology": {"environments": [{"name": "Production", "infrastructure": "AWS Cloud"}]},
        }
        design_sections._add_view_entry(
            doc, {"name": "Infrastructure View", "description": "d"}, high_level_design=high_level_design,
        )
        assert len(doc.inline_shapes) == 1

    def test_a_view_name_matching_no_keyword_renders_no_diagram_and_no_wrong_guess(self):
        # "Process View" has no plausible high_level_design-level data
        # source (no sequence flows at the HLD level) -- it must not draw
        # the wrong (unrelated) diagram just because SOME high_level_design
        # data happens to exist; its own name/description still render.
        doc = docx.Document()
        high_level_design = {
            "integration_points": [{"source": "A", "target": "B"}],
            "deployment_topology": {"environments": [{"name": "Production"}]},
        }
        design_sections._add_view_entry(
            doc, {"name": "Process View", "description": "d"}, high_level_design=high_level_design,
        )
        assert not doc.inline_shapes
        texts = [p.text for p in doc.paragraphs]
        assert not any("not yet generated" in t for t in texts)
        assert "Process View" in texts
        assert "d" in texts


class TestHldComponentsSection:
    """Confirmed as a real readability bug via a live-generated document:
    the generic fallback renderer this replaces showed each component's
    OWN JSON key order, so "Dependencies" rendered as the very FIRST line
    for one component and not at all for a sibling with none -- a fixed
    field order fixes this."""

    def _text(self, doc):
        return [p.text for p in doc.paragraphs]

    def test_fields_render_in_a_fixed_order_regardless_of_source_json_key_order(self):
        doc = docx.Document()
        components = [
            {"dependencies": ["Tenant_Workload_Account"], "component_name": "Dedicated_Backup_Account",
             "description": "Central vault.", "owner": "Platform Team", "type": "Hub Account"},
        ]
        design_sections._add_hld_components_section(doc, components)
        texts = self._text(doc)

        desc_idx = texts.index("Central vault.")
        type_idx = next(i for i, t in enumerate(texts) if t.startswith("Type:"))
        owner_idx = next(i for i, t in enumerate(texts) if t.startswith("Owner:"))
        deps_idx = texts.index("Dependencies:")
        assert desc_idx < type_idx < owner_idx < deps_idx

    def test_no_op_on_empty_input(self):
        doc = docx.Document()
        assert design_sections._add_hld_components_section(doc, []) is False
        assert not doc.paragraphs


class TestIntegrationPointsTable:
    def test_renders_as_a_table_not_repeated_prose_blocks(self):
        doc = docx.Document()
        items = [
            {"source": "Tenant_Workload_Account", "target": "Dedicated_Backup_Account",
             "integration_pattern": "Cross-Account Backup Copy", "protocol": "AWS Internal",
             "description": "Automated copy."},
        ]
        assert design_sections._add_integration_points_table(doc, items) is True
        assert len(doc.tables) == 1
        table = doc.tables[0]
        assert table.rows[0].cells[0].text == "Source"
        assert table.rows[1].cells[0].text == "Tenant_Workload_Account"

    def test_source_component_synonym_is_tolerated(self):
        doc = docx.Document()
        items = [{"source_component": "A", "target_component": "B", "description": "x"}]
        design_sections._add_integration_points_table(doc, items)
        table = doc.tables[0]
        assert table.rows[1].cells[0].text == "A"
        assert table.rows[1].cells[1].text == "B"

    def test_no_op_on_empty_input(self):
        doc = docx.Document()
        assert design_sections._add_integration_points_table(doc, []) is False


class TestTechnologyStackTable:
    def test_renders_as_a_table_not_repeated_prose_blocks(self):
        doc = docx.Document()
        items = [
            {"technology": "AWS Backup", "category": "Backup Service", "version": "Managed",
             "license": "AWS Managed", "justification": "Native AWS service."},
        ]
        assert design_sections._add_technology_stack_table(doc, items) is True
        table = doc.tables[0]
        assert table.rows[0].cells[0].text == "Technology"
        assert table.rows[1].cells[0].text == "AWS Backup"

    def test_no_op_on_empty_input(self):
        doc = docx.Document()
        assert design_sections._add_technology_stack_table(doc, []) is False


class TestArchitectureDecisionsSection:
    """architecture_decisions[] has deliberately no status/date/decided_by
    column -- design_document_schema.json's own comment documents that an
    earlier, near-identical field was removed because it produced
    fabricated decision-meeting content; this renderer simply has no such
    field to show, by design, not by oversight."""

    def test_renders_id_context_decision_alternatives_and_consequences(self):
        doc = docx.Document()
        decisions = [{
            "id": "ADR-001", "title": "Event-Driven vs. Synchronous Checkout",
            "context": "NFR-001 requires sub-second latency.",
            "decision": "Adopt event-driven microservices.",
            "alternatives_considered": [
                {"option": "Monolith", "rejected_because": "Does not scale under peak load."},
            ],
            "consequences": "Requires eventual-consistency handling.",
        }]
        assert design_sections._add_architecture_decisions_section(doc, decisions) is True
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "ADR-001: Event-Driven vs. Synchronous Checkout" in text
        assert "NFR-001 requires sub-second latency." in text
        assert "Adopt event-driven microservices." in text
        assert "Monolith -- rejected because Does not scale under peak load." in text
        assert "Requires eventual-consistency handling." in text
        # No status/date/decided_by field exists on the schema for this --
        # confirm the renderer never fabricates one even if asked to show it.
        assert "Status" not in text
        assert "Decided By" not in text

    def test_entries_are_sorted_by_id(self):
        doc = docx.Document()
        decisions = [
            {"id": "ADR-002", "title": "Second"},
            {"id": "ADR-001", "title": "First"},
        ]
        design_sections._add_architecture_decisions_section(doc, decisions)
        headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 3"]
        assert headings == ["ADR-001: First", "ADR-002: Second"]

    def test_no_op_on_empty_input(self):
        doc = docx.Document()
        assert design_sections._add_architecture_decisions_section(doc, []) is False
        assert not doc.paragraphs


class TestRequirementsTraceabilityTable:
    """Joins requirements[] against each component's own
    satisfies_requirements AND requirements.traceability_matrix[]'s own
    verification_method -- shows "—" for a column with no source data
    rather than omitting the row, so a reviewer sees the gap directly."""

    def _requirements(self):
        return {
            "functional_requirements": [{"id": "FR-001", "description": "x"}],
            "non_functional_requirements": [{"id": "NFR-001", "description": "y"}],
        }

    def test_joins_satisfies_requirements_and_verification_method(self):
        doc = docx.Document()
        requirements = dict(self._requirements())
        requirements["traceability_matrix"] = [
            {"requirement_id": "FR-001", "design_element_id": "Checkout API", "verification_method": "test"},
        ]
        high_level_design = {"components": [
            {"component_name": "Checkout API", "satisfies_requirements": ["FR-001", "NFR-001"]},
        ]}
        assert design_sections._add_requirements_traceability_table(
            doc, requirements, high_level_design, {}
        ) is True
        table = doc.tables[0]
        rows = {row.cells[0].text: [c.text for c in row.cells] for row in table.rows[1:]}
        assert rows["FR-001"] == ["FR-001", "Checkout API", "Test"]
        # NFR-001 is satisfied by the component but has no traceability_matrix
        # entry -- the verification method column shows the gap, not a blank.
        assert rows["NFR-001"] == ["NFR-001", "Checkout API", "—"]

    def test_shows_em_dash_for_an_unsatisfied_requirement(self):
        doc = docx.Document()
        requirements = {"functional_requirements": [{"id": "FR-001", "description": "x"}]}
        high_level_design = {"components": [{"component_name": "Other", "satisfies_requirements": ["FR-999"]}]}
        design_sections._add_requirements_traceability_table(doc, requirements, high_level_design, {})
        table = doc.tables[0]
        row = table.rows[1]
        assert row.cells[0].text == "FR-001"
        assert row.cells[1].text == "—"
        assert row.cells[2].text == "—"

    def test_low_level_design_components_are_also_joined(self):
        doc = docx.Document()
        requirements = {"functional_requirements": [{"id": "FR-001", "description": "x"}]}
        low_level_design = {"components": [
            {"component_name": "Checkout API", "satisfies_requirements": ["FR-001"]},
        ]}
        design_sections._add_requirements_traceability_table(doc, requirements, {}, low_level_design)
        table = doc.tables[0]
        assert table.rows[1].cells[1].text == "Checkout API"

    def test_no_op_when_neither_satisfies_requirements_nor_traceability_matrix_present(self):
        doc = docx.Document()
        requirements = self._requirements()
        assert design_sections._add_requirements_traceability_table(doc, requirements, {}, {}) is False
        assert not doc.tables

    def test_no_op_on_no_requirements(self):
        doc = docx.Document()
        assert design_sections._add_requirements_traceability_table(doc, {}, {}, {}) is False


class TestRequirementsSectionTraceabilitySubsection:
    """_add_requirements_section's own integration of the traceability
    table as a trailing numbered subsection."""

    def test_traceability_subsection_appears_when_data_present(self):
        doc = docx.Document()
        requirements = {
            "functional_requirements": [{"id": "FR-001", "description": "x"}],
        }
        high_level_design = {"components": [
            {"component_name": "Checkout API", "satisfies_requirements": ["FR-001"]},
        ]}
        design_sections._add_requirements_section(
            doc, requirements, heading="3.0 Requirements",
            high_level_design=high_level_design, low_level_design={},
        )
        headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
        assert "3.2 Requirements Traceability" in headings
        assert len(doc.tables) == 2  # functional requirements table + traceability table

    def test_traceability_heading_is_removed_when_nothing_to_show(self):
        # Confirms the heading added speculatively is cleaned up again
        # rather than left dangling above an empty subsection when neither
        # satisfies_requirements nor traceability_matrix has any data.
        doc = docx.Document()
        requirements = {"functional_requirements": [{"id": "FR-001", "description": "x"}]}
        design_sections._add_requirements_section(
            doc, requirements, heading="3.0 Requirements",
            high_level_design={}, low_level_design={},
        )
        headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
        assert "3.2 Requirements Traceability" not in headings
        assert len(doc.tables) == 1  # only the functional requirements table

    def test_no_traceability_subsection_when_design_args_not_passed(self):
        doc = docx.Document()
        requirements = {"functional_requirements": [{"id": "FR-001", "description": "x"}]}
        design_sections._add_requirements_section(doc, requirements, heading="3.0 Requirements")
        headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
        assert "Requirements Traceability" not in "\n".join(headings)


class TestOperationalReadinessSection:
    def test_renders_ownership_support_fields_and_runbooks_table(self):
        doc = docx.Document()
        data = {
            "ownership": {"team": "Checkout Platform Team", "contact": "checkout-team@example.com"},
            "support_model": "24/7 on-call rotation.",
            "escalation_path": "PagerDuty -> On-Call -> Lead.",
            "monitoring_strategy": "CheckoutFailed events monitored via CloudWatch.",
            "alerting_strategy": "Alert on failure rate > 1%.",
            "maintenance_activities": ["Quarterly upgrade window."],
            "runbooks": [{"title": "Outage", "trigger": "Failure spike", "reference": "runbooks/outage.md"}],
        }
        assert design_sections._add_operational_readiness_section(doc, data) is True
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Checkout Platform Team" in text
        assert "checkout-team@example.com" in text
        assert "24/7 on-call rotation." in text
        assert "PagerDuty -> On-Call -> Lead." in text
        assert "Quarterly upgrade window." in text
        table = doc.tables[0]
        assert table.rows[0].cells[0].text == "Title"
        assert table.rows[1].cells[0].text == "Outage"

    def test_no_op_on_empty_input(self):
        doc = docx.Document()
        assert design_sections._add_operational_readiness_section(doc, {}) is False
        assert not doc.paragraphs

    def test_no_op_when_all_fields_are_empty(self):
        doc = docx.Document()
        data = {"ownership": {"team": "", "contact": ""}, "support_model": "", "maintenance_activities": []}
        assert design_sections._add_operational_readiness_section(doc, data) is False


class TestReviewGovernanceChecklistSection:
    """Only sign_off_criteria/reconsideration_triggers render -- NOT
    review_history/change_log/approval_workflow, which stay unrendered
    elsewhere to avoid displaying fabricated reviewer names/dates."""

    def test_renders_sign_off_criteria_and_reconsideration_triggers(self):
        doc = docx.Document()
        data = {
            "sign_off_criteria": ["All NFR targets demonstrated via load test."],
            "reconsideration_triggers": ["Checkout volume exceeds 3x current peak."],
        }
        assert design_sections._add_review_governance_checklist_section(doc, data) is True
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "All NFR targets demonstrated via load test." in text
        assert "Checkout volume exceeds 3x current peak." in text

    def test_review_history_and_approval_workflow_are_never_rendered(self):
        doc = docx.Document()
        data = {
            "review_history": [{"reviewer": "Jane Doe", "date": "2026-01-01", "status": "approved"}],
            "approval_workflow": {"current_status": "approved"},
            "change_log": [{"version": "1.0", "author": "Someone"}],
        }
        assert design_sections._add_review_governance_checklist_section(doc, data) is False
        assert not doc.paragraphs

    def test_no_op_on_empty_input(self):
        doc = docx.Document()
        assert design_sections._add_review_governance_checklist_section(doc, {}) is False
