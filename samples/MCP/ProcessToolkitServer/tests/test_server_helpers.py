"""Unit tests for server.py's internal helpers, called directly as plain
Python functions -- never through an MCP client/transport (that full-stack
coverage, including these same helpers wired into real tools, lives in
test_server.py).
"""

import base64
import os

import pytest
from fastmcp.exceptions import ToolError

import server


class TestDomainOrError:
    def test_returns_the_matching_domain_ops(self):
        ops = server._domain_or_error("togaf")
        assert ops is server.dispatch.DOMAINS["togaf"]

    def test_raises_a_tool_error_naming_the_valid_schema_types(self):
        with pytest.raises(ToolError, match="Unknown schema_type 'bogus'"):
            server._domain_or_error("bogus")


class TestSession:
    def test_none_session_id_is_a_no_op_context_manager(self):
        with server._session(None):
            pass  # must not raise

    def test_a_safe_session_id_is_accepted(self):
        with server._session("my-session_1"):
            pass  # must not raise

    def test_an_unsafe_session_id_raises_a_tool_error_not_a_raw_value_error(self):
        with pytest.raises(ToolError):
            with server._session("../escape"):
                pass


class TestSnapshotAndDiffMtimes:
    def test_snapshot_only_includes_files_matching_the_suffix(self, tmp_path):
        (tmp_path / "a.docx").write_text("x")
        (tmp_path / "b.png").write_text("x")
        snapshot = server._snapshot_mtimes(str(tmp_path), ".docx")
        assert set(snapshot) == {"a.docx"}

    def test_snapshot_of_a_missing_directory_is_empty(self, tmp_path):
        assert server._snapshot_mtimes(str(tmp_path / "nope"), ".docx") == {}

    def test_new_or_changed_detects_a_brand_new_file(self, tmp_path):
        before = server._snapshot_mtimes(str(tmp_path), ".docx")
        (tmp_path / "new.docx").write_text("x")
        changed = server._new_or_changed(before, str(tmp_path), ".docx")
        assert changed == ["new.docx"]

    def test_new_or_changed_detects_a_modified_file_via_mtime(self, tmp_path):
        path = tmp_path / "existing.docx"
        path.write_text("x")
        before = server._snapshot_mtimes(str(tmp_path), ".docx")
        os.utime(path, (before["existing.docx"] + 10, before["existing.docx"] + 10))
        changed = server._new_or_changed(before, str(tmp_path), ".docx")
        assert changed == ["existing.docx"]

    def test_new_or_changed_ignores_untouched_files(self, tmp_path):
        (tmp_path / "untouched.docx").write_text("x")
        before = server._snapshot_mtimes(str(tmp_path), ".docx")
        assert server._new_or_changed(before, str(tmp_path), ".docx") == []


class TestEncodeFile:
    def test_round_trips_real_bytes_through_base64(self, tmp_path):
        path = tmp_path / "artifact.bin"
        path.write_bytes(b"\x00\x01real bytes\xff")
        encoded = server._encode_file(str(path))
        assert encoded["filename"] == "artifact.bin"
        assert encoded["size_bytes"] == len(b"\x00\x01real bytes\xff")
        assert base64.b64decode(encoded["base64"]) == b"\x00\x01real bytes\xff"


class TestSafeArtifactPath:
    def test_resolves_a_real_file_in_the_current_session_output_dir(self, tmp_path):
        (tmp_path / "report.docx").write_text("x")
        resolved = server._safe_artifact_path("report.docx")
        assert resolved == str(tmp_path / "report.docx")

    def test_rejects_a_path_traversal_attempt(self, tmp_path):
        secret_dir = tmp_path.parent / "secret_sibling"
        secret_dir.mkdir(exist_ok=True)
        (secret_dir / "secret.txt").write_text("do not leak me")
        with pytest.raises(ToolError, match="No such artifact"):
            server._safe_artifact_path("../secret_sibling/secret.txt")

    def test_rejects_an_empty_filename(self, tmp_path):
        with pytest.raises(ToolError, match="No such artifact"):
            server._safe_artifact_path("")

    def test_rejects_a_filename_that_does_not_exist(self, tmp_path):
        with pytest.raises(ToolError, match="No such artifact"):
            server._safe_artifact_path("nope.docx")
