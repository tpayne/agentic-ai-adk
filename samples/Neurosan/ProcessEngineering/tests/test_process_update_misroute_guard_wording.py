"""Regression coverage for a second-order bug found during a live review:
Process_Update_Pipeline's misroute guard (added to stop it from fabricating
a brand-new business process when the orchestrator mistakenly transfers to
it for a design-document request) correctly refused on a live run with zero
fabrication, but the orchestrator then silently retried the SAME request
against Design_Doc_Update_Pipeline in the same turn, with no new human
input -- the identical self-driven-cascade shape this router's own "NEVER
CONTINUE ACTING AFTER YOUR SINGLE TOOL CALL RETURNS" rule already forbids
elsewhere, just with a benign outcome this time. Both the guard's own
refusal text and the orchestrator-level rule were tightened to explicitly
forbid this same-turn auto-retry.
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _hocon_text(relative_path: str) -> str:
    path = os.path.join(ROOT, "registries", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_process_update_guard_refusal_does_not_invite_the_human_to_wait_passively():
    text = _hocon_text("process_update.hocon")
    assert "This needs to be asked again as a new message" in text


def test_process_update_guard_instructs_the_caller_not_to_auto_retry():
    text = _hocon_text("process_update.hocon")
    assert "TO WHOEVER CALLS THIS PIPELINE AND RECEIVES THE REFUSAL ABOVE" in text
    assert "do NOT then call Design_Doc_Update_Pipeline" in text


def test_orchestrator_rule_covers_the_milder_refusal_retry_case():
    text = _hocon_text("process_architect.hocon")
    assert "milder-looking case that is the SAME violation" in text
    assert "self-driven retry that happens to land correctly" in text


def test_design_update_pipeline_calls_the_mechanical_formatter_instead_of_guessing():
    # Regression test for a real production bug, TWICE confirmed live: a
    # prose-only instruction not to guess at open feedback topics did not
    # reliably stop a free-paraphrase (first "extreme-load latency" when
    # the real issue was SPOF risk; then wrong SPOF names entirely on the
    # very next live run after the prose was tightened further). The fix
    # is mechanical: a dedicated tool call now supplies the exact text to
    # relay, removing the model's opportunity to misremember at all.
    text = _hocon_text("design_update.hocon")
    assert "Call format_review_status_summary with channels=" in text
    assert "this tool call replaces that unreliable step entirely" in text
    assert '"format_review_status_summary"' in text


def test_process_update_pipeline_calls_the_mechanical_formatter_instead_of_guessing():
    text = _hocon_text("process_update.hocon")
    assert "Call format_review_status_summary with channels=" in text
    assert '"format_review_status_summary"' in text


def test_design_creation_pipeline_also_uses_the_mechanical_formatter():
    # Applied proactively to the creation pipelines too, not just the
    # update pipelines where the bug was actually observed -- same risk,
    # same fix, same tool.
    text = _hocon_text("design.hocon")
    assert "Call format_review_status_summary with channels=" in text
    assert '"format_review_status_summary"' in text


def test_process_creation_pipeline_also_uses_the_mechanical_formatter():
    text = _hocon_text("process.hocon")
    assert "Call format_review_status_summary with channels=" in text
    assert '"format_review_status_summary"' in text
