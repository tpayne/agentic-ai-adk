import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def _read(relative_path):
    with open(os.path.join(ROOT, relative_path), encoding="utf-8") as file:
        return file.read()


def test_itsm_analysis_agent_registers_source_and_feedback_tools():
    from process_agents.itsm.analysis_agent import itsm_analysis_agent
    from process_agents.common.utils import (
        save_iteration_feedback,
        load_directory_context,
        load_requirements_summary,
    )

    assert {
        save_iteration_feedback,
        load_directory_context,
        load_requirements_summary,
    } <= set(itsm_analysis_agent.tools)


def test_itsm_agent_registers_load_validate_persist_tools():
    from process_agents.itsm.itsm_agent import itsm_agent
    from process_agents.common.utils import (
        load_master_itsm_json,
        load_iteration_feedback,
        validate_itsm_json,
        persist_final_itsm_json,
    )

    assert set(itsm_agent.tools) == {
        load_master_itsm_json,
        load_iteration_feedback,
        validate_itsm_json,
        persist_final_itsm_json,
    }


def test_itsm_compliance_agent_registers_load_and_save_tools_only():
    from process_agents.itsm.compliance_agent import itsm_compliance_agent
    from process_agents.common.utils import load_master_itsm_json, save_iteration_feedback

    assert set(itsm_compliance_agent.tools) == {load_master_itsm_json, save_iteration_feedback}


def test_itsm_simulation_agent_wraps_the_shared_structural_analysis_function():
    from process_agents.itsm.simulation_agent import itsm_simulation_agent, simulate_itsm_risk
    from process_agents.common.utils import save_iteration_feedback, simulate_itsm_risk_and_coverage

    assert set(itsm_simulation_agent.tools) == {simulate_itsm_risk, save_iteration_feedback}
    # simulate_itsm_risk takes no meaningful arguments -- it loads the
    # baseline itself, same reasoning as design_simulation_agent.py's own
    # _resolve_input_data docstring (avoiding a caller-supplied JSON blob
    # that risks silent truncation).
    assert simulate_itsm_risk() == simulate_itsm_risk_and_coverage(None)


def test_itsm_simulation_query_agent_is_read_only():
    from process_agents.itsm.simulation_agent import itsm_simulation_query_agent, simulate_itsm_risk
    from process_agents.common.utils import load_full_itsm_context, load_requirements_summary

    assert set(itsm_simulation_query_agent.tools) == {
        load_full_itsm_context,
        load_requirements_summary,
        simulate_itsm_risk,
    }
    tool_names = {getattr(tool, "__name__", "") for tool in itsm_simulation_query_agent.tools}
    assert not any(name.startswith("save_") or name.startswith("persist_") for name in tool_names)


def test_itsm_consultant_agent_is_read_only():
    from process_agents.itsm.consultant_agent import itsm_consultant_agent
    from process_agents.common.utils import load_full_itsm_context, load_requirements_summary

    assert set(itsm_consultant_agent.tools) == {load_full_itsm_context, load_requirements_summary}


def test_itsm_scenario_tester_has_no_save_or_persist_tool_at_all():
    from process_agents.itsm.scenario_agent import itsm_scenario_tester_agent
    from process_agents.common.utils import load_full_itsm_context, load_requirements_summary

    assert set(itsm_scenario_tester_agent.tools) == {load_full_itsm_context, load_requirements_summary}

    # Structural guarantee against mutation, same convention as
    # togaf_scenario_tester_agent/design_scenario_tester_agent: no save/
    # persist tool exists on this agent's own tool list at all.
    tool_names = {getattr(tool, "__name__", "") for tool in itsm_scenario_tester_agent.tools}
    assert not any(name.startswith("save_") or name.startswith("persist_") for name in tool_names)


def test_itsm_reviewer_agent_can_load_validate_and_persist():
    # Unlike the scenario tester/consultant, the reviewer has a genuine
    # (intent-gated) APPLY MODE -- see instructions/itsm/reviewer_agent.txt.
    from process_agents.itsm.reviewer_agent import itsm_reviewer_agent
    from process_agents.common.utils import (
        load_master_itsm_json,
        validate_itsm_json,
        persist_final_itsm_json,
    )

    assert set(itsm_reviewer_agent.tools) == {
        load_master_itsm_json,
        validate_itsm_json,
        persist_final_itsm_json,
    }


