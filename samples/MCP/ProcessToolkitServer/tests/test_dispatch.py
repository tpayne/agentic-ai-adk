"""Unit tests for dispatch.py's DOMAINS table and its composed helpers --
exercised by calling the module's own functions directly, never through an
MCP client/transport (that full-stack coverage lives in test_server.py).
"""

import pytest

import dispatch


class TestDomainsTable:
    @pytest.mark.parametrize("schema_type", sorted(dispatch.DOMAINS))
    def test_every_domain_has_callable_template_context_validate_persist(self, schema_type):
        ops = dispatch.DOMAINS[schema_type]
        assert callable(ops.load_template)
        assert callable(ops.load_context)
        assert callable(ops.validate)
        assert callable(ops.persist)

    @pytest.mark.parametrize("schema_type", sorted(dispatch.DOMAINS))
    def test_load_template_returns_a_fresh_copy_each_call(self, schema_type):
        ops = dispatch.DOMAINS[schema_type]
        first = ops.load_template()
        first["_mutated"] = True
        second = ops.load_template()
        assert "_mutated" not in second

    def test_only_design_and_togaf_declare_a_document_variant_kwarg(self):
        variant_domains = {name for name, ops in dispatch.DOMAINS.items() if ops.doc_variant_kwarg}
        assert variant_domains == {"design", "togaf"}
        assert dispatch.DOMAINS["design"].doc_variant_kwarg == "design_variant"
        assert dispatch.DOMAINS["togaf"].doc_variant_kwarg == "togaf_variant"

    def test_only_design_and_process_declare_a_whole_document_diagram(self):
        diagram_domains = {name for name, ops in dispatch.DOMAINS.items() if ops.has_diagram}
        assert diagram_domains == {"design", "process"}

    def test_persist_is_native_matches_which_domains_have_their_own_persist_final(self):
        native = {name for name, ops in dispatch.DOMAINS.items() if ops.persist_is_native}
        assert native == {"design", "togaf", "process"}


class TestValidateThenSave:
    """Direct unit coverage of the _validate_then_save composition, with
    stub validate/save functions -- isolates the control flow (validate
    first, only call save if valid, never swallow the save function's own
    return message) from any real domain's validation rules."""

    def test_calls_save_and_returns_its_message_when_valid(self):
        calls = []
        persist = dispatch._validate_then_save(
            validate_fn=lambda data: {"valid": True, "issues": []},
            save_fn=lambda data: calls.append(data) or "SUCCESS: saved it",
        )
        result = persist({"some": "data"})
        assert result == "SUCCESS: saved it"
        assert calls == [{"some": "data"}]

    def test_never_calls_save_when_invalid_and_reports_the_issues(self):
        calls = []
        persist = dispatch._validate_then_save(
            validate_fn=lambda data: {"valid": False, "issues": [{"location": "$", "issue": "bad"}]},
            save_fn=lambda data: calls.append(data) or "SUCCESS: should not happen",
        )
        result = persist({"some": "data"})
        assert result.startswith("ERROR: JSON failed validation")
        assert "bad" in result
        assert calls == []


class TestGenerateDocumentFor:
    """Confirms the variant kwarg is only forwarded for the domain it
    actually belongs to -- mocks create_standard_doc_from_file itself so
    this test is about dispatch's own argument wiring, not docgen."""

    def test_design_variant_is_forwarded_as_design_variant_kwarg(self, monkeypatch):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return "SUCCESS: fake"

        monkeypatch.setattr(dispatch, "create_standard_doc_from_file", fake_create)
        dispatch.generate_document_for("design", "Checkout", "hld")
        assert captured == {"process_name": "Checkout", "schema_type": "design", "design_variant": "hld"}

    def test_togaf_variant_is_forwarded_as_togaf_variant_kwarg(self, monkeypatch):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return "SUCCESS: fake"

        monkeypatch.setattr(dispatch, "create_standard_doc_from_file", fake_create)
        dispatch.generate_document_for("togaf", "Checkout", "vision")
        assert captured == {"process_name": "Checkout", "schema_type": "togaf", "togaf_variant": "vision"}

    def test_variant_is_dropped_entirely_for_domains_with_no_variant_kwarg(self, monkeypatch):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return "SUCCESS: fake"

        monkeypatch.setattr(dispatch, "create_standard_doc_from_file", fake_create)
        dispatch.generate_document_for("process", "Checkout", "some-ignored-value")
        assert captured == {"process_name": "Checkout", "schema_type": "process"}

    def test_a_falsy_variant_is_never_forwarded_even_for_a_domain_that_supports_one(self, monkeypatch):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return "SUCCESS: fake"

        monkeypatch.setattr(dispatch, "create_standard_doc_from_file", fake_create)
        dispatch.generate_document_for("design", "Checkout", None)
        assert captured == {"process_name": "Checkout", "schema_type": "design"}
