from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRIES = PROJECT_ROOT / "registries"


def test_manifest_registers_togaf_networks():
    text = (REGISTRIES / "manifest.hocon").read_text(encoding="utf-8")
    assert '"togaf.hocon": true' in text
    assert '"togaf_scenario_tester.hocon": true' in text


def test_router_routes_and_enables_togaf_network():
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    orchestrator_start = text.index('"name": "Process_Architect_Orchestrator"')
    tools_start = text.index('"tools": [', orchestrator_start)
    tools_text = text[tools_start:text.index("]", tools_start)]

    assert '"/togaf"' in tools_text
    assert '"/togaf_scenario_tester"' in tools_text
    assert "### 1h. TOGAF ARCHITECTURE ARTIFACT GENERATION OR UPDATE" in text
    assert "TOGAF architecture artifact creation or update -> TOGAF_Pipeline" in text
    assert "### 5c. TOGAF WHAT-IF SCENARIOS" in text
    assert "-> Call: TOGAF_Scenario_Tester" in text


def test_togaf_network_loads_one_source_and_runs_a_compliance_loop():
    text = (REGISTRIES / "togaf.hocon").read_text(encoding="utf-8")

    assert '"name": "TOGAF_Pipeline"' in text
    assert '"name": "TOGAF_Agent"' in text
    assert '"name": "TOGAF_Compliance_Agent"' in text
    assert "design document exists, use it as the SOLE source" in text
    assert "TOGAF GENERATION STOPPED" in text
    assert "load_requirements_summary" in text
    assert "design_json_tool" in text
    assert "persist_final_togaf_json" in text
    assert "togaf_compliance_status" in text
    assert "format_review_status_summary" in text
    assert "release_pipeline_lock_for_turn" in text


def test_router_sends_bare_togaf_regenerate_requests_to_regenerate_document_agent():
    # Regression for a real live-run bug: "Please regenerate just the TOGAF architecture vision
    # document" matched 1h's own TOGAF signal words ("TOGAF", "architecture vision document") and
    # got routed to TOGAF_Pipeline, which rebuilt the entire artifact set from source and ran a
    # full compliance loop instead of just re-rendering the already-saved JSON -- several times
    # more expensive than intended, and liable to produce a worse result than the already-approved
    # saved content.
    text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")

    section_9_start = text.index("## 9. STANDALONE DOCUMENT REGENERATION")
    section_9_text = text[section_9_start:text.index("## 10.", section_9_start)]
    assert "TOGAF ARCHITECTURE VISION/" in section_9_text
    assert '"Regenerate the TOGAF architecture documents."' in section_9_text
    assert '"Please regenerate just the TOGAF architecture vision document."' in section_9_text
    assert "CONFIRMED AS A REAL PRODUCTION BUG" in section_9_text

    section_1h_start = text.index("### 1h. TOGAF ARCHITECTURE ARTIFACT GENERATION OR UPDATE")
    section_1h_text = text[section_1h_start:section_9_start]
    assert "is Section 9 (STANDALONE DOCUMENT REGENERATION) instead" in section_1h_text


def test_togaf_pipeline_answers_pure_scope_questions_without_attempting_generation():
    # Regression for a real live-run bug: a pure "does this cover Phase H?" question still ran the
    # full REQUIRED SEQUENCE and tacked on an unprompted "TOGAF GENERATION STOPPED: no saved
    # source" result for a generation attempt nobody asked for in that turn.
    text = (REGISTRIES / "togaf.hocon").read_text(encoding="utf-8")
    assert "# PURE SCOPE/COVERAGE QUESTIONS (no generation needed)" in text
    assert "do not proceed to the REQUIRED SEQUENCE below and do not call any tool" in text
    assert "CONFIRMED AS A REAL BUG" in text


def test_togaf_scope_documents_phase_h_exclusion():
    # The scope decision (which ADM phases are covered vs. deliberately
    # excluded) must be stated plainly where a user would actually see
    # it, not just in a code comment -- both in the router's own routing
    # section and in the pipeline's own final-report instruction.
    router_text = (REGISTRIES / "process_architect.hocon").read_text(encoding="utf-8")
    assert "Phase H" in router_text and "deliberately out of" in router_text

    pipeline_text = (REGISTRIES / "togaf.hocon").read_text(encoding="utf-8")
    assert "Phase H and full" in pipeline_text


