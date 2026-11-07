import docx

from process_toolkit.docgen.content import (
    _resolve_index_references, _add_process_steps_section, _add_stakeholders_section,
    _add_design_overview_section, _render_generic_value,
)


def _all_text(doc):
    return [p.text for p in doc.paragraphs]


class TestResolveIndexReferences:
    """_resolve_index_references -- a process step's own
    risks_and_controls/change_management/continuous_improvement
    sometimes comes back as bare integers referencing positions in the
    process-wide list of the same name, instead of the documented
    {"risk", "control"}-shaped (etc.) objects -- confirmed directly
    against a real generated document where every step rendered literal
    "0"/"2"/"4" bullets instead of any real risk/control text."""

    def test_resolves_valid_indices_to_real_objects(self):
        top_level = [{"risk": "A"}, {"risk": "B"}, {"risk": "C"}, {"risk": "D"}, {"risk": "E"}]
        assert _resolve_index_references([0, 2, 4], top_level) == [
            {"risk": "A"}, {"risk": "C"}, {"risk": "E"},
        ]

    def test_out_of_range_indices_are_dropped_not_rendered_as_content(self):
        top_level = [{"risk": "A"}, {"risk": "B"}]
        assert _resolve_index_references([0, 5, 1], top_level) == [{"risk": "A"}, {"risk": "B"}]

    def test_all_out_of_range_resolves_to_empty_not_the_bare_indices(self):
        top_level = [{"risk": "A"}]
        assert _resolve_index_references([5, 6], top_level) == []

    def test_no_top_level_list_resolves_to_empty_not_the_bare_indices(self):
        assert _resolve_index_references([0, 2], None) == []
        assert _resolve_index_references([0, 2], []) == []

    def test_well_formed_object_list_passes_through_unchanged(self):
        # The documented shape (list of {"risk", "control"} objects, not
        # bare integers) must never be altered by this guard.
        value = [{"risk": "A", "control": "X"}]
        assert _resolve_index_references(value, [{"risk": "unrelated"}]) is value

    def test_non_list_value_passes_through_unchanged(self):
        assert _resolve_index_references(None, [{"risk": "A"}]) is None
        assert _resolve_index_references("some string", [{"risk": "A"}]) == "some string"

    def test_booleans_are_not_treated_as_indices(self):
        # isinstance(True, int) is True in Python -- must not let a
        # stray boolean list slip through the "all bare ints" check.
        value = [True, False]
        assert _resolve_index_references(value, [{"risk": "A"}]) is value


class TestAddProcessStepsSectionResolvesIndexReferences:
    """End-to-end: a step whose risks_and_controls/change_management/
    continuous_improvement are index-reference lists (the real shape
    seen from a live generation run) must render the REAL referenced
    content, not bare numbers."""

    def test_index_reference_step_renders_real_risk_control_text(self):
        doc = docx.Document()
        steps = [{
            "step_name": "Screen Candidates",
            "description": "x" * 10,
            "step_risks_and_controls": [0, 2],
        }]
        top_level_risks_and_controls = [
            {"risk": "Legal liability from discrimination.", "control": "Merit-based criteria."},
            {"risk": "Unrelated risk.", "control": "Unrelated control."},
            {"risk": "Data breach.", "control": "Encryption at rest."},
        ]

        _add_process_steps_section(
            doc, steps, top_level_risks_and_controls=top_level_risks_and_controls,
        )

        text = _all_text(doc)
        assert any("Legal liability from discrimination." in t for t in text)
        assert any("Data breach." in t for t in text)
        # Index 1 wasn't referenced -- its content must not appear.
        assert not any("Unrelated risk." in t for t in text)
        # The bare index values themselves must never appear as bullets.
        assert not any(t.strip() in ("• 0", "• 2") for t in text)

    def test_step_with_only_out_of_range_indices_renders_no_section(self):
        doc = docx.Document()
        steps = [{
            "step_name": "Some Step",
            "description": "x" * 10,
            "change_management": [7],
        }]

        _add_process_steps_section(doc, steps, top_level_change_management=[{"change_request_process": "A"}])

        text = _all_text(doc)
        assert not any("Change Management" in t for t in text)

    def test_well_formed_step_level_content_still_renders_normally(self):
        # A step that already has REAL, well-formed risk/control objects
        # (not index references) must render exactly as before -- this
        # fix must not regress the already-working case.
        doc = docx.Document()
        steps = [{
            "step_name": "Some Step",
            "description": "x" * 10,
            "step_risks_and_controls": [{"risk": "Direct risk.", "control": "Direct control."}],
        }]

        _add_process_steps_section(doc, steps, top_level_risks_and_controls=[{"risk": "Unrelated."}])

        text = _all_text(doc)
        assert any("Direct risk." in t for t in text)


