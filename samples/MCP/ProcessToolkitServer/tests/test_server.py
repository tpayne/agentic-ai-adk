"""Regression coverage for server.py's MCP tools. Most coverage uses
fastmcp.Client's in-memory transport (no subprocess, no real socket); one
test exercises the real Streamable HTTP path end-to-end to prove the
network transport actually works, not just the tool functions in isolation.
"""

import base64
import datetime
import ipaddress
import os
import socket
import ssl
import threading
import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastmcp import Client

import server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _generate_self_signed_cert(tmp_path) -> tuple[str, str]:
    """A throwaway, locally-generated cert/key pair for proving HTTPS
    actually works end-to-end -- SAN covers 127.0.0.1 specifically (not
    just "localhost"), matching what the real test below connects to, so
    a real TLS handshake and real certificate validation both have to
    succeed, not just "a cert happened to be configured"."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(minutes=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certfile = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    return str(certfile), str(keyfile)


def _minimal_valid_togaf_doc() -> dict:
    data = server.dispatch.DOMAINS["togaf"].load_template()
    data["document_metadata"].update({
        "document_id": "ARCH-TEST-001",
        "system_name": "Checkout Service",
        "title": "Checkout Service",
    })
    data["architecture_requirements_specification"]["functional_requirements"] = []
    data["architecture_requirements_specification"]["non_functional_requirements"] = []
    # The template's one-item example shapes (business_architecture.capabilities,
    # etc.) are placeholders with blank "" values -- validate_togaf_json now
    # structurally validates these sections too, so clear them the same way the
    # requirements lists above already are.
    data["business_architecture"]["capabilities"] = []
    data["business_architecture"]["value_streams"] = []
    data["data_architecture"]["data_entities"] = []
    data["data_architecture"]["data_flows"] = []
    data["application_architecture"]["application_components"] = []
    data["application_architecture"]["application_communications"] = []
    data["technology_architecture"]["technology_portfolio"] = []
    data["opportunities_and_solutions"] = []
    data["migration_planning"]["work_packages"] = []
    data["architecture_compliance_assessment"]["compliance_findings"] = []
    return data


def _minimal_valid_itsm_doc() -> dict:
    data = server.dispatch.DOMAINS["itsm"].load_template()
    data["document_metadata"].update({
        "document_id": "ITSM-TEST-001",
        "system_name": "Checkout Service",
        "title": "Checkout Service",
    })
    # The template's one-item example shapes are placeholders with blank
    # "" values -- validate_itsm_json structurally validates these
    # sections too, so clear them the same way _minimal_valid_togaf_doc
    # above does.
    data["service_catalog"]["services"] = []
    data["incident_management"]["priority_matrix"] = []
    data["incident_management"]["process_steps"] = []
    data["problem_management"]["process_steps"] = []
    data["change_management"]["change_types"] = []
    data["change_management"]["process_steps"] = []
    data["request_fulfillment"]["request_types"] = []
    data["request_fulfillment"]["process_steps"] = []
    data["service_level_management"]["slas"] = []
    data["configuration_management"]["configuration_items"] = []
    data["configuration_management"]["relationships"] = []
    data["raci_matrix"] = []
    data["risks_and_controls"] = []
    return data


class TestListSchemaTypes:
    async def test_lists_every_registered_domain(self):
        async with Client(server.mcp) as client:
            result = await client.call_tool("list_schema_types")
        assert result.data == sorted([
            "design", "togaf", "itsm", "process", "requirements", "proposal_response", "test_specification",
        ])


class TestLoadTemplate:
    async def test_togaf_template_has_document_metadata_shape(self):
        async with Client(server.mcp) as client:
            result = await client.call_tool("load_template", {"schema_type": "togaf"})
        assert "document_metadata" in result.data
        assert "architecture_vision" in result.data

    async def test_unknown_schema_type_raises_a_clear_tool_error(self):
        async with Client(server.mcp) as client:
            with pytest.raises(Exception, match="Unknown schema_type"):
                await client.call_tool("load_template", {"schema_type": "nope"})


class TestTogafRoundTrip:
    async def test_validate_persist_generate_document_and_download(self):
        data = _minimal_valid_togaf_doc()
        async with Client(server.mcp) as client:
            validation = (await client.call_tool(
                "validate_json", {"schema_type": "togaf", "data": data},
            )).data
            assert validation["valid"], validation["issues"]

            persisted = (await client.call_tool(
                "persist_json", {"schema_type": "togaf", "data": data, "session_id": "s1"},
            )).data
            assert persisted["success"], persisted["message"]

            context = (await client.call_tool(
                "load_context", {"schema_type": "togaf", "session_id": "s1"},
            )).data
            assert context["document_metadata"]["system_name"] == "Checkout Service"

            generated = (await client.call_tool(
                "generate_document",
                {"schema_type": "togaf", "session_id": "s1", "variant": "vision"},
            )).data
            assert generated["message"].startswith("SUCCESS"), generated["message"]
            assert len(generated["documents"]) == 1
            doc = generated["documents"][0]
            assert doc["filename"].endswith(".docx")
            assert doc["size_bytes"] > 0
            # bytes round-trip cleanly through base64
            assert len(base64.b64decode(doc["base64"])) == doc["size_bytes"]

            artifacts = (await client.call_tool(
                "list_artifacts", {"session_id": "s1"},
            )).data
            assert doc["filename"] in {a["filename"] for a in artifacts}

            fetched = (await client.call_tool(
                "get_artifact", {"filename": doc["filename"], "session_id": "s1"},
            )).data
            assert fetched["base64"] == doc["base64"]

    async def test_sessions_do_not_see_each_others_artifacts(self):
        data = _minimal_valid_togaf_doc()
        async with Client(server.mcp) as client:
            await client.call_tool("persist_json", {"schema_type": "togaf", "data": data, "session_id": "a"})
            await client.call_tool("generate_document", {"schema_type": "togaf", "session_id": "a"})
            artifacts_b = (await client.call_tool("list_artifacts", {"session_id": "b"})).data
        assert artifacts_b == []

    async def test_unsafe_session_id_raises_a_clean_tool_error_not_a_crash(self):
        # Regression: _session used to try/except around *constructing*
        # paths.use_session(...) rather than around entering it, so this
        # raised a raw, unconverted ValueError instead of a ToolError --
        # caught by tests/test_server_helpers.py's unit coverage and fixed
        # in server.py's _session. This proves the fix holds through the
        # real MCP call path too, not just a direct Python call.
        async with Client(server.mcp) as client:
            with pytest.raises(Exception, match="Refusing to use"):
                await client.call_tool(
                    "persist_json",
                    {"schema_type": "togaf", "data": {}, "session_id": "../escape"},
                )

    async def test_get_artifact_rejects_path_traversal(self):
        async with Client(server.mcp) as client:
            with pytest.raises(Exception, match="No such artifact"):
                await client.call_tool("get_artifact", {"filename": "../../etc/passwd", "session_id": "s1"})


class TestItsmRoundTrip:
    """Mirrors TestTogafRoundTrip -- ITSM has no document-variant kwarg
    and always produces exactly one document (no Vision/Definition-style
    split)."""

    async def test_validate_persist_generate_document_and_download(self):
        data = _minimal_valid_itsm_doc()
        async with Client(server.mcp) as client:
            validation = (await client.call_tool(
                "validate_json", {"schema_type": "itsm", "data": data},
            )).data
            assert validation["valid"], validation["issues"]

            persisted = (await client.call_tool(
                "persist_json", {"schema_type": "itsm", "data": data, "session_id": "s1"},
            )).data
            assert persisted["success"], persisted["message"]

            context = (await client.call_tool(
                "load_context", {"schema_type": "itsm", "session_id": "s1"},
            )).data
            assert context["document_metadata"]["system_name"] == "Checkout Service"

            generated = (await client.call_tool(
                "generate_document", {"schema_type": "itsm", "session_id": "s1"},
            )).data
            assert generated["message"].startswith("SUCCESS"), generated["message"]
            assert len(generated["documents"]) == 1
            doc = generated["documents"][0]
            assert doc["filename"].endswith(".docx")
            assert doc["size_bytes"] > 0
            assert len(base64.b64decode(doc["base64"])) == doc["size_bytes"]

            artifacts = (await client.call_tool(
                "list_artifacts", {"session_id": "s1"},
            )).data
            assert doc["filename"] in {a["filename"] for a in artifacts}

    async def test_simulate_itsm_risk_reports_a_grounded_bottleneck(self):
        data = _minimal_valid_itsm_doc()
        data["incident_management"]["process_steps"] = [
            {"step_id": "INC-1", "step_name": "Log", "responsible_role": "Service Desk"},
            {"step_id": "INC-2", "step_name": "Triage", "responsible_role": "Service Desk"},
        ]
        async with Client(server.mcp) as client:
            await client.call_tool("persist_json", {"schema_type": "itsm", "data": data, "session_id": "s1"})
            result = (await client.call_tool("simulate_itsm_risk", {"session_id": "s1"})).data
        assert len(result["bottlenecks"]) == 1
        assert "Service Desk" in result["bottlenecks"][0]


class TestGenerateDiagram:
    async def test_not_applicable_schema_types_report_cleanly_without_fabricating_a_diagram(self):
        async with Client(server.mcp) as client:
            for schema_type in ("requirements", "proposal_response", "test_specification", "togaf", "itsm"):
                result = (await client.call_tool(
                    "generate_diagram", {"schema_type": schema_type, "session_id": "s1"},
                )).data
                assert result["diagram"] is None
                assert "NOT_APPLICABLE" in result["message"], (schema_type, result["message"])


class TestExportProcessDesignVsdx:
    async def test_not_applicable_schema_types_report_cleanly_without_fabricating_a_vsdx(self):
        async with Client(server.mcp) as client:
            for schema_type in ("requirements", "proposal_response", "test_specification", "togaf", "itsm"):
                result = (await client.call_tool(
                    "export_process_design_vsdx", {"schema_type": schema_type, "session_id": "s1"},
                )).data
                assert result["vsdx"] is None
                assert "NOT_APPLICABLE" in result["message"], (schema_type, result["message"])

    async def test_process_with_no_saved_data_still_exports_the_start_end_fallback(self):
        # _infer_edges_from_json ALWAYS returns at least a Start->End
        # fallback edge when process_data.json is missing -- same "always
        # produces something" contract generate_diagram relies on -- so
        # this succeeds even with nothing persisted first.
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "export_process_design_vsdx", {"schema_type": "process", "session_id": "s2"},
            )).data
            assert result["vsdx"] is not None
            assert result["vsdx"]["filename"].endswith(".vsdx")
            assert result["vsdx"]["size_bytes"] > 0
            assert "successfully exported" in result["message"], result["message"]


class TestExportCloudarchVsdx:
    async def test_errors_cleanly_without_fabricating_a_vsdx_when_nothing_saved(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "export_cloudarch_vsdx", {"session_id": "s3"},
            )).data
            assert result["vsdx"] is None
            assert result["message"].startswith("ERROR:"), result["message"]

    async def test_exports_a_saved_diagrams_vertices_and_edges(self):
        xml = (
            '<mxGraphModel><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/>'
            '<mxCell id="api" value="API Gateway" vertex="1" parent="1" '
            'style="shape=mxgraph.aws4.resourceIcon;"/>'
            '<mxCell id="db" value="Database" vertex="1" parent="1" '
            'style="shape=mxgraph.aws4.resourceIcon;"/>'
            '<mxCell id="e1" edge="1" source="api" target="db" parent="1"/>'
            '</root></mxGraphModel>'
        )
        with server.paths.use_session("s4"):
            with open(os.path.join(server.paths.output_dir(), "cloudarch_drawio.xml"), "w", encoding="utf-8") as f:
                f.write(xml)

        async with Client(server.mcp) as client:
            result = (await client.call_tool("export_cloudarch_vsdx", {"session_id": "s4"})).data
            assert result["vsdx"] is not None
            assert result["vsdx"]["size_bytes"] > 0
            assert "successfully exported" in result["message"], result["message"]


class TestExportProjectPlan:
    async def test_not_applicable_schema_types_report_cleanly_without_fabricating_a_plan(self):
        async with Client(server.mcp) as client:
            for schema_type in ("requirements", "process", "design", "test_specification", "togaf", "itsm"):
                result = (await client.call_tool(
                    "export_project_plan", {"schema_type": schema_type, "session_id": "s1"},
                )).data
                assert result["project_plan"] is None
                assert "NOT_APPLICABLE" in result["message"], (schema_type, result["message"])

    async def test_portfolio_backlog_with_nothing_saved_errors_without_fabricating_a_plan(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "export_project_plan", {"schema_type": "portfolio_backlog", "session_id": "s2"},
            )).data
            assert result["project_plan"] is None
            assert result["message"].startswith("ERROR:"), result["message"]

    async def test_proposal_response_with_nothing_saved_errors_without_fabricating_a_plan(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "export_project_plan", {"schema_type": "proposal_response", "session_id": "s3"},
            )).data
            assert result["project_plan"] is None
            assert result["message"].startswith("ERROR:"), result["message"]

    async def test_exports_a_saved_portfolio_backlogs_epics_features_and_stories(self):
        priority = {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2}
        backlog = {
            "name": "Checkout Backlog", "summary": "s", "source_name": "Checkout", "source_artifact": "design",
            "epics": [{
                "id": "EPIC-1", "title": "Checkout flow", "description": "d",
                "traces_to": ["REQ-1"], "priority_components": priority, "job_size": 8,
                "features": [{
                    "id": "FEAT-1", "title": "Cart management", "description": "d",
                    "traces_to": ["REQ-1"], "priority_components": priority, "job_size": 5,
                    "stories": [{
                        "id": "STORY-1", "title": "Add to cart", "description": "d",
                        "traces_to": ["REQ-1"], "priority_components": priority, "job_size": 3,
                        "acceptance_criteria": ["Given an item, when added, then it appears in the cart."],
                    }],
                }],
            }],
        }
        async with Client(server.mcp) as client:
            saved = (await client.call_tool(
                "generate_portfolio_backlog", {"backlog": backlog, "session_id": "s4"},
            )).data
            assert saved["message"].startswith("SUCCESS"), saved["message"]

            result = (await client.call_tool(
                "export_project_plan", {"schema_type": "portfolio_backlog", "session_id": "s4"},
            )).data
            assert result["project_plan"] is not None
            assert result["project_plan"]["filename"].endswith(".xml")
            assert result["project_plan"]["size_bytes"] > 0
            assert "successfully exported" in result["message"], result["message"]

    async def test_exports_a_saved_proposal_responses_implementation_plan_phases(self):
        response = {
            "name": "Harborlight Response",
            "implementation_plan": [
                {"phase": "Discovery", "timing": "2 weeks", "deliverable": "d", "acceptance_criteria": "a"},
            ],
        }
        async with Client(server.mcp) as client:
            saved = (await client.call_tool(
                "persist_json", {"schema_type": "proposal_response", "data": response, "session_id": "s5"},
            )).data
            assert saved["success"], saved["message"]

            result = (await client.call_tool(
                "export_project_plan", {"schema_type": "proposal_response", "session_id": "s5"},
            )).data
            assert result["project_plan"] is not None
            assert result["project_plan"]["filename"].endswith(".xml")
            assert "successfully exported" in result["message"], result["message"]


class TestPersistJsonValidatesFirst:
    async def test_invalid_togaf_data_is_rejected_without_writing_anything(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "persist_json", {"schema_type": "togaf", "data": {}, "session_id": "s1"},
            )).data
            assert not result["success"]

            artifacts = (await client.call_tool("list_artifacts", {"session_id": "s1"})).data
            assert artifacts == []

    async def test_requirements_persist_is_zero_validation_matching_process_toolkit(self):
        # Regression: this domain's persist used to compose validate-then-
        # save at this server's own boundary, making MCP mode strictly
        # stricter than local mode (which calls process_toolkit's own
        # save_requirements_summary directly -- intentionally zero-
        # validation, by its own docstring, so an in-progress draft that
        # doesn't yet pass validate_requirements_summary's structural
        # checks can still be saved). Deliberately invalid data (empty
        # dict) must still succeed here, proving persist_json for
        # "requirements" is a plain save now, not a validating one.
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "persist_json", {"schema_type": "requirements", "data": {"anything": "goes"}, "session_id": "s1"},
            )).data
            assert result["success"], result["message"]

            loaded = (await client.call_tool(
                "load_context", {"schema_type": "requirements", "session_id": "s1"},
            )).data
            assert loaded["anything"] == "goes"


class TestPortfolioBacklog:
    async def test_save_and_load_round_trip_with_a_rendered_workbook(self):
        priority = {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2}
        backlog = {
            "name": "Checkout Backlog",
            "summary": "Backlog for the checkout service.",
            "source_name": "Checkout Service",
            "source_artifact": "design",
            "epics": [{
                "id": "EPIC-1",
                "title": "Checkout flow",
                "description": "Core checkout.",
                "traces_to": ["REQ-1"],
                "priority_components": priority,
                "job_size": 8,
                "features": [{
                    "id": "FEAT-1",
                    "title": "Cart management",
                    "description": "Add/remove items from the cart.",
                    "traces_to": ["REQ-1"],
                    "priority_components": priority,
                    "job_size": 5,
                    "stories": [{
                        "id": "STORY-1",
                        "title": "Add to cart",
                        "description": "User can add an item to the cart.",
                        "traces_to": ["REQ-1"],
                        "priority_components": priority,
                        "job_size": 3,
                        "acceptance_criteria": ["Given an item, when added, then it appears in the cart."],
                    }],
                }],
            }],
        }
        async with Client(server.mcp) as client:
            saved = (await client.call_tool(
                "generate_portfolio_backlog", {"backlog": backlog, "session_id": "s1"},
            )).data
            assert saved["message"].startswith("SUCCESS"), saved["message"]
            assert saved["workbook"] is not None
            assert saved["workbook"]["filename"].endswith(".xlsx")

            loaded = (await client.call_tool(
                "load_portfolio_backlog_json", {"session_id": "s1"},
            )).data
            assert loaded["name"] == "Checkout Backlog"


class TestRateLimitingIsDisabledForThisSharedTestInstance:
    """A safety-net check on the assumption every other test in this file
    (and test_dispatch.py) depends on: that tests/conftest.py's
    PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED=false setdefault actually took
    effect before server.py's module-level `if _rate_limiting_enabled():
    mcp.add_middleware(...)` ran. If this ever started failing, every
    other test calling through server.mcp in-memory would start failing
    too, for an unrelated, confusing reason -- see conftest.py's own
    comment for why. The middleware class, client-id function, and
    enabled/disabled toggle itself are tested directly in
    tests/test_server_helpers.py against short-lived, dedicated FastMCP
    instances that never touch this shared bucket."""

    def test_server_mcp_has_no_rate_limiting_middleware_installed(self):
        assert not any(
            isinstance(mw, server.ToolCallRateLimitingMiddleware) for mw in server.mcp.middleware
        )


class TestRealStreamableHttpTransport:
    async def test_round_trip_over_an_actual_http_connection(self):
        port = _free_port()

        def _serve():
            server.mcp.run(transport="http", host="127.0.0.1", port=port, show_banner=False)

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()

        deadline = time.monotonic() + 5
        connected = False
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    connected = True
                    break
            except OSError:
                time.sleep(0.1)
        assert connected, "server did not start listening in time"

        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            result = await client.call_tool("list_schema_types")
        assert "togaf" in result.data


class TestRealHttpsTransport:
    async def test_round_trip_over_an_actual_tls_connection(self, tmp_path):
        certfile, keyfile = _generate_self_signed_cert(tmp_path)
        port = _free_port()

        def _serve():
            server.mcp.run(
                transport="http", host="127.0.0.1", port=port, show_banner=False,
                uvicorn_config={"ssl_certfile": certfile, "ssl_keyfile": keyfile},
            )

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()

        deadline = time.monotonic() + 5
        connected = False
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    connected = True
                    break
            except OSError:
                time.sleep(0.1)
        assert connected, "server did not start listening in time"

        # Trusts our own throwaway cert explicitly rather than disabling
        # verification -- a real client validating a real certificate
        # against a real TLS handshake, not just "the socket happened to
        # connect."
        trust_context = ssl.create_default_context(cafile=certfile)
        async with Client(f"https://127.0.0.1:{port}/mcp", verify=trust_context) as client:
            result = await client.call_tool("list_schema_types")
        assert "togaf" in result.data

    async def test_plain_http_is_rejected_by_a_tls_only_client(self, tmp_path):
        # Same server, same port range, but this time started WITHOUT TLS --
        # confirms the test above's success is really coming from HTTPS
        # being active, not from some unrelated client-side leniency.
        certfile, _keyfile = _generate_self_signed_cert(tmp_path)
        port = _free_port()

        def _serve():
            server.mcp.run(transport="http", host="127.0.0.1", port=port, show_banner=False)

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()

        deadline = time.monotonic() + 5
        connected = False
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    connected = True
                    break
            except OSError:
                time.sleep(0.1)
        assert connected, "server did not start listening in time"

        trust_context = ssl.create_default_context(cafile=certfile)
        with pytest.raises(Exception):
            async with Client(f"https://127.0.0.1:{port}/mcp", verify=trust_context) as client:
                await client.call_tool("list_schema_types")
