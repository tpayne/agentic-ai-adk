"""Mirrors the Neuro-San sibling port's fix for a confirmed real production
bug (identical router logic, developed in tandem with this one): a request
to import a design document --

    "Import the design documented in /tmp/design_hld_only_src as a
    High-Level Design only -- there is no low-level design content in this
    source, and none should be invented."

-- was misrouted to Process_Import_Agent, even though the request's own
words ("design", "High-Level Design", "low-level design") are unambiguous
DESIGN DOCUMENT signals repeated multiple times, confirmed directly via the
live session's own agent-transcript logs showing the process-import agent
handled it, not the design-import one. The saved design baseline this
request was supposed to persist never existed afterward, so every
following design-domain command failed.

This is the THIRD instance of the same failure mode already documented
twice in instructions/common/agent.txt's own Section 1c ("review this
architecture ... keep it for future use" misrouted to Process_Import_Agent)
-- but unlike those two, this wasn't a signal-word gap at all; the request
text was unambiguous. The likely cause is template anchoring: Section 1c's
own example list's FIRST entry ("Import the process documented in
./legacy-sops as a process document.") was the ONLY example sharing this
request's exact "Import the <X> documented in <path> as a <Y>" sentence
shape, so a same-shaped DESIGN request risked being pattern-matched to that
example's tool choice rather than reasoned about from its own actual domain
word. The fix adds a same-shaped DESIGN example immediately after it.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "common" / "agent.txt"


def test_import_examples_include_a_design_shaped_example_matching_the_process_one():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert '"Import the process documented in ./legacy-sops as a process document." → Process_Import_Agent.' in text
    idx = text.index('"Import the process documented in ./legacy-sops')
    following_text = text[idx:idx + 700]
    assert '"Import the design documented in ./old-hld as a High-Level Design only' in following_text
    assert "→ Design_Import_Agent, NOT\n  Process_Import_Agent." in following_text


def test_the_new_example_is_flagged_as_a_confirmed_production_bug_like_its_siblings():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "CONFIRMED AS A REAL PRODUCTION BUG, a THIRD instance" in text
    assert "template anchoring" in text
