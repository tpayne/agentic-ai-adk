"""Coverage for giving the proposal-response domain the same
artifact-level parity process/design/requirements already have: a
web-client-visible artifact (see test_web_service.py's proposal_response
cases) and literal-restore recognition of a re-uploaded
proposal_response.json, folded into Proposal_Response_Agent's own
instructions rather than a separate import agent (it already saves
directly, with no review loop to bypass).
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _instruction_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "instructions", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestProposalResponseAgentLiteralRestore:
    def test_instructions_contain_the_literal_restore_step(self):
        text = _instruction_text("common/proposal_response_agent.txt")
        assert "STEP 1B: LITERAL RESTORE CHECK" in text
        assert "proposal_response.json" in text
        assert "compliance_matrix" in text
        assert "VERBATIM" in text

    def test_instructions_require_the_requirements_summary_first(self):
        text = _instruction_text("common/proposal_response_agent.txt")
        assert "load_requirements_summary" in text
        assert "NOT_FOUND" in text

    def test_instructions_warn_against_fabricating_pricing(self):
        text = _instruction_text("common/proposal_response_agent.txt")
        assert "NEVER invent actual" in text
        assert "pricing_approach" in text


class TestRouterCrossReferences:
    def _router_text(self) -> str:
        return _instruction_text("common/agent.txt")

    def test_section_1c_points_proposal_response_imports_away_from_the_other_import_agents(self):
        text = self._router_text()
        assert "A REQUIREMENTS SUMMARY or a PROPOSAL RESPONSE is not one of this rule's three" in text

    def test_section_1e_exists_with_precedence_over_1d(self):
        text = self._router_text()
        assert "### 1e. PROPOSAL RESPONSE DOCUMENT CREATION" in text
        assert "PRECEDENCE vs. 1d" in text
