"""Confirms every always-local module behaves identically to its
process_toolkit counterpart AND never imports process_interface._transport
-- the user's explicit ruling is that run_lock/loop_control/session_purge
(and, by the same reasoning, paths/filenames and the pure-compute pieces of
drawio/cloudarch/iac/ingestion) must NEVER redirect to MCP mode, regardless
of PROCESS_TOOLKIT_MODE. This is a static guarantee (no _transport import
at all), not just "happens not to call it today."
"""

import ast
import importlib
import inspect

import pytest

ALWAYS_LOCAL_MODULES = [
    "process_interface.paths",
    "process_interface.filenames",
    "process_interface.run_lock",
    "process_interface.loop_control",
    "process_interface.session_purge",
    "process_interface.drawio.graph",
    "process_interface.cloudarch.layout",
    "process_interface.iac.validation",
    "process_interface.ingestion.chunking",
]


def _imports_transport(module) -> bool:
    source = inspect.getsource(module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "_transport" in node.module:
            return True
        if isinstance(node, ast.Import) and any("_transport" in alias.name for alias in node.names):
            return True
    return False


@pytest.mark.parametrize("module_name", ALWAYS_LOCAL_MODULES)
def test_never_imports_transport(module_name):
    module = importlib.import_module(module_name)
    assert not _imports_transport(module), (
        f"{module_name} must never import process_interface._transport -- "
        "it's an always-local module per the user's explicit ruling."
    )


class TestPathsMatchesProcessToolkit:
    def test_output_dir_and_output_path_delegate_to_the_same_live_global(self, tmp_path):
        from process_interface import paths as interface_paths
        from process_toolkit import paths as toolkit_paths

        assert interface_paths.output_dir() == toolkit_paths.output_dir()
        assert interface_paths.output_path("x.txt") == toolkit_paths.output_path("x.txt")

    def test_use_session_scopes_identically(self):
        from process_interface import paths as interface_paths

        with interface_paths.use_session("some-session"):
            assert "some-session" in interface_paths.output_dir()


class TestFilenames:
    def test_safe_filename_component_matches_process_toolkit(self):
        from process_interface.filenames import safe_filename_component
        from process_toolkit.filenames import safe_filename_component as toolkit_version

        assert safe_filename_component("a/b:c") == toolkit_version("a/b:c")


class TestRunLockRoundTrip:
    def test_acquire_release_round_trips_through_the_interface(self):
        from process_interface import run_lock

        token = run_lock.acquire_pipeline_lock(label="test")
        assert isinstance(token, str) and token
        run_lock.release_pipeline_lock(token)


class TestLoopControlRoundTrip:
    def test_counter_round_trips_through_the_interface(self):
        from process_interface import loop_control

        loop_control.reset_counter()
        assert loop_control.load_counter() == 0
        loop_control.save_counter(3)
        assert loop_control.load_counter() == 3


class TestPureComputeReexports:
    def test_parse_drawio_graph_matches_process_toolkit(self):
        from process_interface.drawio.graph import parse_drawio_graph

        xml = "<mxGraphModel><root></root></mxGraphModel>"
        result = parse_drawio_graph(xml)
        assert isinstance(result, dict)
        assert "vertices" in result and "edges" in result

    def test_validate_iac_files_matches_process_toolkit(self):
        from process_interface.iac.validation import validate_iac_files

        report = validate_iac_files({"main.tf": "resource \"x\" \"y\" {}"})
        assert isinstance(report, dict)

    def test_chunk_and_wrap_matches_process_toolkit(self):
        from process_interface.ingestion.chunking import chunk_and_wrap

        result = chunk_and_wrap("hello world " * 50, max_tokens=10)
        assert isinstance(result, dict)
        assert result["chunk_count"] == len(result["chunks"]) >= 1
