"""Unit tests for ProcessEngineering's own Agent Discovery API module."""

import pytest
from process_toolkit.agentic_web import (
    AgentCard,
    AgentProvenance,
    AGENT_CARDS,
    get_all_agent_cards,
    get_agent_card,
    list_agent_summaries,
    ArtifactContract,
    ARTIFACT_CONTRACTS,
    get_artifact_contract,
    list_all_artifact_contracts,
    wrap_artifact_envelope,
    WorkflowDefinition,
    WORKFLOW_DEFINITIONS,
    get_all_workflows,
    get_workflow,
    get_agent_manifest,
    search_capabilities,
)


class TestAgentCards:
    def test_all_expected_specialist_agents_registered(self):
        cards = get_all_agent_cards()
        assert len(cards) >= 41
        names = {c["name"] for c in cards}
        expected = [
            "process_architect",
            "requirements_summary",
            "requirements_consultant",
            "requirements_reviewer",
            "requirements_simulation_query",
            "requirements_doc_pipeline",
            "process",
            "process_update",
            "process_consultant",
            "process_simulation_query",
            "process_scenario_tester",
            "design",
            "design_update",
            "design_consultant",
            "design_simulation_query",
            "design_scenario_tester",
            "cloudarch",
            "cloudarch_consultant",
            "cloudarch_simulation_query",
            "cloudarch_attack_simulation_query",
            "cloudarch_finops",
            "cloudarch_iac",
            "test_specification",
            "test_consultant",
            "test_reviewer",
            "portfolio_backlog",
            "portfolio_backlog_consultant",
            "portfolio_backlog_reviewer",
            "project_plan_export",
            "project_plan_reviewer",
            "proposal_response_pipeline",
            "proposal_response_consultant",
            "proposal_response_reviewer",
            "togaf",
            "togaf_scenario_tester",
            "togaf_consultant",
            "itsm",
            "itsm_update",
            "itsm_import",
            "itsm_consultant",
            "itsm_reviewer",
            "itsm_scenario_tester",
            "itsm_simulation_query",
            "regenerate_document",
        ]
        for name in expected:
            assert name in names, f"Expected agent '{name}' to be registered in AGENT_CARDS"

    def test_agent_card_structure(self):
        design_card = get_agent_card("design")
        assert design_card is not None
        assert design_card["name"] == "design"
        assert design_card["category"] == "design"
        assert design_card["agent_type"] == "generator"
        assert "inputs" in design_card
        assert "outputs" in design_card
        assert "artifacts" in design_card
        assert "high_level_design" in design_card["artifacts"]
        assert design_card["version"] == "1.0.0"
        assert "Agentic-AI-ADK" in design_card["provenance"]["owner"]

    def test_get_agent_card_case_and_alias_tolerance(self):
        # Case insensitive
        assert get_agent_card("DESIGN") is not None
        assert get_agent_card("Design")["name"] == "design"

        # Alias tolerance
        assert get_agent_card("Design_Agent")["name"] == "design"
        assert get_agent_card("Design_Pipeline")["name"] == "design"
        assert get_agent_card("CloudArch_Agent")["name"] == "cloudarch"
        assert get_agent_card("nonexistent_agent_xyz") is None

        # ITSM aliases: the real ADK/neuro-san agent idents (ITSM_Agent, ITSM_Pipeline,
        # Full_ITSM_Pipeline isn't alias-stripped since it doesn't end in _agent/_pipeline
        # after stripping "Full_", but the bare ones resolve) and the scenario tester.
        assert get_agent_card("ITSM_Agent")["name"] == "itsm"
        assert get_agent_card("ITSM_Pipeline")["name"] == "itsm"
        assert get_agent_card("ITSM_Scenario_Tester")["name"] == "itsm_scenario_tester"

    def test_search_capabilities_filters(self):
        # Filter by category
        design_agents = search_capabilities(category="design")
        assert len(design_agents) > 0
        assert all(a["category"] == "design" for a in design_agents)

        # Filter by artifact
        drawio_agents = search_capabilities(artifact="drawio_xml")
        assert any(a["name"] == "cloudarch" for a in drawio_agents)

        # Filter by agent_type
        sim_agents = search_capabilities(agent_type="simulator")
        assert any(a["name"] == "cloudarch_simulation_query" for a in sim_agents)

        # Search query text
        finops_agents = search_capabilities(query="finops")
        assert any("finops" in a["name"] for a in finops_agents)

    def test_search_capabilities_filters_itsm(self):
        itsm_agents = search_capabilities(category="itsm")
        assert len(itsm_agents) == 7
        assert all(a["category"] == "itsm" for a in itsm_agents)

        itsm_artifact_agents = search_capabilities(artifact="itsm_artifacts")
        assert any(a["name"] == "itsm" for a in itsm_artifact_agents)

        itsm_reviewer_agents = search_capabilities(agent_type="reviewer", category="itsm")
        assert any(a["name"] == "itsm_reviewer" for a in itsm_reviewer_agents)

    def test_list_agent_summaries(self):
        summaries = list_agent_summaries()
        assert len(summaries) >= 41
        for s in summaries:
            assert "name" in s
            assert "description" in s
            assert "category" in s
            assert "agent_type" in s
            assert "artifacts" in s
            assert "version" in s