class TestStakeholdersSection:
    """_add_stakeholders_section -- shared across process/design/
    architecture/requirements documents. Confirms the base 2-column
    shape is unchanged for callers that don't populate interest/
    approval_authority, and that both columns appear (independently)
    when at least one stakeholder entry actually has that data."""

    def test_is_a_noop_when_empty(self):
        doc = docx.Document()
        assert _add_stakeholders_section(doc, None) is False
        assert _add_stakeholders_section(doc, []) is False

    def test_plain_string_list_renders_as_bullets_not_a_table(self):
        doc = docx.Document()
        assert _add_stakeholders_section(doc, ["Legal SME", "Contract Manager"]) is True
        assert doc.tables == []
        bullets = [p.text for p in doc.paragraphs if p.style and p.style.name == "List Bullet"]
        assert bullets == ["Legal SME", "Contract Manager"]

    def test_dict_list_without_interest_or_authority_renders_the_original_two_columns(self):
        doc = docx.Document()
        stakeholders = [{"name": "Legal SME", "responsibilities": ["Review contract clauses."]}]
        assert _add_stakeholders_section(doc, stakeholders) is True
        table = doc.tables[0]
        assert [c.text for c in table.rows[0].cells] == ["Stakeholder", "Responsibilities"]
        assert table.rows[1].cells[0].text == "Legal SME"

    def test_interest_and_approval_authority_columns_appear_when_present(self):
        doc = docx.Document()
        stakeholders = [{
            "name": "Contract Manager", "responsibilities": ["Owns the business relationship."],
            "interest": "High", "approval_authority": "Yes",
        }]
        assert _add_stakeholders_section(doc, stakeholders) is True
        table = doc.tables[0]
        assert [c.text for c in table.rows[0].cells] == [
            "Stakeholder", "Responsibilities", "Interest", "Approval Authority",
        ]
        assert table.rows[1].cells[2].text == "High"
        assert table.rows[1].cells[3].text == "Yes"

    def test_a_row_missing_interest_still_renders_a_blank_cell_not_a_column_shift(self):
        # One stakeholder has "interest", another doesn't -- the column
        # still appears (since at least one entry has it), and the
        # entry without it gets a blank cell rather than misaligned data.
        doc = docx.Document()
        stakeholders = [
            {"name": "Contract Manager", "interest": "High"},
            {"name": "Legal SME"},
        ]
        assert _add_stakeholders_section(doc, stakeholders) is True
        table = doc.tables[0]
        assert table.rows[1].cells[2].text == "High"
        assert table.rows[2].cells[2].text == ""


