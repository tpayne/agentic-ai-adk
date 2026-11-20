"""Regression tests for the dual-mode (GENERAL vs SPECIFIC) consultant pattern.

CONFIRMED AS A REAL GAP on the sibling neuro-san port (identical agent logic, developed in tandem
with this one): every consultant agent used to refuse ANY question -- including a purely general
one with no reference to the user's own saved document -- simply because no document was saved,
even though answering it needs no document at all. Each consultant agent must classify
general-vs-specific BEFORE deciding whether a saved document/diagram/summary is required.
ITSM_Consultant_Agent's own version of this pattern is covered separately, inline in
tests/test_itsm_pipeline_wiring.py (it was the template this pattern was built from).
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _read(relative_path):
    with open(os.path.join(ROOT, relative_path), encoding="utf-8") as file:
        return file.read()


def test_process_consultant_answers_general_questions_without_requiring_a_saved_process():
    text = _read("instructions/process/consultant_agent.txt")
    assert "GENERAL: asks about process design/BPM concepts" in text
    assert "SPECIFIC: references the user's OWN process" in text
    assert "Do NOT call the 'load_full_process_context'\ntool for a purely general question" in text


def test_design_consultant_answers_general_questions_without_requiring_a_saved_document():
    text = _read("instructions/design/consultant_design_agent.txt")
    assert "GENERAL: asks about architecture/solution-design concepts" in text
    assert "SPECIFIC: references the user's OWN design" in text
    assert "Do NOT call the\n'load_full_design_context' tool for a purely general question" in text


def test_cloudarch_consultant_answers_general_questions_without_requiring_a_saved_diagram():
    text = _read("instructions/cloudarch/cloudarch_consultant_agent.txt")
    assert "GENERAL: asks about cloud architecture concepts" in text
    assert "SPECIFIC: references the user's OWN diagram" in text
    assert "Do NOT call the 'load_drawio' tool for a\npurely general question" in text


def test_requirements_consultant_answers_general_questions_without_requiring_a_saved_summary():
    text = _read("instructions/common/requirements_consultant_agent.txt")
    assert "GENERAL: asks about requirements-analysis concepts" in text
    assert "SPECIFIC: references the user's OWN saved summary" in text
    assert "Do NOT call the 'load_requirements_summary'\ntool for a purely general question" in text


def test_proposal_response_consultant_answers_general_questions_without_requiring_a_saved_response():
    text = _read("instructions/common/proposal_response_consultant_agent.txt")
    assert "GENERAL: asks about proposal-writing/bid concepts" in text
    assert "SPECIFIC: references the user's OWN saved response" in text
    assert "Do NOT call the 'load_proposal_response'\ntool for a purely general question" in text


def test_test_consultant_answers_general_questions_without_requiring_a_saved_specification():
    text = _read("instructions/common/test_consultant_agent.txt")
    assert "GENERAL: asks about test-design/QA concepts" in text
    assert "SPECIFIC: references the user's OWN saved specification" in text
    assert "Do NOT call the 'load_test_specification'\ntool for a purely general question" in text
