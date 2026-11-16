"""Unit tests for process_interface.agentic_web in local mode and switchable behavior."""

import pytest
from process_interface import agentic_web


def test_agentic_web_local_manifest():
    manifest = agentic_web.get_agent_manifest("http://127.0.0.1:8765")
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["standard"] == "Open Agentic Web MVP Profile"
    assert manifest["capabilities_count"] >= 32
    assert manifest["workflows_count"] >= 6
    assert manifest["artifact_contracts_count"] >= 13


def test_agentic_web_local_cards_and_search():
    cards = agentic_web.get_all_agent_cards()
    assert len(cards) >= 32

    design_card = agentic_web.get_agent_card("design")
    assert design_card is not None
    assert design_card["name"] == "design"

    summaries = agentic_web.list_agent_summaries(category="design")
    assert len(summaries) > 0
    assert all(s["category"] == "design" for s in summaries)

    search_res = agentic_web.search_capabilities(query="simulation")
    assert len(search_res) > 0


def test_agentic_web_local_workflows():
    wfs = agentic_web.get_all_workflows()
    assert len(wfs) >= 6

    wf = agentic_web.get_workflow("architecture_lifecycle")
    assert wf is not None
    assert wf["workflow"] == "architecture_lifecycle"
    assert "design" in wf["steps"]


def test_agentic_web_local_contracts():
    contracts = agentic_web.list_all_artifact_contracts()
    assert len(contracts) >= 13

    contract = agentic_web.get_artifact_contract("high_level_design")
    assert contract is not None
    assert contract["artifact_type"] == "high_level_design"

    envelope = agentic_web.wrap_artifact_envelope("high_level_design", {"title": "HLD"})
    assert envelope["artifact_type"] == "high_level_design"
    assert envelope["producer"] == "design"
    assert "artifact_id" in envelope


def test_agentic_web_mcp_mode_delegation(monkeypatch):
    calls = []

    def fake_call(tool_name, arguments=None):
        calls.append((tool_name, arguments))
        if tool_name == "get_agent_manifest":
            return {"standard": "Open Agentic Web MVP Profile"}
        if tool_name == "list_agents":
            return [{"name": "fake_agent", "category": "test", "description": "desc", "agent_type": "gen", "artifacts": ["art"], "version": "1.0"}]
        if tool_name == "get_agent_card":
            return {"name": arguments.get("name")}
        if tool_name == "list_workflows":
            return [{"workflow": "fake_wf"}]
        if tool_name == "get_workflow":
            return {"workflow": arguments.get("workflow_name")}
        if tool_name == "list_artifact_contracts":
            return [{"artifact_type": "fake_art"}]
        if tool_name == "get_artifact_contract":
            return {"artifact_type": arguments.get("artifact_type")}
        return {}

    monkeypatch.setattr(agentic_web.config, "is_mcp_mode", lambda: True)
    monkeypatch.setattr(agentic_web._transport, "call", fake_call)

    # Test MCP delegation
    manifest = agentic_web.get_agent_manifest("http://fake")
    assert manifest["standard"] == "Open Agentic Web MVP Profile"
    assert calls[-1][0] == "get_agent_manifest"

    cards = agentic_web.get_all_agent_cards()
    assert cards[0]["name"] == "fake_agent"
    assert calls[-1][0] == "list_agents"

    card = agentic_web.get_agent_card("my_agent")
    assert card["name"] == "my_agent"
    assert calls[-1][0] == "get_agent_card"

    wfs = agentic_web.get_all_workflows()
    assert wfs[0]["workflow"] == "fake_wf"
    assert calls[-1][0] == "list_workflows"

    wf = agentic_web.get_workflow("my_wf")
    assert wf["workflow"] == "my_wf"
    assert calls[-1][0] == "get_workflow"

    contracts = agentic_web.list_all_artifact_contracts()
    assert contracts[0]["artifact_type"] == "fake_art"
    assert calls[-1][0] == "list_artifact_contracts"

    contract = agentic_web.get_artifact_contract("my_art")
    assert contract["artifact_type"] == "my_art"
    assert calls[-1][0] == "get_artifact_contract"