def test_itsm_import_agent_registers_directory_and_persistence_tools():
    from process_agents.itsm.import_agent import itsm_import_agent
    from process_agents.common.utils import (
        load_directory_context,
        load_master_itsm_json,
        validate_itsm_json,
        persist_final_itsm_json,
    )

    assert set(itsm_import_agent.tools) == {
        load_directory_context,
        load_master_itsm_json,
        validate_itsm_json,
        persist_final_itsm_json,
    }


def test_full_itsm_pipeline_has_a_three_member_compliance_loop_and_doc_creation_stage():
    from process_agents.itsm.itsm_agent import itsm_agent
    from process_agents.itsm.compliance_agent import itsm_compliance_agent
    from process_agents.itsm.simulation_agent import itsm_simulation_agent
    from process_agents.itsm.analysis_agent import itsm_analysis_agent
    from process_agents.itsm.create_itsm_agent import (
        full_itsm_pipeline,
        itsm_review_loop,
        stop_controller_agent_instance,
    )

    assert itsm_analysis_agent in full_itsm_pipeline.sub_agents
    assert itsm_review_loop in full_itsm_pipeline.sub_agents
    assert itsm_agent in itsm_review_loop.sub_agents
    assert itsm_compliance_agent in itsm_review_loop.sub_agents
    assert itsm_simulation_agent in itsm_review_loop.sub_agents
    assert stop_controller_agent_instance in itsm_review_loop.sub_agents

    stage_names = [agent.name for agent in full_itsm_pipeline.sub_agents]
    assert any("Doc_Creation" in name for name in stage_names)


def test_full_itsm_pipeline_stop_controller_uses_itsm_specific_approval_key():
    from process_agents.itsm.create_itsm_agent import stop_controller_agent_instance
    from process_agents.common.utils_agent import itsm_stop_if_ready, status_logger

    assert set(stop_controller_agent_instance.tools) == {status_logger, itsm_stop_if_ready}


def test_update_itsm_pipeline_clones_the_loop_agents_not_the_originals():
    # Each ADK BaseAgent instance can only have ONE parent -- the update
    # pipeline must use its own clones, not the same objects
    # Full_ITSM_Pipeline's own loop already claims.
    from process_agents.itsm.itsm_agent import itsm_agent
    from process_agents.itsm.compliance_agent import itsm_compliance_agent
    from process_agents.itsm.simulation_agent import itsm_simulation_agent
    from process_agents.itsm.update_itsm_agent import (
        update_itsm_pipeline,
        itsm_update_review_loop,
        itsm_update_analyst,
        itsm_inst,
        itsm_compliance_inst,
        itsm_simulation_inst,
    )

    assert itsm_update_analyst in update_itsm_pipeline.sub_agents
    assert itsm_update_review_loop in update_itsm_pipeline.sub_agents
    assert itsm_inst in itsm_update_review_loop.sub_agents
    assert itsm_compliance_inst in itsm_update_review_loop.sub_agents
    assert itsm_simulation_inst in itsm_update_review_loop.sub_agents

    assert itsm_inst is not itsm_agent
    assert itsm_compliance_inst is not itsm_compliance_agent
    assert itsm_simulation_inst is not itsm_simulation_agent
    # But the clone carries the SAME instruction text -- itsm_agent.txt's
    # own feedback-shape branching (extracted_requirements vs. a bare
    # delta instruction) is what lets ONE shared instruction file serve
    # both the create and update pipelines correctly.
    assert itsm_inst.instruction == itsm_agent.instruction


def test_itsm_update_analyst_refuses_to_fabricate_against_an_empty_baseline():
    # CONFIRMED AS A REAL BUG on the sibling neuro-san port: a bare update request against nothing
    # saved ("Add an emergency change type to the ITSM process document.") fabricated an entire
    # fictitious organization and persisted it as a brand-new document instead of refusing -- the
    # update-side equivalent of ITSM_Analysis_Agent's own NO REAL SOURCE MATERIAL guard. Both the
    # first line of defense (ITSM_Update_Analyst) and the defense-in-depth check (ITSM_Agent's own
    # UPDATE DELTA branch) must refuse rather than fabricate.
    analyst_text = _read("instructions/itsm/update_analysis_agent.txt")
    assert "do not create one as a substitute -- stop here" in analyst_text

    agent_text = _read("instructions/itsm/itsm_agent.txt")
    assert "do NOT invent an" in agent_text
    assert "organization/service catalog from nothing" in agent_text
    assert "CONFIRMED AS A REAL BUG" in agent_text


