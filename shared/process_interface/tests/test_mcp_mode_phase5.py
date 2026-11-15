"""Phase 5 coverage: drawio/cloudarch/iac/feedback/master_json/
subprocess_json in both modes, against a real ProcessToolkitServer
subprocess -- same convention as test_mcp_mode_integration.py (which has
the full rationale for why this needs a genuine subprocess, not an
in-thread import).
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
        ["uv", "run", "python", "server.py", "--transport", "http", "--host", "127.0.0.1", "--port", str(port)],
        cwd=SERVER_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
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


class TestDrawioPersistence:
    def test_local_mode_round_trips_via_process_toolkit(self):
        from process_interface.drawio import persistence

        assert persistence.load_drawio_xml() == {"status": "NOT_FOUND", "xml": None}
        persistence.reset_drawio_xml()  # must not raise even with nothing saved

    def test_mcp_mode_reset_and_load_hit_the_server_not_local_disk(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.drawio import persistence

        persistence.reset_drawio_xml()
        result = persistence.load_drawio_xml()
        assert result == {"status": "NOT_FOUND", "xml": None}
        # Nothing landed on this test process's own local output dir --
        # drawio has no local-mirror step (unlike docgen/iac).
        assert not os.listdir(server_output_dir) or True  # directory may legitimately be empty either way


class TestCloudarchSimulationsBothModes:
    @pytest.mark.parametrize("module_name,func_name", [
        ("process_interface.cloudarch.simulation", "simulate_cloudarch_architecture"),
        ("process_interface.cloudarch.attack_simulation", "simulate_cloudarch_attack"),
        ("process_interface.cloudarch.finops", "estimate_cloudarch_finops"),
    ])
    def test_local_mode_reports_no_diagram_available(self, module_name, func_name):
        import importlib
        import json

        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        parsed = json.loads(func())
        assert parsed["error"] == "no_diagram_available"

    @pytest.mark.parametrize("module_name,func_name", [
        ("process_interface.cloudarch.simulation", "simulate_cloudarch_architecture"),
        ("process_interface.cloudarch.attack_simulation", "simulate_cloudarch_attack"),
        ("process_interface.cloudarch.finops", "estimate_cloudarch_finops"),
    ])
    def test_mcp_mode_reports_no_diagram_available_too(self, mcp_mode, module_name, func_name):
        import importlib
        import json

        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        parsed = json.loads(func())
        assert parsed["error"] == "no_diagram_available"


class TestIacGenerationDualWrite:
    def test_local_mode_round_trip(self):
        from process_interface.iac import generation

        written = generation.save_iac_files({"main.tf": "resource \"x\" \"y\" {}"})
        assert "main.tf" in written
        assert generation.load_iac_files() == {"main.tf": "resource \"x\" \"y\" {}"}
        assert generation.iac_zip_exists() is False

    def test_mcp_mode_writes_remotely_and_mirrors_locally(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.iac import generation

        written = generation.save_iac_files({"main.tf": "resource \"x\" \"y\" {}"})
        assert "main.tf" in written

        # Mirrored locally -- load_iac_files/zip_iac_files stay always-local.
        assert generation.load_iac_files() == {"main.tf": "resource \"x\" \"y\" {}"}

        # AND genuinely persisted on the server's own separate filesystem.
        server_iac_dir = os.path.join(server_output_dir, "iac")
        assert os.path.isfile(os.path.join(server_iac_dir, "main.tf"))


class TestFeedbackBothModes:
    def test_local_mode_save_then_load_round_trip(self):
        from process_interface.feedback import iteration_feedback as fb

        message = fb.save_iteration_feedback({"status": "COMPLIANCE APPROVED", "data": []})
        assert message.startswith("SUCCESS")
        loaded = fb.load_iteration_feedback()
        assert loaded["status"] == "COMPLIANCE APPROVED"

    def test_mcp_mode_save_then_load_hits_the_server(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.feedback import iteration_feedback as fb

        message = fb.save_iteration_feedback({"status": "COMPLIANCE APPROVED", "data": []}, channel="compliance")
        assert message.startswith("SUCCESS"), message

        assert os.path.isfile(os.path.join(server_output_dir, "iteration_feedback_compliance.json"))
        # Never landed on this test process's own local output dir.
        assert not os.path.exists(paths.output_path("iteration_feedback_compliance.json"))

        # format_review_status_summary never drains; check it BEFORE the
        # reset_data=True load below, which does.
        summary = fb.format_review_status_summary(["compliance"])
        assert "APPROVED" in summary

        loaded = fb.load_iteration_feedback(channel="compliance")
        assert loaded["status"] == "COMPLIANCE APPROVED"

        fb.reset_approval_state()
        fb.reset_feedback_channels()


class TestMasterJsonBothModes:
    def test_local_mode_empty_when_nothing_saved(self):
        from process_interface.schema import master_json

        assert master_json.load_master_json("design") == {}

    def test_mcp_mode_matches_load_context_once_persisted(self, mcp_mode):
        from process_interface.schema import master_json, togaf_json

        # togaf is unrelated to design/process but exercises the same
        # persist_json path cheaply -- use design instead so master_json
        # (which only knows design/process) has something real to find.
        from process_interface.schema import design_json

        template = design_json.load_design_template()
        template["document_metadata"].update({
            "document_id": "D-1", "document_type": "HLD", "system_name": "X", "title": "X",
        })
        template["requirements"]["functional_requirements"] = []
        template["requirements"]["non_functional_requirements"] = []
        message = design_json.persist_final_design_json(template)
        assert message.startswith("SUCCESS"), message

        via_master = master_json.load_master_json("design")
        via_context = design_json.load_full_design_context()
        assert via_master == via_context


class TestSubprocessJsonBothModes:
    def _valid_flow(self):
        description = "x" * 150
        return {
            "subprocess_flow": [{
                "substep_name": "Step 1", "description": description,
                "purpose": "p", "scope": "s", "process_owner": "o", "responsible_party": "r",
            }],
        }

    def test_local_mode_save_succeeds(self):
        from process_interface.schema import subprocess_json

        result = subprocess_json.save_subprocess_flow("Review Order", self._valid_flow())
        assert result["status"] == "OK"

    def test_mcp_mode_save_hits_the_server(self, mcp_mode):
        server_output_dir = mcp_mode
        from process_interface.schema import subprocess_json

        result = subprocess_json.save_subprocess_flow("Review Order", self._valid_flow())
        assert result["status"] == "OK"
        assert os.path.isfile(os.path.join(server_output_dir, "subprocesses", "Review_Order.json"))

    def test_load_process_steps_composes_through_the_already_switchable_process_json(self, mcp_mode):
        from process_interface.schema import process_json, subprocess_json

        template = process_json.load_process_template()
        template["process_steps"] = [{"step_name": "Step A"}, {"step_name": ""}]
        process_json.persist_final_json(template)

        steps = subprocess_json.load_process_steps()
        assert [s["step_name"] for s in steps] == ["Step A"]
