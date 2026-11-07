"""Regression coverage for a third, separate instance of the same failure
mode already documented twice in registries/process_architect.hocon's own
Section 1c ("review this architecture ... keep it for future use" misrouted
to Process_Import_Agent): a request to import a design document --

    "Import the design documented in /tmp/design_hld_only_src as a
    High-Level Design only -- there is no low-level design content in this
    source, and none should be invented."

-- was ALSO misrouted to Process_Import_Agent (confirmed directly via the
live session's own output/logs/agent_thinking/ transcript, which showed
Process_Architect_Orchestrator.__process_import handling it, not
.__design_import), even though the request's own words ("design",
"High-Level Design", "low-level design") are unambiguous DESIGN DOCUMENT
signals repeated multiple times. The design_data.json baseline this
request was supposed to persist never existed afterward, so every
following design-domain command failed with "Design document JSON not
found".

Unlike the two bugs already documented in Section 1c, this one wasn't a
signal-word gap at all -- the request text was unambiguous. The likely
cause is template anchoring: Section 1c's own example list's FIRST entry
("Import the process documented in ./legacy-sops as a process document.")
is the ONLY example sharing this request's exact "Import the <X> documented
in <path> as a <Y>" sentence shape, so a same-shaped DESIGN request risked
being pattern-matched to that example's tool choice rather than reasoned
about from its own actual domain word. The fix adds a same-shaped DESIGN
example immediately after it, giving the router an equally-weighted anchor
for each domain.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_HOCON = PROJECT_ROOT / "registries" / "process_architect.hocon"


def test_import_examples_include_a_design_shaped_example_matching_the_process_one():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    needle = '"Import the process documented in ./legacy-sops as a process document." -> Process_Import_Agent.'
    assert needle in text
    idx = text.index(needle)
    # The next ~600 characters (the very next example) must be the
    # same-shaped DESIGN case, not skip straight to the unrelated
    # "Load the design in ..." example that already existed.
    following_text = text[idx:idx + 700]
    assert '"Import the design documented in ./old-hld as a High-Level Design only' in following_text
    assert "-> Design_Import_Agent, NOT\n  Process_Import_Agent." in following_text


def test_the_new_example_is_flagged_as_a_confirmed_production_bug_like_its_siblings():
    text = ROUTER_HOCON.read_text(encoding="utf-8")
    assert "CONFIRMED AS A REAL PRODUCTION BUG, a THIRD instance" in text
    assert "template anchoring" in text