class TestDesignOverviewSectionBusinessContextLists:
    """Confirmed as a real bug via a live-generated document: objectives/
    business_drivers/assumptions/constraints entries shaped as
    {"description": "...", "type": "..."} (the real schema shape, not a
    bare string) rendered as literal Python dict repr -- "{'description':
    'Enforce uniform backup processes...'}" -- because this section used
    str(item) directly instead of _item_text(item, "description"), unlike
    every sibling list-of-dict renderer elsewhere in this module."""

    def test_dict_shaped_business_context_entries_render_as_plain_text_not_dict_repr(self):
        doc = docx.Document()
        data = {
            "document_metadata": {"system_name": "X"},
            "business_context": {
                "purpose": "Test purpose.",
                "objectives": [{"description": "Enforce uniform backup processes."}],
                "business_drivers": [{"description": "Ensure data resilience."}],
                "assumptions": [{"type": "infrastructure", "description": "Landing zone follows best practices."}],
                "constraints": [{"description": "Must use AWS Backup.", "type": "technical"}],
            },
        }
        _add_design_overview_section(doc, data)
        texts = [p.text for p in doc.paragraphs]
        assert "Enforce uniform backup processes." in texts
        assert "Ensure data resilience." in texts
        assert "Landing zone follows best practices." in texts
        assert "Must use AWS Backup." in texts
        assert not any("{'description'" in t or '{"description"' in t for t in texts)

    def test_bare_string_business_context_entries_still_render_unchanged(self):
        # _item_text falls back to str(item) for non-dict entries, so the
        # older/simpler plain-string schema shape keeps working too.
        doc = docx.Document()
        data = {
            "document_metadata": {},
            "business_context": {"objectives": ["Reduce latency."]},
        }
        _add_design_overview_section(doc, data)
        texts = [p.text for p in doc.paragraphs]
        assert "Reduce latency." in texts


class TestRenderGenericValueAcronymLabels:
    """Confirmed as a real bug via a live-generated document: a dict field
    like availability_and_resilience's own {"rto": ..., "rpo": ...}
    rendered as "Rto: 4 hours" / "Rpo: 12 hours" -- str.title() uppercases
    only each word's first letter, which is wrong for an acronym. Every
    dict-of-scalars value renders through the SAME merged_labels/
    combined_label path (even a dict with no duplicate values -- see
    _render_generic_value's own merged_labels construction), so this single
    path covers both the common case and the "two keys share one value"
    merge case."""

    def test_acronym_keys_render_fully_capitalized_not_title_cased(self):
        doc = docx.Document()
        _render_generic_value(
            doc, {"rto": "4 hours", "rpo": "12 hours", "backup_strategy": "daily"}, label="Availability"
        )
        texts = [p.text for p in doc.paragraphs]
        assert any(t.startswith("RTO: 4 hours") for t in texts)
        assert any(t.startswith("RPO: 12 hours") for t in texts)
        assert any(t.startswith("Backup Strategy: daily") for t in texts)

    def test_duplicate_valued_acronym_keys_merge_into_a_combined_label(self):
        # Two keys sharing the exact same text value get merged into one
        # "KEY1 / KEY2:" line (merged_labels) -- confirmed this specific
        # path (not just the single-key path) also uses the acronym-aware
        # label, since a prior fix attempt broke ONLY this path (a regex
        # substitution corrupted the "kk" loop variable here specifically).
        doc = docx.Document()
        _render_generic_value(doc, {"rto": "4 hours", "sla": "4 hours"})
        texts = [p.text for p in doc.paragraphs]
        assert any(t.startswith("RTO / SLA: 4 hours") for t in texts)


class TestDesignOverviewSectionDocumentTypeLabel:
    """Confirmed as a real bug via a live-generated document: the HLD
    document's own body text printed "Document Type: Combined" -- the raw
    document_metadata.document_type value -- even though design
    generation always persists document_type="Combined" in the underlying
    JSON regardless of which file(s) actually get rendered (see
    generation.py's own _build_design_documents), and this function only
    ever builds the HLD half (_build_lld_document never calls it). A
    reader of just the HLD file seeing "Document Type: Combined" with no
    LLD file in sight is misleading."""

    def test_document_type_always_shows_high_level_design_not_the_raw_json_value(self):
        doc = docx.Document()
        data = {"document_metadata": {"document_type": "Combined"}, "business_context": {}}
        _add_design_overview_section(doc, data)
        texts = [p.text for p in doc.paragraphs]
        assert "Document Type: High-Level Design" in texts
        assert not any("Document Type: Combined" in t for t in texts)
