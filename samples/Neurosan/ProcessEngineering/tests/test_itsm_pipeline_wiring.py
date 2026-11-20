"""Wiring coverage for the ITSM pipeline family: registries/itsm.hocon (create),
registries/itsm_update.hocon (explicit update), and the five standalone networks
(itsm_import/itsm_consultant/itsm_reviewer/itsm_scenario_tester/itsm_simulation_query).
Mirrors test_togaf_pipeline_wiring.py's own structural-assertion style, extended for
ITSM's fuller agent roster (analysis/compliance/simulation, not just a single derive-
from-design agent) -- see test_proposal_response_consultant_reviewer_wiring.py and
test_requirements_reviewer_simulation_wiring.py for the analogous reviewer/consultant
coverage this file reuses the same shape for.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRIES = PROJECT_ROOT / "registries"


def test_manifest_registers_all_seven_itsm_networks():
    text = (REGISTRIES / "manifest.hocon").read_text(encoding="utf-8")
    for name in (
        "itsm.hocon",
        "itsm_update.hocon",
        "itsm_import.hocon",
        "itsm_consultant.hocon",
        "itsm_reviewer.hocon",
        "itsm_scenario_tester.hocon",
        "itsm_simulation_query.hocon",
    ):
        assert f'"{name}": true' in text


def test_router_routes_and_enables_every_itsm_network():
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_start = text.index('"tools": [', orchestrator_start)
    tools_text = text[tools_start:text.index("]", tools_start)]

    for route in (
        "/itsm",
        "/itsm_update",
        "/itsm_import",
        "/itsm_consultant",
        "/itsm_reviewer",
        "/itsm_scenario_tester",
        "/itsm_simulation_query",
    ):
        assert f'"{route}"' in tools_text

    assert "### 1i. ITSM PROCESS DOCUMENT GENERATION OR UPDATE" in text
    assert "ITSM process document creation -> ITSM_Pipeline" in text
    assert "### 3g. ITSM PROCESS DOCUMENT STRUCTURAL RISK/COVERAGE ANALYSIS" in text
    assert "### 4j. ITSM PROCESS DOCUMENT EXPLANATION / REVIEW" in text
    assert "### 4k. ITSM PROCESS DOCUMENT QUALITY REVIEW" in text
    assert "### 5d. ITSM PROCESS DOCUMENT WHAT-IF SCENARIOS" in text


def test_router_disambiguates_itsm_from_generic_process_and_togaf():
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    assert 'Signal words for an ITSM PROCESS DOCUMENT: "ITSM", "IT service management", "ITIL"' in text
    # Precedence: ITSM's own signal words win even when "process"/"architecture"
    # would otherwise match the generic domains -- same pattern TOGAF already uses.
    assert "is the ITSM PROCESS DOCUMENT domain, not a generic business PROCESS" in text


def test_router_scenario_section_prefers_itsm_signal_words_over_the_generic_process():
    # CONFIRMED AS A REAL PRODUCTION BUG from a live run: "What happens if the Service Desk role
    # is unavailable?" -- asked with both an ITSM process document and a plain business process
    # saved, immediately after a turn about that plain process -- answered using the plain
    # process's own data instead of routing to ITSM_Scenario_Tester and tracing the real Service
    # Desk role/RACI/escalation data in the saved ITSM document. Section 5a's own generic "what
    # happens if..." trigger has no built-in exclusion for an ITSM (or design/TOGAF) signal word,
    # and recency of the prior turn apparently won over the signal word in actual live routing.
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    section_5a_start = text.index("### 5a. PROCESS WHAT-IF SCENARIOS")
    section_5b_start = text.index("### 5b. DESIGN DOCUMENT WHAT-IF SCENARIOS")
    section_5a_text = text[section_5a_start:section_5b_start]

    assert "DOMAIN PRECEDENCE WITHIN SECTION 5" in section_5a_text
    assert "CONFIRMED AS A REAL\nPRODUCTION BUG" in section_5a_text or "CONFIRMED AS A REAL PRODUCTION BUG" in section_5a_text
    assert "recency of\nthe prior turn is not a tiebreaker" in section_5a_text or "recency of the prior turn is not a tiebreaker" in section_5a_text

    # SECOND, STILL-CONFIRMED bug after the first fix above landed: the router stopped
    # answering from the wrong domain but started asking a clarification question instead of
    # just calling ITSM_Scenario_Tester -- a partial fix, not the fix. The carve-out must
    # explicitly forbid asking, not just state a precedence preference.
    assert 'DO NOT ask a clarification question in this situation' in section_5a_text
    assert "STILL-CONFIRMED production bug" in section_5a_text
    assert "it is not a tiebreaker among equally\nplausible options, it is the decision" in section_5a_text or "it is not a tiebreaker among equally plausible options, it is the decision" in section_5a_text


def test_router_sends_bare_itsm_regenerate_requests_to_regenerate_document_agent():
    # Same production-bug precedent as TOGAF's own regression guard (see
    # test_togaf_pipeline_wiring.py's matching test): a bare "regenerate the ITSM
    # process document" matches 1i's own signal word ("ITSM") and must NOT be routed
    # to ITSM_Pipeline, which would re-run the full generate/review cycle instead of
    # just re-rendering the already-saved JSON.
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")

    section_9_start = text.index("## 9. STANDALONE DOCUMENT REGENERATION")
    section_9_text = text[section_9_start:text.index("## 10.", section_9_start)]
    assert '"Regenerate the ITSM process document."' in section_9_text

    section_1i_start = text.index("### 1i. ITSM PROCESS DOCUMENT GENERATION OR UPDATE")
    section_1i_text = text[section_1i_start:text.index("### 1j." if "### 1j." in text else "## 2.", section_1i_start)]
    assert "same precedence pattern as TOGAF's" in section_1i_text


def test_itsm_pipeline_loads_requirements_and_runs_a_dual_gate_loop():
    text = (REGISTRIES / "itsm.hocon").read_text(encoding="utf-8")

    assert '"name": "ITSM_Pipeline"' in text
    assert '"name": "ITSM_Analysis_Agent"' in text
    assert '"name": "ITSM_Agent"' in text
    assert '"name": "ITSM_Compliance_Agent"' in text
    assert '"name": "ITSM_Simulation_Agent"' in text
    assert "itsm_compliance_status" in text
    assert "format_review_status_summary" in text
    assert "release_pipeline_lock_for_turn" in text
    # Simulation is informational input to the compliance gate, not an
    # independent approval gate -- loop_control's own required= dict only
    # names the compliance channel, same discipline as cloudarch/design.
    loop_control_call = text.index("Call loop_control with required=")
    loop_control_line = text[loop_control_call:text.index("\n", loop_control_call)]
    assert "itsm_simulation_status" not in loop_control_line


def test_itsm_consultant_answers_general_questions_without_requiring_a_saved_document():
    # CONFIRMED AS A REAL GAP: every consultant agent used to refuse ANY question -- including a
    # purely general "what are the core phases of incident management?" with no reference to the
    # user's own document -- simply because no document was saved, even though answering it needs
    # no document at all. The agent must classify general-vs-specific BEFORE deciding whether a
    # saved document is required.
    text = (REGISTRIES / "itsm_consultant.hocon").read_text(encoding="utf-8")
    assert "GENERAL: asks about ITSM/ITIL concepts" in text
    assert "SPECIFIC: references the user's OWN document" in text
    assert "Do NOT\ncall load_full_itsm_context for a purely general question" in text or \
        "Do NOT call load_full_itsm_context for a purely general question" in text


def test_itsm_pipeline_stops_and_renders_on_max_iterations_not_only_on_approval():
    # Same confirmed-bug precedent as every sibling full-consortium pipeline:
    # an open compliance item after the max revision passes is feedback for a
    # FUTURE revision, not a reason to withhold the document that already exists.
    text = (REGISTRIES / "itsm.hocon").read_text(encoding="utf-8")
    assert 'NOT only when "reason" is "APPROVED"' in text
    assert "MAX_ITERATIONS" in text


def test_itsm_agent_never_fabricates_dates_cost_or_headcount():
    text = (REGISTRIES / "itsm.hocon").read_text(encoding="utf-8")
    assert "NEVER populate a date, budget, cost, or team-headcount figure anywhere" in text
    assert "the schema has no such fields by design" in text


def test_itsm_analysis_agent_refuses_to_fabricate_from_nothing():
    text = (REGISTRIES / "itsm.hocon").read_text(encoding="utf-8")
    assert "NO REAL SOURCE MATERIAL" in text
    assert "Do NOT invent a plausible-\nsounding organization/service catalog from nothing." in text


def test_itsm_compliance_agent_has_the_six_item_checklist():
    for hocon_path in (REGISTRIES / "itsm.hocon", REGISTRIES / "itsm_update.hocon"):
        text = hocon_path.read_text(encoding="utf-8")
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
    for hocon_path in (REGISTRIES / "itsm.hocon", REGISTRIES / "itsm_update.hocon"):
        text = hocon_path.read_text(encoding="utf-8")
        assert "STABLE IDS" in text
        assert "ROLE NAME TRACEABILITY" in text
        assert "validate_itsm_json checks this leniently, by substring, not" in text


def test_itsm_simulation_agent_runs_structural_not_timing_analysis():
    text = (REGISTRIES / "itsm.hocon").read_text(encoding="utf-8")
    assert "STRUCTURAL analysis" in text
    assert "NOT a\ntiming/cost simulation, since this schema deliberately has no duration/date fields" in text
    assert "ITSM_SIMULATION_ALL_APPROVED" in text


def test_itsm_update_analyst_refuses_to_fabricate_against_an_empty_baseline():
    # CONFIRMED AS A REAL BUG from a live run: a bare update request against nothing saved
    # ("Add an emergency change type to the ITSM process document.") fabricated an entire
    # fictitious organization and persisted it as a brand-new document instead of refusing --
    # the update-side equivalent of ITSM_Analysis_Agent's own NO REAL SOURCE MATERIAL guard.
    text = (REGISTRIES / "itsm_update.hocon").read_text(encoding="utf-8")
    assert "NO BASELINE TO UPDATE" in text
    assert "CONFIRMED AS A REAL BUG" in text
    # The front-man must actually check for and act on that sentinel, and release the pipeline
    # lock before stopping (same discipline as the create pipeline's own REQUIREMENTS EXTRACTION
    # FAILED check).
    assert 'reply begins with "NO BASELINE TO UPDATE"' in text
    assert "release_pipeline_lock_for_turn" in text
    # Defense in depth: ITSM_Agent's own SAFETY CHECK must also refuse rather than fabricate.
    assert "do NOT invent an organization/service catalog from nothing" in text


def test_itsm_update_pipeline_duplicates_the_shared_loop_agents():
    # External network references only reach a network's front-man, never its
    # internal sub-agents -- itsm_update.hocon must carry its own full copies of
    # ITSM_Agent/ITSM_Compliance_Agent/ITSM_Simulation_Agent, same as
    # process_update.hocon does for Process_Agent/Design_Doc_Compliance_Agent-shaped
    # peers.
    text = (REGISTRIES / "itsm_update.hocon").read_text(encoding="utf-8")
    assert '"name": "ITSM_Update_Pipeline"' in text
    assert '"name": "ITSM_Update_Analyst"' in text
    assert '"name": "ITSM_Agent"' in text
    assert '"name": "ITSM_Compliance_Agent"' in text
    assert '"name": "ITSM_Simulation_Agent"' in text


def test_itsm_scenario_tester_network_has_no_save_tool_at_all():
    # Structural guarantee against mutation -- same convention as
    # togaf_scenario_tester.hocon/design_scenario_tester.hocon.
    text = (REGISTRIES / "itsm_scenario_tester.hocon").read_text(encoding="utf-8")
    assert '"name": "ITSM_Scenario_Tester"' in text
    assert "save_" not in text
    assert "persist_" not in text


def test_itsm_reviewer_network_is_intent_gated_with_the_same_combined_reply_rule():
    text = (REGISTRIES / "itsm_reviewer.hocon").read_text(encoding="utf-8")
    assert "APPLY MODE" in text
    assert "By default" in text
    assert "do NOT produce both;" in text


def test_coded_tool_delegates_to_shared_itsm_persistence():
    text = (
        PROJECT_ROOT / "coded_tools" / "itsm" / "itsm_json_tool.py"
    ).read_text(encoding="utf-8")
    # Delegates through process_interface (the compliance chokepoint), not
    # process_toolkit directly -- see test_togaf_pipeline_wiring.py's matching
    # assertion for the same reasoning.
    assert "process_interface.schema.itsm_json" in text
    assert "persist_final_itsm_json" in text


def test_doc_generation_tool_releases_the_pipeline_lock_unconditionally():
    text = (
        PROJECT_ROOT / "coded_tools" / "itsm" / "doc_generation_tool.py"
    ).read_text(encoding="utf-8")
    assert 'schema_type="itsm"' in text
    assert "finally:" in text
    assert "release_pipeline_lock(token)" in text


def test_load_coded_tool_returns_the_empty_template_when_nothing_is_saved():
    from coded_tools.itsm.itsm_json_tool import LoadFullItsmContextCodedTool

    result = LoadFullItsmContextCodedTool().invoke({}, {})

    assert "document_metadata" in result
    assert "incident_management" in result


def test_standalone_networks_re_export_the_canonical_itsm_loader():
    from coded_tools.itsm.itsm_json_tool import LoadFullItsmContextCodedTool as Canonical
    from coded_tools.itsm_consultant.itsm_json_tool import LoadFullItsmContextCodedTool as ConsultantReExported
    from coded_tools.itsm_scenario_tester.itsm_json_tool import LoadFullItsmContextCodedTool as ScenarioReExported
    from coded_tools.itsm_simulation_query.itsm_json_tool import LoadFullItsmContextCodedTool as SimQueryReExported

    assert ConsultantReExported is Canonical
    assert ScenarioReExported is Canonical
    assert SimQueryReExported is Canonical


def test_itsm_reviewer_reexports_the_canonical_load_and_persist_classes():
    # The reviewer, unlike the read-only consultant/scenario-tester/sim-query
    # networks, also needs to persist a mechanical fix when explicitly asked
    # (APPLY MODE) -- so it re-exports Load/Validate/PersistFinal, not
    # LoadFullItsmContext.
    from coded_tools.itsm.itsm_json_tool import (
        LoadMasterItsmJsonCodedTool as CanonicalLoad,
        PersistFinalItsmJsonCodedTool as CanonicalPersist,
    )
    from coded_tools.itsm_reviewer.itsm_json_tool import (
        LoadMasterItsmJsonCodedTool as ReviewerLoad,
        PersistFinalItsmJsonCodedTool as ReviewerPersist,
    )

    assert ReviewerLoad is CanonicalLoad
    assert ReviewerPersist is CanonicalPersist


def test_simulation_query_shim_reexports_the_canonical_simulation_tool():
    from coded_tools.itsm.simulation_tool import SimulateItsmRiskCodedTool as Canonical
    from coded_tools.itsm_simulation_query.simulation_tool import SimulateItsmRiskCodedTool as ReExported

    assert ReExported is Canonical


def test_regenerate_document_network_knows_about_itsm():
    text = (REGISTRIES / "regenerate_document.hocon").read_text(encoding="utf-8")
    assert '"itsm"' in text
    # Never auto-detected, same as requirements/proposal_response/test_specification/
    # togaf -- confirmed by NOT being in regenerate_flow_diagram's own schema_type enum
    # (ITSM renders its diagrams inline per-section, there is no whole-document flow
    # diagram to regenerate for it at all).
    flow_diagram_start = text.index('"name": "regenerate_flow_diagram"')
    flow_diagram_enum_line = text[flow_diagram_start:text.index("\n", text.index("enum", flow_diagram_start))]
    assert "itsm" not in flow_diagram_enum_line
    assert "ITSM has no\n  variant knob at all" in text


def test_web_artifact_routes_expose_itsm_json():
    text = (PROJECT_ROOT / "cli.py").read_text(encoding="utf-8")
    assert '"itsm": "itsm_data.json"' in text


def test_itsm_format_review_status_defaults_to_itsm_compliance_channel():
    from coded_tools.itsm.format_review_status_tool import FormatReviewStatusCodedTool
    from process_toolkit.feedback.iteration_feedback import save_iteration_feedback

    save_iteration_feedback({"status": "ITSM_COMPLIANCE_APPROVED", "data": []}, channel="itsm_compliance")
    result = FormatReviewStatusCodedTool().invoke({}, {})

    assert "Itsm Compliance: APPROVED." in result or "ITSM Compliance: APPROVED." in result
