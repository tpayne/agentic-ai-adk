"""Coverage for docgen/vsdx_export.py's switchable wrapper, in both modes
-- local mode is a plain pass-through (sanity-checked here), MCP mode runs
against the real ProcessToolkitServer subprocess, mirroring
test_mcp_mode_integration.py's own mcp_mode fixture/pattern exactly, so a
passing MCP-mode test proves bytes actually transited the wire rather than
two sides accidentally sharing one directory.
"""

import os
import socket
import subprocess
import sys
import time

import pytest

from process_interface import _transport, paths

SERVER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "samples", "MCP", "ProcessToolkitServer")
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def mcp_mode(monkeypatch, tmp_path):
    if not os.path.isdir(SERVER_DIR):
        pytest.skip(f"ProcessToolkitServer not found at {SERVER_DIR}")

    port = _free_port()
    server_output_dir = tmp_path / "server_output"
    server_output_dir.mkdir()

    env = {**os.environ, "PROCESS_TOOLKIT_MCP_OUTPUT_DIR": str(server_output_dir)}
    proc = subprocess.Popen(
        [
            "uv", "run", "python", "server.py",
            "--transport", "http", "--host", "127.0.0.1", "--port", str(port),
        ],
        cwd=SERVER_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.monotonic() + 30
    connected = False
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                connected = True
                break
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.2)

    if not connected:
        output = proc.stdout.read() if proc.stdout else ""
        proc.kill()
        pytest.fail(f"real ProcessToolkitServer subprocess never started listening.\n{output}")

    monkeypatch.setenv("PROCESS_TOOLKIT_MODE", "mcp")
    monkeypatch.setenv("PROCESS_TOOLKIT_MCP_URL", f"http://127.0.0.1:{port}/mcp")
    try:
        yield server_output_dir
    finally:
        _transport.reset()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


class TestBuildProcessDesignVsdxLocalMode:
    def test_falls_back_to_start_end_placeholder_with_nothing_saved(self):
        from process_interface.docgen import vsdx_export

        result = vsdx_export.build_process_design_vsdx("process")
        assert result.startswith("Visio diagram successfully exported to ")
        out_path = result.removeprefix("Visio diagram successfully exported to ")
        assert os.path.isfile(out_path)


class TestBuildCloudarchVsdxLocalMode:
    def test_errors_cleanly_with_nothing_saved(self):
        from process_interface.docgen import vsdx_export

        result = vsdx_export.build_cloudarch_vsdx()
        assert result.startswith("ERROR:")

    def test_exports_a_saved_diagram(self):
        from process_interface.docgen import vsdx_export
        from process_interface.drawio.persistence import DRAWIO_FILENAME

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
        with open(paths.output_path(DRAWIO_FILENAME), "w", encoding="utf-8") as f:
            f.write(xml)

        result = vsdx_export.build_cloudarch_vsdx()
        assert result.startswith("Visio diagram successfully exported to ")


class TestBothModesAgainstTheRealServer:
    def test_process_design_vsdx_mcp_mode_materializes_locally(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.docgen import vsdx_export

        result = vsdx_export.build_process_design_vsdx("process")
        assert result.startswith("Visio diagram successfully exported to "), result

        local_path = paths.output_path("process_flow.vsdx")
        assert os.path.isfile(local_path)
        assert os.path.getsize(local_path) > 0
        # Proof this came over the wire, not a shared directory: the file
        # also independently exists on the server's own side.
        assert os.path.isfile(os.path.join(server_output_dir, "process_flow.vsdx"))

    def test_process_design_vsdx_mcp_mode_not_applicable_for_requirements(self, mcp_mode):
        from process_interface.docgen import vsdx_export

        result = vsdx_export.build_process_design_vsdx("requirements")
        assert "NOT_APPLICABLE" in result, result

    def test_cloudarch_vsdx_mcp_mode_reports_no_diagram_available(self, mcp_mode):
        # Cloud-architecture XML is never actually transmitted to the
        # remote server (drawio's own write side stays port-local -- see
        # drawio/persistence.py's own module docstring), so this always
        # reports nothing saved in MCP mode -- the same already-accepted
        # limitation test_mcp_mode_phase5.py's own
        # TestCloudarchSimulationsBothModes class documents for every
        # other cloudarch-diagram-dependent MCP tool.
        from process_interface.docgen import vsdx_export

        result = vsdx_export.build_cloudarch_vsdx()
        assert result.startswith("ERROR:"), result
