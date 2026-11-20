"""Coverage for docgen/project_plan_export.py's switchable wrapper, in both
modes -- local mode is a plain pass-through (sanity-checked here), MCP mode
runs against the real ProcessToolkitServer subprocess, mirroring
test_vsdx_export.py's own mcp_mode fixture/pattern exactly, so a passing
MCP-mode test proves bytes actually transited the wire rather than two sides
accidentally sharing one directory.
"""

import os
import socket
import subprocess
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


def _save_backlog():
    # The switchable wrapper, not process_toolkit's own local-only save --
    # in MCP mode this must actually reach the real server over the wire,
    # the same way the test itself later reads the result back.
    from process_interface.portfolio_backlog.portfolio_backlog import save_portfolio_backlog

    save_portfolio_backlog({
        "name": "Test Backlog", "summary": "s", "source_artifact": "design", "source_name": "x",
        "epics": [{
            "id": "EPIC-001", "title": "Epic One", "description": "d", "strategic_theme": "t",
            "traces_to": ["FR-1"],
            "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
            "job_size": 3,
            "features": [{
                "id": "FEAT-001", "title": "Feature One", "description": "d", "strategic_theme": "t",
                "traces_to": ["FR-1"],
                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                "job_size": 3,
                "stories": [{
                    "id": "STORY-001", "title": "Story One", "description": "d", "strategic_theme": "t",
                    "traces_to": ["FR-1"],
                    "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                    "job_size": 3, "acceptance_criteria": ["works"],
                }],
            }],
        }],
    })


def _save_proposal_response():
    from process_interface.proposal_response.proposal_response import save_proposal_response

    save_proposal_response({
        "name": "Test Response",
        "implementation_plan": [
            {"phase": "Discovery", "timing": "2 weeks", "deliverable": "d", "acceptance_criteria": "a"},
        ],
    })


class TestBuildPortfolioBacklogProjectPlanLocalMode:
    def test_errors_cleanly_with_nothing_saved(self):
        from process_interface.docgen import project_plan_export

        result = project_plan_export.build_portfolio_backlog_project_plan()
        assert result.startswith("ERROR:")

    def test_exports_a_saved_backlog(self):
        from process_interface.docgen import project_plan_export

        _save_backlog()
        result = project_plan_export.build_portfolio_backlog_project_plan()
        assert result.startswith("Project plan successfully exported to "), result
        out_path = result.removeprefix("Project plan successfully exported to ")
        assert os.path.isfile(out_path)


class TestBuildProposalResponseProjectPlanLocalMode:
    def test_errors_cleanly_with_nothing_saved(self):
        from process_interface.docgen import project_plan_export

        result = project_plan_export.build_proposal_response_project_plan()
        assert result.startswith("ERROR:")

    def test_exports_a_saved_response(self):
        from process_interface.docgen import project_plan_export

        _save_proposal_response()
        result = project_plan_export.build_proposal_response_project_plan()
        assert result.startswith("Project plan successfully exported to "), result
        out_path = result.removeprefix("Project plan successfully exported to ")
        assert os.path.isfile(out_path)


class TestBothModesAgainstTheRealServer:
    def test_portfolio_backlog_project_plan_mcp_mode_materializes_locally(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.docgen import project_plan_export

        _save_backlog()
        result = project_plan_export.build_portfolio_backlog_project_plan()
        assert result.startswith("Project plan successfully exported to "), result

        local_path = paths.output_path("portfolio_backlog_project_plan.xml")
        assert os.path.isfile(local_path)
        assert os.path.getsize(local_path) > 0
        # Proof this came over the wire, not a shared directory: the file
        # also independently exists on the server's own side.
        assert os.path.isfile(os.path.join(server_output_dir, "portfolio_backlog_project_plan.xml"))

    def test_proposal_response_project_plan_mcp_mode_materializes_locally(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.docgen import project_plan_export

        _save_proposal_response()
        result = project_plan_export.build_proposal_response_project_plan()
        assert result.startswith("Project plan successfully exported to "), result

        local_path = paths.output_path("proposal_response_project_plan.xml")
        assert os.path.isfile(local_path)
        assert os.path.isfile(os.path.join(server_output_dir, "proposal_response_project_plan.xml"))

    def test_mcp_mode_reports_error_cleanly_when_nothing_saved(self, mcp_mode):
        from process_interface.docgen import project_plan_export

        result = project_plan_export.build_portfolio_backlog_project_plan()
        assert result.startswith("ERROR:"), result
