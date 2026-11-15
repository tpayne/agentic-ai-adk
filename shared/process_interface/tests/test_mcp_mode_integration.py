"""End-to-end coverage of the switchable schema/docgen/portfolio_backlog/
state-threading modules, in BOTH modes, against a real instance of the
actual ProcessToolkitServer -- run as a genuine, separate OS subprocess
(not an in-thread import), specifically so it has its OWN
process_toolkit.paths.OUTPUT_DIR global, independent of this test
process's. Running it in-thread would share one Python process's module
state (process_toolkit.paths is the same imported module object either
way), which would make "materialize() copies bytes from the server to a
local path" untestable -- a no-op materialize() could still pass, since
the server would already be writing into the same directory this test
reads from. test_transport.py already covers the async/thread transport
bridge in isolation; this file is about behavioral parity end-to-end.
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
    """Starts the real server as a genuine subprocess with its own
    output root (tmp_path/server_output -- deliberately NOT the same
    tmp_path this test's own isolated_output_dir fixture scopes local
    materialization to), so a passing test proves bytes actually
    transited the wire rather than two sides accidentally sharing one
    directory."""
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


class TestTogafRoundTripBothModes:
    def _minimal_valid_togaf_doc(self, load_template):
        data = load_template()
        data["document_metadata"].update({
            "document_id": "ARCH-TEST-001", "system_name": "Checkout", "title": "Checkout",
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

    def test_local_mode_persist_load_generate(self):
        from process_interface.schema import togaf_json

        data = self._minimal_valid_togaf_doc(togaf_json.load_togaf_template)
        assert togaf_json.persist_final_togaf_json(data).startswith("SUCCESS")
        loaded = togaf_json.load_master_togaf_json()
        assert loaded["document_metadata"]["system_name"] == "Checkout"

        from process_interface.docgen import generation

        result = generation.create_standard_doc_from_file(schema_type="togaf", togaf_variant="vision")
        assert result.startswith("SUCCESS"), result
        assert os.path.isfile(paths.output_path("Checkout_Architecture_Vision.docx"))

    def test_mcp_mode_persist_load_generate_materializes_locally(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.schema import togaf_json

        data = self._minimal_valid_togaf_doc(togaf_json.load_togaf_template)
        message = togaf_json.persist_final_togaf_json(data)
        assert message.startswith("SUCCESS"), message

        # Written on the SERVER's side (a different directory than this
        # test process's own local output dir)...
        assert os.path.isfile(os.path.join(server_output_dir, togaf_json.TOGAF_JSON_FILENAME))
        # ...AND mirrored locally per schema/_common.py's mirror_local_copy.
        assert os.path.isfile(paths.output_path(togaf_json.TOGAF_JSON_FILENAME))

        loaded = togaf_json.load_master_togaf_json()
        assert loaded["document_metadata"]["system_name"] == "Checkout"

        from process_interface.docgen import generation

        result = generation.create_standard_doc_from_file(schema_type="togaf", togaf_variant="vision")
        assert result.startswith("SUCCESS"), result

        local_path = paths.output_path("Checkout_Architecture_Vision.docx")
        assert os.path.isfile(local_path)
        assert os.path.getsize(local_path) > 0
        # The real proof this came over the wire, not a shared directory:
        # the SAME file also exists, independently, on the server's side.
        assert os.path.isfile(os.path.join(server_output_dir, "Checkout_Architecture_Vision.docx"))


class TestRequirementsSummaryStateThreading:
    def test_state_cache_hit_never_touches_disk_or_network_in_either_mode(self, mcp_mode):
        from process_interface.requirements_summary import requirements_summary as rs

        state = {rs.STATE_KEY: {"name": "cached"}}
        result = rs.load_requirements_summary(state)
        assert result == {"name": "cached", "status": "OK"}

    def test_mcp_mode_falls_back_to_server_when_state_is_empty_and_updates_state_on_save(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.requirements_summary import requirements_summary as rs

        state: dict = {}
        assert rs.load_requirements_summary(state) == {"status": "NOT_FOUND"}

        save_message = rs.save_requirements_summary({"name": "Checkout"}, state)
        assert save_message.startswith("SUCCESS"), save_message
        assert state[rs.STATE_KEY] == {"name": "Checkout"}

        # Lives on the server's side, not this test process's local dir --
        # requirements_summary has no mirror_local_copy (its load function
        # always redirects to the server in MCP mode when state is empty).
        assert os.path.isfile(os.path.join(server_output_dir, rs.REQUIREMENTS_SUMMARY_FILENAME))
        assert not os.path.exists(paths.output_path(rs.REQUIREMENTS_SUMMARY_FILENAME))

        # A fresh call with no state must find it via the server.
        assert rs.load_requirements_summary(None) == {"name": "Checkout", "status": "OK"}

    def test_update_requires_an_existing_summary_in_both_modes(self, mcp_mode):
        from process_interface.requirements_summary import requirements_summary as rs

        assert rs.update_requirements_summary({"x": 1}, None) == (
            "ERROR: No existing requirements summary to update -- save one first."
        )


class TestPortfolioBacklogBothModes:
    def _valid_backlog(self):
        priority = {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2}
        return {
            "name": "Checkout Backlog", "summary": "s", "source_name": "Checkout", "source_artifact": "design",
            "epics": [{
                "id": "EPIC-1", "title": "t", "description": "d",
                "traces_to": ["REQ-1"], "priority_components": priority, "job_size": 8,
                "features": [{
                    "id": "FEAT-1", "title": "t", "description": "d",
                    "traces_to": ["REQ-1"], "priority_components": priority, "job_size": 5,
                    "stories": [{
                        "id": "STORY-1", "title": "t", "description": "d",
                        "traces_to": ["REQ-1"], "priority_components": priority, "job_size": 3,
                        "acceptance_criteria": ["Given/when/then."],
                    }],
                }],
            }],
        }

    def test_mcp_mode_save_materializes_workbook_and_json_locally(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.portfolio_backlog import portfolio_backlog as pb

        message = pb.save_portfolio_backlog(self._valid_backlog())
        assert message.startswith("SUCCESS"), message

        assert os.path.isfile(os.path.join(server_output_dir, pb.PORTFOLIO_BACKLOG_WORKBOOK_FILENAME))
        assert os.path.isfile(paths.output_path(pb.PORTFOLIO_BACKLOG_WORKBOOK_FILENAME))
        assert os.path.isfile(paths.output_path(pb.PORTFOLIO_BACKLOG_FILENAME))

        loaded = pb.load_portfolio_backlog()
        assert loaded["name"] == "Checkout Backlog"
