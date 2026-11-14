"""Regression coverage for server.py's MCP tools. Most coverage uses
fastmcp.Client's in-memory transport (no subprocess, no real socket); one
test exercises the real Streamable HTTP path end-to-end to prove the
network transport actually works, not just the tool functions in isolation.
"""

import base64
import datetime
import ipaddress
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
    return data


class TestListSchemaTypes:
    async def test_lists_every_registered_domain(self):
        async with Client(server.mcp) as client:
            result = await client.call_tool("list_schema_types")
        assert result.data == sorted([
            "design", "togaf", "process", "requirements", "proposal_response", "test_specification",
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


class TestGenerateDiagram:
    async def test_not_applicable_schema_types_report_cleanly_without_fabricating_a_diagram(self):
        async with Client(server.mcp) as client:
            for schema_type in ("requirements", "proposal_response", "test_specification", "togaf"):
                result = (await client.call_tool(
                    "generate_diagram", {"schema_type": schema_type, "session_id": "s1"},
                )).data
                assert result["diagram"] is None
                assert "NOT_APPLICABLE" in result["message"], (schema_type, result["message"])


class TestPersistJsonValidatesFirst:
    async def test_invalid_togaf_data_is_rejected_without_writing_anything(self):
        async with Client(server.mcp) as client:
            result = (await client.call_tool(
                "persist_json", {"schema_type": "togaf", "data": {}, "session_id": "s1"},
            )).data
            assert not result["success"]

            artifacts = (await client.call_tool("list_artifacts", {"session_id": "s1"})).data
            assert artifacts == []

    async def test_requirements_domain_composes_validate_then_save_at_this_boundary(self):
        async with Client(server.mcp) as client:
            blank = (await client.call_tool("load_template", {"schema_type": "requirements"})).data
            # The template ships one example register entry with blank
            # fields as a shape reference (same convention as togaf's
            # template) -- clear it so this demo's validation doesn't fail
            # on an intentionally-empty placeholder.
            blank["requirements_register"] = []
            result = (await client.call_tool(
                "persist_json", {"schema_type": "requirements", "data": blank, "session_id": "s1"},
            )).data
            # process_toolkit's own validate_requirements_summary is intentionally
            # soft (old-format detection only) -- a freshly loaded template must
            # pass it, proving this server's validate-then-save composition
            # doesn't newly reject something the domain itself considers fine.
            assert result["success"], result["message"]


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
