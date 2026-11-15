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

    def test_every_domain_now_persists_via_its_own_native_process_toolkit_function(self):
        # requirements/proposal_response/test_specification used to compose
        # a validate-then-save wrapper at this server's own boundary; that
        # made MCP mode stricter than local mode (process_toolkit's own
        # save_* functions for these three are intentionally
        # zero-validation). All six domains are native now -- see
        # test_server.py::test_requirements_persist_is_zero_validation_
        # matching_process_toolkit for the behavioral regression test.
        native = {name for name, ops in dispatch.DOMAINS.items() if ops.persist_is_native}
        assert native == set(dispatch.DOMAINS)


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
