"""Regression coverage for the Phase 4 tool additions: drawio, cloudarch
simulation/attack/finops, iac save, the generic master-json reader,
subprocess-flow persistence, and feedback. Same in-memory Client(server.mcp)
convention as test_server.py.
"""

import json

import pytest
from fastmcp import Client

import server


class TestDrawio:
    async def test_load_when_nothing_saved_yet(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool("load_drawio", {"session_id": "s1"})).data
        assert result == {"status": "NOT_FOUND", "xml": None}

    async def test_reset_then_load_confirms_removal(self):
        async with Client(server.mcp) as client:
            await client.call_tool("reset_drawio", {"session_id": "s1"})
            result = (await client.call_tool("load_drawio", {"session_id": "s1"})).data
        assert result == {"status": "NOT_FOUND", "xml": None}


class TestCloudarchSimulations:
    @pytest.mark.parametrize("tool_name", ["simulate_architecture", "simulate_attack", "estimate_finops"])
    async def test_reports_no_diagram_available_rather_than_erroring(self, tool_name):
        async with Client(server.mcp) as client:
            raw = (await client.call_tool(tool_name, {"session_id": "s1"})).data
        parsed = json.loads(raw)
        assert parsed == {"error": "no_diagram_available", "detail": "No cloud architecture diagram has been saved yet."}


class TestSaveIac:
    async def test_save_then_reflected_in_list_artifacts_via_local_mirror_pattern(self):
        # save_iac itself only reports sanitized filenames (no base64 --
        # process_interface mirrors the content it already has locally
        # instead of round-tripping it back), but the files really do
        # land in the session's own iac/ subdirectory server-side.
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "save_iac", {"files": {"main.tf": "resource \"x\" \"y\" {}"}, "session_id": "s1"},
            )).data
        assert result == {"files_written": ["main.tf"]}


class TestLoadMasterJson:
    async def test_returns_empty_dict_when_nothing_saved(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "load_master_json", {"schema_type": "design", "session_id": "s1"},
            )).data
        assert result == {}

    async def test_explicit_schema_type_matches_load_context_once_a_real_baseline_is_persisted(self):
        # load_master_json's own "nothing saved yet" contract (empty dict)
        # deliberately differs from load_context's (falls back to the
        # full template, so a generator always has a valid object to
        # start from) -- they only have to agree once a real file exists
        # on disk, which is what this test actually proves. Persisting
        # the template itself guarantees it passes validation trivially.
        async with Client(server.mcp) as client:
            template = (await client.call_tool("load_template", {"schema_type": "design"})).data
            template["document_metadata"].update({
                "document_id": "ARCH-TEST-001", "document_type": "HLD",
                "system_name": "Checkout", "title": "Checkout",
            })
            template["requirements"]["functional_requirements"] = []
            template["requirements"]["non_functional_requirements"] = []
            persisted = (await client.call_tool(
                "persist_json", {"schema_type": "design", "data": template, "session_id": "s1"},
            )).data
            assert persisted["success"], persisted["message"]

            via_master = (await client.call_tool(
                "load_master_json", {"schema_type": "design", "session_id": "s1"},
            )).data
            via_context = (await client.call_tool(
                "load_context", {"schema_type": "design", "session_id": "s1"},
            )).data
        assert via_master == via_context


class TestSaveSubprocessFlow:
    def _valid_flow(self):
        description = "x" * 150
        return {
            "subprocess_flow": [{
                "substep_name": "Step 1", "description": description,
                "purpose": "p", "scope": "s", "process_owner": "o", "responsible_party": "r",
            }],
        }

    async def test_valid_flow_persists_successfully(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "save_subprocess_flow",
                {"step_name": "Review Order", "flow": self._valid_flow(), "session_id": "s1"},
            )).data
        assert result["status"] == "OK"
        assert result["path"].endswith(".json")

    async def test_invalid_flow_reports_error_without_raising(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "save_subprocess_flow",
                {"step_name": "Review Order", "flow": {}, "session_id": "s1"},
            )).data
        assert result["status"] == "ERROR"