class TestArtifactContracts:
    def test_all_artifact_contracts_present(self):
        contracts = list_all_artifact_contracts()
        types = {c["artifact_type"] for c in contracts}
        expected = [
            "requirements_summary",
            "process_definition",
            "high_level_design",
            "low_level_design",
            "cloud_architecture",
            "drawio_xml",
            "simulation_report",
            "finops_report",
            "iac_package",
            "test_specification",
            "portfolio_backlog",
            "project_plan",
            "pert_cpm",
            "togaf_artifacts",
            "itsm_artifacts",
            "proposal_response",
        ]
        for t in expected:
            assert t in types, f"Expected artifact contract '{t}'"

    def test_get_artifact_contract(self):
        hld = get_artifact_contract("high_level_design")
        assert hld is not None
        assert hld["artifact_type"] == "high_level_design"
        assert hld["file_format"] == "json"
        assert "document_metadata" in hld["schema_fields"]

        # Extension tolerance
        assert get_artifact_contract("high_level_design.json") is not None
        assert get_artifact_contract("DRAWIO_XML") is not None

    def test_wrap_artifact_envelope(self):
        raw_data = {"process_name": "Order Fulfillment"}
        wrapped = wrap_artifact_envelope("process_definition", raw_data, version="1.0")

        assert wrapped["artifact_type"] == "process_definition"
        assert wrapped["producer"] == "process"
        assert wrapped["version"] == "1.0"
        assert wrapped["contract_version"] == "1.0"
        assert "artifact_id" in wrapped
        assert wrapped["artifact_id"].startswith("PRO-")
        assert "created" in wrapped
        assert wrapped["data"] == raw_data


class TestWorkflows:
    def test_all_lifecycle_workflows_present(self):
        wfs = get_all_workflows()
        ids = {w["workflow"] for w in wfs}
        expected = [
            "architecture_lifecycle",
            "process_engineering_lifecycle",
            "enterprise_architecture_togaf_lifecycle",
            "test_assurance_lifecycle",
            "portfolio_planning_lifecycle",
            "bid_proposal_lifecycle",
            "itsm_management_lifecycle",
        ]
        for w in expected:
            assert w in ids

    def test_get_workflow(self):
        arch_flow = get_workflow("architecture_lifecycle")
        assert arch_flow is not None
        assert arch_flow["workflow"] == "architecture_lifecycle"
        assert "design" in arch_flow["steps"]
        assert "cloudarch" in arch_flow["steps"]
        assert "cloudarch_iac" in arch_flow["steps"]
        assert len(arch_flow["produced_artifacts"]) >= 4

        # Case insensitive
        assert get_workflow("ARCHITECTURE_LIFECYCLE") is not None
        assert get_workflow("nonexistent_workflow") is None


class TestAgentManifest:
    def test_get_agent_manifest(self):
        manifest = get_agent_manifest("http://localhost:5000")
        assert manifest["schema_version"] == "1.0.0"
        assert "standard" not in manifest
        assert manifest["provider"]["name"] == "Agentic-AI-ADK"
        assert manifest["endpoints"]["agents"] == "http://localhost:5000/agents"
        assert manifest["endpoints"]["chat"] == "http://localhost:5000/chat"
        assert manifest["capabilities_count"] >= 41
        assert manifest["workflows_count"] >= 7
        assert manifest["artifact_contracts_count"] >= 14
        assert len(manifest["agents"]) >= 41