def test_togaf_agent_carries_the_naming_hygiene_and_anti_fabrication_rules():
    text = (REGISTRIES / "togaf.hocon").read_text(encoding="utf-8")
    assert "NEVER embed \"Architecture Vision Document\"" in text
    assert "NEVER add a date, budget figure, team-capacity number" in text


def test_togaf_compliance_agent_has_the_four_item_checklist():
    text = (REGISTRIES / "togaf.hocon").read_text(encoding="utf-8")
    assert "TRACEABILITY CHAIN INTEGRITY" in text
    assert "GROUNDED GAPS" in text
    assert "ANTI-FABRICATION ON MIGRATION PLANNING" in text
    assert "DOCUMENT METADATA NAMING HYGIENE" in text
    assert "TOGAF_COMPLIANCE_APPROVED" in text


def test_togaf_scenario_tester_network_has_no_save_tool_at_all():
    # Structural guarantee against mutation -- same convention as
    # design_scenario_tester.hocon: no save/write tool exists on this
    # network, so it cannot persist a change even if asked to.
    text = (REGISTRIES / "togaf_scenario_tester.hocon").read_text(encoding="utf-8")
    assert '"name": "TOGAF_Scenario_Tester"' in text
    assert "save_" not in text
    assert "persist_" not in text


def test_coded_tool_delegates_to_shared_togaf_persistence():
    text = (
        PROJECT_ROOT / "coded_tools" / "togaf" / "togaf_json_tool.py"
    ).read_text(encoding="utf-8")
    assert "process_toolkit.schema.togaf_json" in text
    assert "persist_final_togaf_json" in text


def test_doc_generation_tool_releases_the_pipeline_lock_unconditionally():
    text = (
        PROJECT_ROOT / "coded_tools" / "togaf" / "doc_generation_tool.py"
    ).read_text(encoding="utf-8")
    assert "schema_type=\"togaf\"" in text
    assert "finally:" in text
    assert "release_pipeline_lock(token)" in text


def test_load_coded_tool_returns_the_empty_template_when_nothing_is_saved():
    from coded_tools.togaf.togaf_json_tool import LoadFullTogafContextCodedTool

    result = LoadFullTogafContextCodedTool().invoke({}, {})

    assert "document_metadata" in result
    assert "architecture_vision" in result


def test_scenario_tester_re_exports_the_canonical_togaf_loader():
    from coded_tools.togaf.togaf_json_tool import LoadFullTogafContextCodedTool as Canonical
    from coded_tools.togaf_scenario_tester.togaf_json_tool import LoadFullTogafContextCodedTool as ReExported

    assert ReExported is Canonical


def test_regenerate_document_network_knows_about_togaf():
    text = (REGISTRIES / "regenerate_document.hocon").read_text(encoding="utf-8")
    assert '"togaf"' in text
    assert "togaf_variant" in text
    # Never auto-detected, same as requirements/proposal_response/test_specification --
    # confirmed by NOT being in regenerate_flow_diagram's own schema_type enum.
    flow_diagram_start = text.index('"name": "regenerate_flow_diagram"')
    flow_diagram_enum_line = text[flow_diagram_start:text.index("\n", text.index("enum", flow_diagram_start))]
    assert "togaf" not in flow_diagram_enum_line


def test_web_artifact_routes_expose_togaf_json():
    text = (PROJECT_ROOT / "cli.py").read_text(encoding="utf-8")
    assert '"togaf": "togaf_data.json"' in text


def test_togaf_format_review_status_defaults_to_togaf_compliance_channel():
    from coded_tools.togaf.format_review_status_tool import FormatReviewStatusCodedTool
    from process_toolkit.feedback.iteration_feedback import save_iteration_feedback

    save_iteration_feedback({"status": "TOGAF_COMPLIANCE_APPROVED", "data": []}, channel="togaf_compliance")
    result = FormatReviewStatusCodedTool().invoke({}, {})

    assert "TOGAF Compliance: APPROVED." in result or "Togaf_compliance: APPROVED." in result
