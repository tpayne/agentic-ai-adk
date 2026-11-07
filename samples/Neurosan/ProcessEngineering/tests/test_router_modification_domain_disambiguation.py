"""Regression coverage for a fourth, distinct real production bug in
registries/process_architect.hocon's own Section 2 (MODIFICATION
REQUESTS): a request to modify an existing DESIGN document --

    "Add a rate-limiting component in front of the Checkout Service's API
    Gateway to protect the Payment Gateway from traffic spikes, and
    regenerate the documents."

-- is (an elaborated form of) design_update.hocon's OWN canonical
sample_query, yet was routed to Process_Update_Pipeline on THREE SEPARATE
live runs, confirmed directly via the live session's own
output/logs/agent_thinking/ transcript each time (a __process_update file
existed; no __design_update file did at all). Only a DESIGN document
existed in that session (no process at all), so Process_Update_Pipeline
then applied its OWN "no existing process -> treat as a creation request"
STATE PRECEDENCE rule and fabricated an entirely new, unrelated BUSINESS
PROCESS from scratch each time (three different fabricated
process_data.json files across the three runs), instead of updating the
existing design.

Two earlier fix attempts both failed on live re-test:
1. A trailing "check session state" advisory note after both 2a and 2b
   (lost to 2a's own simple, direct trigger match).
2. A "mandatory gate" embedded in the trigger condition itself, but STILL
   carrying a state-based exception ("unless a process already exists and
   a design doesn't") -- this also failed, because the router has no tool
   that lets it actually verify session state; it was being asked to
   check something it has no reliable way to check.

The fix that held: remove the state-based exception ENTIRELY and make the
gate UNCONDITIONAL -- any modification request naming no explicit
process/design domain word is ALWAYS Rule 10 (ask), full stop, regardless
of what the router believes session state shows.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_2a_gate_is_unconditional_with_no_state_based_exception():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    idx_2a = text.index("### 2a. PROCESS MODIFICATION")
    idx_2b = text.index("### 2b. DESIGN DOCUMENT MODIFICATION")
    section_2a = text[idx_2a:idx_2b]
    assert "DO NOT TRIGGER THIS RULE (MANDATORY GATE, CHECK BEFORE ANYTHING ELSE IN THIS SECTION, NO\nEXCEPTIONS)" in section_2a
    idx_gate = section_2a.index("DO NOT TRIGGER THIS RULE")
    idx_normal_case = section_2a.index("Normal case:")
    assert idx_gate < idx_normal_case
    assert "this is UNCONDITIONALLY Rule 10" in section_2a
    assert "UNLESS a process" not in section_2a


def test_2b_gate_is_unconditional_with_no_state_based_exception():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    idx_2b = text.index("### 2b. DESIGN DOCUMENT MODIFICATION")
    idx_why = text.index("### 2a/2b: WHY THE GATE ABOVE HAS NO STATE-BASED EXCEPTION")
    section_2b = text[idx_2b:idx_why]
    assert "DO NOT TRIGGER THIS RULE (MANDATORY GATE, NO EXCEPTIONS" in section_2b
    idx_gate = section_2b.index("DO NOT TRIGGER THIS RULE")
    idx_normal_case = section_2b.index("Normal case:")
    assert idx_gate < idx_normal_case
    assert "this is\nUNCONDITIONALLY Rule 10 instead" in section_2b
    assert "UNLESS a design document" not in section_2b


def test_bug_explanation_documents_all_three_failed_rounds():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    idx = text.index("### 2a/2b: WHY THE GATE ABOVE HAS NO STATE-BASED EXCEPTION")
    section_text = text[idx:idx + 2200]
    assert "CONFIRMED AS A REAL PRODUCTION BUG, requiring THREE rounds of fixes" in section_text
    assert "on THREE SEPARATE live runs" in section_text
    assert "remove\nthe state-based escape valve entirely and make the gate UNCONDITIONAL" in section_text


def test_rule_10_itself_explicitly_covers_the_domain_neutral_modification_case():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    idx_rule_10 = text.index("## 10. AMBIGUOUS OR UNCLEAR INTENT")
    section_text = text[idx_rule_10:idx_rule_10 + 2500]
    assert "A MODIFICATION request" in section_text
    assert "lands here UNCONDITIONALLY" in section_text
    assert "2a/2b's\nown mandatory gates above" in section_text
