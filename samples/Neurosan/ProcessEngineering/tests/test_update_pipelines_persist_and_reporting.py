"""Consistency fixes mirrored onto process_update.hocon/design_update.hocon
after confirming the same "claim success either way" and "steps might get
silently skipped on MAX_ITERATIONS" bug classes on process.hocon/design.hocon
(see test_process_persist_and_reporting.py / test_design_persist_and_reporting.py).
Both update pipelines' Design_Agent/Design_Doc_Agent always operate on an
existing real baseline (never a fresh generation), so the skeleton-first
checkpoint fix doesn't apply here -- only the orchestrator-level reporting-
honesty and mandatory-step-execution fixes.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESS_UPDATE_HOCON = PROJECT_ROOT / "registries" / "process_update.hocon"
DESIGN_UPDATE_HOCON = PROJECT_ROOT / "registries" / "design_update.hocon"


def test_process_update_pipeline_mandates_the_refresh_steps_and_honest_reporting():
    text = PROCESS_UPDATE_HOCON.read_text(encoding="utf-8")
    assert "MANDATORY, NO EXCEPTIONS" in text
    assert "NEVER claim a" in text
    assert "NEVER describe the" in text
    assert 'starting with' in text and '"SUCCESS:" or "ERROR:"' in text


def test_design_update_pipeline_mandates_the_refresh_steps_and_honest_reporting():
    text = DESIGN_UPDATE_HOCON.read_text(encoding="utf-8")
    assert "MANDATORY, NO EXCEPTIONS" in text
    assert 'NEVER claim a document was produced "either way"' in text
    assert "NEVER describe the design's own content" in text
    assert 'starting with either "SUCCESS:" or "ERROR:"' in text