def test_itsm_agent_instructions_handle_both_fresh_generation_and_update_deltas():
    # Regression guard: itsm_agent.txt is shared (via true clone) by both
    # Full_ITSM_Pipeline and Update_ITSM_Pipeline. Early draft wrongly
    # treated "feedback has no extracted_requirements key" as a hard-stop
    # error, which would have made it refuse every genuine update-delta
    # instruction from ITSM_Update_Analyst (which never carries that key).
    text = _read("instructions/itsm/itsm_agent.txt")

    assert "FRESH GENERATION" in text
    assert "UPDATE DELTA" in text
    assert "ITSM_Update_Analyst" in text


def test_approval_markers_are_registered_in_the_shared_feedback_module():
    # Regression for the exact gap this pipeline would otherwise hit: the
    # literal "status" values itsm_compliance_agent.txt/itsm_simulation_
    # agent.txt instruct the LLM to save must be registered markers, or
    # itsm_stop_if_ready would never detect approval.
    from process_toolkit.feedback.iteration_feedback import APPROVAL_MARKERS, APPROVED_STATUSES

    assert "ITSM_COMPLIANCE_APPROVED" in APPROVAL_MARKERS
    assert APPROVAL_MARKERS["ITSM_COMPLIANCE_APPROVED"] == ("itsm_compliance_status", "APPROVED")
    assert "ITSM_COMPLIANCE_APPROVED" in APPROVED_STATUSES

    assert "ITSM_SIMULATION_ALL_APPROVED" in APPROVAL_MARKERS
    assert APPROVAL_MARKERS["ITSM_SIMULATION_ALL_APPROVED"] == ("itsm_simulation_status", "APPROVED")


def test_itsm_compliance_instructions_have_the_six_item_checklist_and_approved_marker():
    text = _read("instructions/itsm/compliance_agent.txt")

    assert "NAMING HYGIENE" in text
    assert "ANTI-FABRICATION" in text
    assert "RACI COVERAGE" in text
    assert "STRUCTURAL COMPLETENESS" in text
    assert "STEP HANDOFF CONSISTENCY" in text
    assert "KNOWN ERROR TRACEABILITY" in text
    assert "ITSM_COMPLIANCE_APPROVED" in text


def test_itsm_agent_assigns_stable_ids_and_checks_role_traceability():
    # Follow-up schema-quality fixes: request_types/risks_and_controls entries now need a
    # real id (same convention SLA/CI/known_errors already use), and every role name written
    # into raci_matrix/process_steps must trace back to a role actually defined in
    # stakeholders_and_roles/cab_members -- the "CAB" vs "Change Advisory Board (CAB)" drift a
    # plain human reviewer would catch on sight.
    text = _read("instructions/itsm/itsm_agent.txt")
    assert "STABLE IDS" in text
    assert "ROLE NAME TRACEABILITY" in text
    assert "validate_itsm_json` checks this leniently, by substring, not" in text


def test_itsm_agent_instructions_carry_the_naming_hygiene_and_anti_fabrication_rules():
    text = _read("instructions/itsm/itsm_agent.txt")

    assert 'NEVER "ITSM"/"ITSM Process Document"' in text
    assert "NEVER populate a date, budget, cost, or team-headcount figure anywhere" in text


def test_root_router_routes_itsm_requests():
    text = _read("instructions/common/agent.txt")

    assert "### 1i. ITSM PROCESS DOCUMENT GENERATION OR UPDATE" in text
    assert "→ Call: Full_ITSM_Pipeline" in text
    assert "### 3g. ITSM PROCESS DOCUMENT STRUCTURAL RISK/COVERAGE ANALYSIS" in text
    assert "→ Call: ITSM_Simulation_Query_Agent" in text
    assert "### 4j. ITSM PROCESS DOCUMENT EXPLANATION / REVIEW" in text
    assert "### 4k. ITSM PROCESS DOCUMENT QUALITY REVIEW" in text
    assert "### 5d. ITSM PROCESS DOCUMENT WHAT-IF SCENARIOS" in text
    assert "→ Call: ITSM_Scenario_Tester" in text
    assert "ITSM process document creation → Full_ITSM_Pipeline" in text
    assert "ITSM process document → ITSM_Scenario_Tester" in text


