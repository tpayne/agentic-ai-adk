"""Regression coverage for a real production bug found during a live review
of a design_hld_lld_split CLI run: a design-document update request
("Add a rate-limiting component to the design document... and regenerate
the documents.") contains the explicit word "design" -- per the router's
own domain-disambiguation rule this should route unambiguously to
Update_Design_Doc_Pipeline -- yet the router invoked the process-update
pipeline instead. With no existing process in the session, that pipeline
fabricated an entirely new "Online Checkout and Payment Process" from
scratch, and the router's own relayed reply then described it as a design
document update, naming Combined HLD/LLD files that were never touched.

Mirrors the sibling Neuro-San port's own fix: (1) the router's domain
disambiguation rule now checks for an explicit design/process word FIRST,
before any generic infrastructure noun is allowed to compete with it; (2)
the process-update analyst has its own defense-in-depth guard so that even
if the router misroutes again, it refuses to fabricate process content
instead of silently building something nobody asked for.
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _instruction_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "instructions", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _router_text() -> str:
    return _instruction_text("common/agent.txt")


def _update_analysis_text() -> str:
    return _instruction_text("process/update_analysis_agent.txt")


def _compliance_text() -> str:
    return _instruction_text("design/design_doc_compliance_agent.txt")


class TestRouterDesignWordPrecedence:
    def test_router_checks_for_an_explicit_design_word_before_either_modification_gate(self):
        text = _router_text()
        assert "CHECK THIS FIRST, BEFORE EITHER GATE BELOW" in text
        assert '"design document", "the design", "this design"' in text

    def test_router_documents_the_recurrence_with_the_design_word_present(self):
        text = _router_text()
        assert "with the disambiguating word PRESENT this time" in text
        assert "Online Checkout and Payment Process" in text


class TestProcessUpdateAnalystMisrouteGuard:
    def test_analyst_has_a_misroute_guard_before_its_normal_sequence(self):
        text = _update_analysis_text()
        assert "STEP 0 -- MISROUTE GUARD" in text
        assert '"misroute_guard": true' in text

    def test_guard_fires_on_the_literal_design_word(self):
        text = _update_analysis_text()
        assert 'the literal words "design"' in text


class TestRouterDoesNotAutoRetryAfterAMisrouteRefusal:
    def test_router_rule_covers_the_milder_refusal_retry_case(self):
        text = _router_text()
        assert "milder-looking case that is the SAME violation" in text
        assert "self-driven retry that happens to land correctly" in text


class TestComplianceAgentMetadataNamingCheck:
    def test_compliance_checklist_flags_combined_hld_lld_in_system_name(self):
        text = _compliance_text()
        assert "Metadata_Naming" in text
        assert "Document Metadata Naming Hygiene" in text
        assert "Combined_HLD+LLD_for_Checkout_Service_Architecture_HLD.docx" in text
