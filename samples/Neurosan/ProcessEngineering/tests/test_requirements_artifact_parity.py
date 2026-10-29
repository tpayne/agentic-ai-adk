"""Coverage for giving the requirements domain the same artifact-level
parity process/design already have: a web-client-visible artifact (see
test_cli.py::TestArtifactRoute's requirements cases) and literal-restore
recognition of a re-uploaded requirements_summary.json, folded into
Requirements_Summary_Agent's own HOCON instructions rather than a
separate import network (it already calls save_requirements_summary
directly, with no review loop to bypass -- see the network's own
STEP 1B). Mirrors the sibling ADK port's own
test_requirements_artifact_parity.py.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_SUMMARY_HOCON = PROJECT_ROOT / "registries" / "requirements_summary.hocon"
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_instructions_contain_the_literal_restore_step():
    text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
    assert "STEP 1B: LITERAL RESTORE CHECK" in text
    assert "requirements_summary.json" in text
    assert "requirements_register" in text
    assert "VERBATIM" in text


def test_old_format_keys_are_recognized_too():
    text = REQUIREMENTS_SUMMARY_HOCON.read_text(encoding="utf-8")
    for key in (
        "functional_requirements",
        "non_functional_requirements",
        "goals_or_objectives",
        "constraints",
    ):
        assert key in text


def test_section_1c_points_requirements_imports_away_from_the_other_import_agents():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "A REQUIREMENTS SUMMARY is not one of this rule's three artifact types" in text
    assert "Route it to Requirements_Summary_Agent (Section 7) instead" in text


def test_section_7_mentions_the_literal_restore_case():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "This ALSO covers re-uploading a" in text
    assert "requirements_summary.json" in text
