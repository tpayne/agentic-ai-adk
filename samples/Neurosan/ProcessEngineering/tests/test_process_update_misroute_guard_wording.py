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


def test_design_update_step9_requires_grounding_the_open_feedback_topic():
    # Regression test for a real production bug: the pipeline's own final
    # report characterized open simulation feedback as "extreme-load
    # latency" when the actual persisted feedback was entirely about
    # resilience/SPOF risk, and latency_budget_risk was explicitly false.
    text = _hocon_text("design_update.hocon")
    assert "MUST be the actual topic/component named in Compliance_Agent's or" in text
    assert "extreme-load latency" in text


def test_process_update_step10_requires_grounding_the_open_feedback_topic():
    text = _hocon_text("process_update.hocon")
    assert "it MUST be the actual topic/component named in" in text
    assert "Compliance_Agent's or Simulation_Agent's own most recent feedback" in text
