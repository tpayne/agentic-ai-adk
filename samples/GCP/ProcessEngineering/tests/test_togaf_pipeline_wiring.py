import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _read(relative_path):
    with open(os.path.join(ROOT, relative_path), encoding="utf-8") as file:
        return file.read()


def test_togaf_agent_registers_source_and_persistence_tools():
    from process_agents.common.togaf_agent import togaf_agent
    from process_agents.common.utils import (
        load_full_design_context,
        load_iteration_feedback,
        load_master_togaf_json,
        load_requirements_summary,
        persist_final_togaf_json,
    )

    assert {
        load_master_togaf_json,
        load_requirements_summary,
        load_full_design_context,
        load_iteration_feedback,
        persist_final_togaf_json,
    } <= set(togaf_agent.tools)


def test_togaf_pipeline_has_compliance_loop_and_doc_creation_stage():
    from process_agents.common.togaf_agent import togaf_agent
    from process_agents.common.togaf_compliance_agent import togaf_compliance_agent
    from process_agents.common.togaf_pipeline_agent import (
        togaf_pipeline,
        togaf_review_loop,
        stop_controller_agent_instance,
    )

    assert togaf_review_loop in togaf_pipeline.sub_agents
    assert togaf_agent in togaf_review_loop.sub_agents
    assert togaf_compliance_agent in togaf_review_loop.sub_agents
    assert stop_controller_agent_instance in togaf_review_loop.sub_agents

    # A real render stage follows the review loop -- structurally distinct
    # from CloudArch_Pipeline, which has nothing after its own loop.
    stage_names = [agent.name for agent in togaf_pipeline.sub_agents]
    assert any("Doc_Creation" in name for name in stage_names)


def test_stop_controller_clone_uses_togaf_specific_approval_key():
    from process_agents.common.togaf_pipeline_agent import stop_controller_agent_instance
    from process_agents.common.utils_agent import togaf_stop_if_ready, status_logger

    assert set(stop_controller_agent_instance.tools) == {status_logger, togaf_stop_if_ready}


def test_togaf_compliance_agent_registers_load_and_save_tools_only():
    from process_agents.common.togaf_compliance_agent import togaf_compliance_agent
    from process_agents.common.utils import load_master_togaf_json, save_iteration_feedback

    assert set(togaf_compliance_agent.tools) == {load_master_togaf_json, save_iteration_feedback}


def test_togaf_compliance_instructions_have_the_four_item_checklist_and_approved_marker():
    text = _read("instructions/common/togaf_compliance_agent.txt")

    assert "TRACEABILITY CHAIN INTEGRITY" in text
    assert "GROUNDED GAPS" in text
    assert "ANTI-FABRICATION ON MIGRATION PLANNING" in text
    assert "DOCUMENT METADATA NAMING HYGIENE" in text
    assert "TOGAF_COMPLIANCE_APPROVED" in text


def test_approval_marker_is_registered_in_the_shared_feedback_module():
    # Regression for the exact gap this pipeline would otherwise hit: the
    # literal "status" value togaf_compliance_agent.txt instructs the LLM
    # to save must be a registered marker, or loop_control's own
    # togaf_stop_if_ready would never detect approval.
    from process_toolkit.feedback.iteration_feedback import APPROVAL_MARKERS, APPROVED_STATUSES

    assert "TOGAF_COMPLIANCE_APPROVED" in APPROVAL_MARKERS
    assert APPROVAL_MARKERS["TOGAF_COMPLIANCE_APPROVED"] == ("togaf_compliance_status", "APPROVED")
    assert "TOGAF_COMPLIANCE_APPROVED" in APPROVED_STATUSES


def test_togaf_agent_instructions_carry_naming_hygiene_and_anti_fabrication_rules():
    text = _read("instructions/common/togaf_agent.txt")

    assert 'NEVER embed "Architecture Vision Document"' in text
    assert "NEVER add a date, budget figure, team-capacity number" in text


def test_scenario_tester_has_no_save_or_persist_tool_at_all():
    from process_agents.common.togaf_scenario_tester_agent import togaf_scenario_tester_agent
    from process_agents.common.utils import load_full_togaf_context, load_requirements_summary

    assert set(togaf_scenario_tester_agent.tools) == {load_full_togaf_context, load_requirements_summary}

    # Structural guarantee against mutation, same convention as
    # design_scenario_tester_agent: no save/persist tool exists on this
    # agent's own tool list at all.
    tool_names = {getattr(tool, "__name__", "") for tool in togaf_scenario_tester_agent.tools}
    assert not any(name.startswith("save_") or name.startswith("persist_") for name in tool_names)


def test_root_router_routes_togaf_requests():
    text = _read("instructions/common/agent.txt")

    assert "### 1h. TOGAF ARCHITECTURE ARTIFACT GENERATION OR UPDATE" in text
    assert "→ Call: TOGAF_Pipeline" in text
    assert "### 5c. TOGAF WHAT-IF SCENARIOS" in text
    assert "→ Call: TOGAF_Scenario_Tester" in text
    assert "TOGAF architecture artifact creation or update → TOGAF_Pipeline" in text
    assert "TOGAF artifacts → TOGAF_Scenario_Tester" in text


def test_togaf_scope_documents_phase_h_exclusion_in_the_router():
    text = _read("instructions/common/agent.txt")

    assert "Phase H" in text and "deliberately out of" in text


def test_registry_and_root_wiring():
    registry = _read("process_agents/common/agent_registry.py")
    root = _read("process_agents/common/agent.py")

    assert "from .togaf_pipeline_agent import togaf_pipeline" in registry
    assert "from .togaf_scenario_tester_agent import togaf_scenario_tester_agent" in registry
    assert root.count("togaf_pipeline,") == 2
    assert root.count("togaf_scenario_tester_agent,") == 2


def test_web_artifact_routes_expose_togaf_json():
    text = _read("process_agents/common/agent.py")

    assert text.count('"togaf": "togaf_data.json"') == 2


def test_doc_creation_pinning_exposes_togaf_variant():
    text = _read("process_agents/common/doc_creation_agent.py")

    assert 'if schema_type == "togaf"' in text
    assert "togaf_variant" in text


def test_doc_generation_instructions_mention_togaf_variant():
    text = _read("instructions/common/doc_generation_agent.txt")

    assert "togaf_variant" in text
    assert 'schema_type="togaf"' in text