class TestFeedback:
    async def test_load_when_nothing_saved_yet_returns_empty_dict(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "load_feedback", {"session_id": "s1"},
            )).data
        assert result == {}

    async def test_save_then_load_round_trip_and_drain(self):
        async with Client(server.mcp) as client:
            saved = (await client.call_tool(
                "save_feedback",
                {"feedback_data": {"status": "COMPLIANCE APPROVED", "data": []}, "session_id": "s1"},
            )).data
            assert saved["success"], saved["message"]

            first_load = (await client.call_tool("load_feedback", {"session_id": "s1"})).data
            assert first_load["status"] == "COMPLIANCE APPROVED"

            # reset_data defaults True -- a second read must see the
            # drained sentinel, not the same content again.
            second_load = (await client.call_tool("load_feedback", {"session_id": "s1"})).data
            assert second_load["status"] == "NONE"

    async def test_channels_are_independent_mailboxes(self):
        async with Client(server.mcp) as client:
            await client.call_tool(
                "save_feedback",
                {"feedback_data": {"status": "COMPLIANCE APPROVED", "data": []}, "channel": "compliance", "session_id": "s1"},
            )
            compliance = (await client.call_tool(
                "load_feedback", {"channel": "compliance", "session_id": "s1"},
            )).data
            simulation = (await client.call_tool(
                "load_feedback", {"channel": "simulation", "session_id": "s1"},
            )).data
        assert compliance["status"] == "COMPLIANCE APPROVED"
        assert simulation == {}

    async def test_reset_approval_state_and_reset_feedback_channels_report_ok(self):
        async with Client(server.mcp) as client:
            r1 = (await client.call_tool("reset_approval_state", {"session_id": "s1"})).data
            r2 = (await client.call_tool("reset_feedback_channels", {"session_id": "s1"})).data
        assert r1 == {"status": "OK"}
        assert r2 == {"status": "OK"}

    async def test_review_status_summary_reflects_saved_approval(self):
        async with Client(server.mcp) as client:
            await client.call_tool(
                "save_feedback",
                {"feedback_data": {"status": "COMPLIANCE APPROVED", "data": []}, "channel": "compliance", "session_id": "s1"},
            )
            summary = (await client.call_tool(
                "review_status_summary", {"channels": ["compliance"], "session_id": "s1"},
            )).data
        assert "APPROVED" in summary


class TestAgenticWebMcpTools:
    def test_get_agent_manifest_via_mcp(self):
        import asyncio

        async def _run():
            async with Client(server.mcp) as client:
                manifest = (await client.call_tool("get_agent_manifest", {"base_url": "http://test"})).data
            assert manifest["schema_version"] == "1.0.0"
            assert manifest["standard"] == "Open Agentic Web MVP Profile"
            assert manifest["capabilities_count"] >= 32

        asyncio.run(_run())

    def test_list_agents_and_get_card_via_mcp(self):
        import asyncio

        async def _run():
            async with Client(server.mcp) as client:
                agents = (await client.call_tool("list_agents", {"category": "design"})).data
                assert len(agents) > 0
                assert all(a["category"] == "design" for a in agents)

                card = (await client.call_tool("get_agent_card", {"name": "design"})).data
                assert card["name"] == "design"
                assert "inputs" in card
                assert "outputs" in card

        asyncio.run(_run())

    def test_workflows_via_mcp(self):
        import asyncio

        async def _run():
            async with Client(server.mcp) as client:
                wfs = (await client.call_tool("list_workflows", {})).data
                assert len(wfs) >= 6
                assert any(w["workflow"] == "architecture_lifecycle" for w in wfs)

                wf = (await client.call_tool("get_workflow", {"workflow_name": "architecture_lifecycle"})).data
                assert wf["workflow"] == "architecture_lifecycle"
                assert "design" in wf["steps"]

        asyncio.run(_run())

    def test_artifact_contracts_via_mcp(self):
        import asyncio

        async def _run():
            async with Client(server.mcp) as client:
                contracts = (await client.call_tool("list_artifact_contracts", {})).data
                assert len(contracts) >= 13

                contract = (await client.call_tool("get_artifact_contract", {"artifact_type": "high_level_design"})).data
                assert contract["artifact_type"] == "high_level_design"
                assert "document_metadata" in contract["schema_fields"]

        asyncio.run(_run())