def test_router_scenario_section_prefers_itsm_signal_words_over_the_generic_process():
    # CONFIRMED AS A REAL PRODUCTION BUG on the sibling neuro-san port (identical router logic,
    # developed in tandem with this one): "What happens if the Service Desk role is unavailable?"
    # -- asked with both an ITSM process document and a plain business process saved, immediately
    # after a turn about that plain process -- answered using the plain process's own data instead
    # of routing to ITSM_Scenario_Tester and tracing the real Service Desk role/RACI/escalation
    # data in the saved ITSM document. Section 5a's own generic "what happens if..." trigger has
    # no built-in exclusion for an ITSM (or design/TOGAF) signal word, and recency of the prior
    # turn apparently won over the signal word in actual live routing.
    text = _read("instructions/common/agent.txt")
    section_5a_start = text.index("### 5a. PROCESS WHAT-IF SCENARIOS")
    section_5b_start = text.index("### 5b. DESIGN DOCUMENT WHAT-IF SCENARIOS")
    section_5a_text = text[section_5a_start:section_5b_start]

    assert "DOMAIN PRECEDENCE WITHIN SECTION 5" in section_5a_text
    assert "CONFIRMED AS A REAL" in section_5a_text
    assert "recency of the prior turn\nis not a tiebreaker" in section_5a_text or "recency of the prior turn is not a tiebreaker" in section_5a_text

    # SECOND, STILL-CONFIRMED bug after the first fix above landed: the router stopped
    # answering from the wrong domain but started asking a clarification question instead of
    # just calling ITSM_Scenario_Tester -- a partial fix, not the fix. The carve-out must
    # explicitly forbid asking, not just state a precedence preference.
    assert "DO NOT ask a clarification question in this situation" in section_5a_text
    assert "STILL-CONFIRMED production bug" in section_5a_text
    assert "it is not a tiebreaker among equally plausible options, it is the decision" in section_5a_text


def test_router_sends_bare_itsm_regenerate_requests_to_create_doc_agent():
    # Same production-bug precedent as TOGAF's own regression guard (see
    # test_togaf_pipeline_wiring.py's matching test): a bare "regenerate
    # the ITSM process document" matches 1i's own signal word ("ITSM") and
    # must NOT be routed to Full_ITSM_Pipeline, which would re-run the
    # full generate/review cycle instead of just re-rendering the already-
    # saved JSON.
    text = _read("instructions/common/agent.txt")

    section_6_start = text.index("## 6. DOCUMENT REGENERATION")
    section_6_text = text[section_6_start:text.index("## 7.", section_6_start)]
    assert '"Regenerate the ITSM process document."' in section_6_text
    assert "AND SECTION 1i FOR ITSM" in section_6_text

    section_1i_start = text.index("### 1i. ITSM PROCESS DOCUMENT GENERATION OR UPDATE")
    section_1i_text = text[section_1i_start:section_6_start]
    assert "Section 6 (DOCUMENT REGENERATION) instead" in section_1i_text


def test_itsm_scope_documents_out_of_scope_itil_practices():
    text = _read("instructions/common/agent.txt")

    assert "Capacity/Availability Management" in text
    assert "Continual Service Improvement" in text


def test_registry_and_root_wiring():
    registry = _read("process_agents/common/agent_registry.py")
    root = _read("process_agents/common/agent.py")

    assert "from ..itsm.create_itsm_agent import full_itsm_pipeline" in registry
    assert "from ..itsm.update_itsm_agent import update_itsm_pipeline" in registry
    for name in (
        "full_itsm_pipeline",
        "update_itsm_pipeline",
        "itsm_import_agent",
        "itsm_consultant_agent",
        "itsm_reviewer_agent",
        "itsm_scenario_tester_agent",
        "itsm_simulation_query_agent",
    ):
        assert root.count(f"{name},") == 2


def test_web_artifact_routes_expose_itsm_json():
    text = _read("process_agents/common/agent.py")

    assert text.count('"itsm": "itsm_data.json"') == 2


def test_doc_creation_pinning_has_no_variant_for_itsm():
    # ITSM is a single-document schema type (no Vision/Definition-style
    # split the way design/togaf have) -- confirmed by NOT appearing in
    # doc_creation_agent.py's own schema_type == "design"/"togaf" variant
    # branches at all; it falls through to the generic, variant-free
    # closure.
    text = _read("process_agents/common/doc_creation_agent.py")

    assert 'if schema_type == "design"' in text
    assert 'if schema_type == "togaf"' in text
    assert "itsm" not in text.lower()


def test_root_agent_registers_all_seven_itsm_agents():
    from process_agents.common.agent import root_agent

    names = {agent.name for agent in root_agent.sub_agents}
    assert {
        "Full_ITSM_Pipeline",
        "Update_ITSM_Pipeline",
        "ITSM_Import_Agent",
        "ITSM_Consultant_Agent",
        "ITSM_Reviewer_Agent",
        "ITSM_Scenario_Tester",
        "ITSM_Simulation_Query_Agent",
    } <= names
