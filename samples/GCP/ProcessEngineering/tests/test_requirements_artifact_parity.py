"""Coverage for giving the requirements domain the same artifact-level
parity process/design already have: a web-client-visible artifact (see
test_web_service.py's requirements cases) and literal-restore recognition
of a re-uploaded requirements_summary.json, folded into
Requirements_Summary_Agent's own instructions rather than a separate
import agent (it already calls save_requirements_summary directly, with
no review loop to bypass -- see the instruction file's own STEP 1B).
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _instruction_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "instructions", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestRequirementsSummaryAgentLiteralRestore:
    def test_instructions_contain_the_literal_restore_step(self):
        text = _instruction_text("common/requirements_summary_agent.txt")
        assert "STEP 1B: LITERAL RESTORE CHECK" in text
        assert "requirements_summary.json" in text
        assert "requirements_register" in text
        assert "VERBATIM" in text

    def test_old_format_keys_are_recognized_too(self):
        text = _instruction_text("common/requirements_summary_agent.txt")
        for key in (
            "functional_requirements",
            "non_functional_requirements",
            "goals_or_objectives",
            "constraints",
        ):
            assert key in text


class TestRouterCrossReferences:
    def _router_text(self) -> str:
        return _instruction_text("common/agent.txt")

    def test_section_1c_points_requirements_imports_away_from_the_other_import_agents(self):
        text = self._router_text()
        assert "A REQUIREMENTS SUMMARY or a PROPOSAL RESPONSE is not one of this rule's three" in text
        assert "Route a requirements summary to\nRequirements_Summary_Agent (Section 8) instead" in text

    def test_section_8_mentions_the_literal_restore_case(self):
        text = self._router_text()
        assert "This ALSO covers re-uploading a" in text
        assert "requirements_summary.json" in text
