"""Tests that the Process_Architect_Orchestrator instructions in agent.txt
explicitly detect and handle chained multi-intent sequential requests
(e.g. 'Create the requirements, then the backlog, then the project plan')
rather than dropping subsequent intents or pausing mid-sequence.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTER_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "common" / "agent.txt"


def test_section_10b_chained_multi_intent_defined():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "### 10b. EXPLICIT SEQUENTIAL WORKFLOW CHAINS (CHAINED MULTI-INTENT)" in text
    assert "Create the requirements, then the backlog, then the project plan" in text


def test_section_10b_maps_all_three_pipeline_stages():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "Requirements Stage: Requirements_Doc_Pipeline" in text
    assert "Backlog Stage: Portfolio_Backlog_Pipeline" in text
    assert "Project Plan Stage: Project_Plan_Export_Agent" in text


def test_section_10b_forbids_pausing_for_already_commanded_steps():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "DO NOT stop to ask the user" in text
    assert "Shall I proceed with creating the backlog next?" in text
    assert "the user ALREADY commanded this in their prompt!" in text


def test_critical_creation_vs_export_distinction_references_chained_multi_intent():
    text = ROUTER_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "If the prompt ALSO explicitly requests a multi-stage sequence" in text
    assert "Apply Section 10b (Chained Multi-Intent):" in text
