"""Regression coverage for coded_tools/common/artifact_downloads.py --
shared resolution/copy logic behind both cli.py's own "list"/"download"
control lines and DownloadArtifactCodedTool's LLM-invokable path."""

import os

import pytest

from coded_tools.common.artifact_downloads import (
    copy_artifact_to_destination,
    list_output_documents,
    resolve_artifact_target,
    safe_output_file_path,
)
from process_toolkit import paths


def _write_output_file(name: str, content: bytes = b"content") -> str:
    path = os.path.join(paths.output_dir(), name)
    with open(path, "wb") as f:
        f.write(content)
    return path


class TestListOutputDocuments:
    def test_empty_output_dir_returns_empty_list(self):
        assert list_output_documents() == []

    def test_only_docx_files_are_listed(self):
        _write_output_file("Vendor_Onboarding.docx")
        _write_output_file("process_data.json")
        _write_output_file("cloudarch_drawio.xml")
        docs = list_output_documents()
        assert [d["filename"] for d in docs] == ["Vendor_Onboarding.docx"]

    def test_reports_real_size(self):
        _write_output_file("Vendor_Onboarding.docx", b"0123456789")
        docs = list_output_documents()
        assert docs[0]["size_bytes"] == 10

    def test_sorted_most_recently_modified_first(self):
        old_path = _write_output_file("Older.docx")
        new_path = _write_output_file("Newer.docx")
        # Force a real mtime gap -- same-second writes could otherwise
        # tie, leaving the sort order coincidental rather than proven.
        os.utime(old_path, (1000, 1000))
        os.utime(new_path, (2000, 2000))
        docs = list_output_documents()
        assert [d["filename"] for d in docs] == ["Newer.docx", "Older.docx"]


class TestSafeOutputFilePath:
    def test_resolves_a_real_file(self):
        _write_output_file("Vendor_Onboarding.docx")
        resolved = safe_output_file_path("Vendor_Onboarding.docx")
        assert resolved is not None
        assert os.path.isfile(resolved)

    def test_none_for_a_missing_file(self):
        assert safe_output_file_path("nope.docx") is None

    def test_none_for_empty_filename(self):
        assert safe_output_file_path("") is None
        assert safe_output_file_path(None) is None

    def test_path_traversal_attempt_is_rejected(self, tmp_path):
        secret = os.path.join(os.path.dirname(paths.output_dir()), "secret.txt")
        with open(secret, "w", encoding="utf-8") as f:
            f.write("do not leak me")
        assert safe_output_file_path("../secret.txt") is None
        # basename() strips the traversal component entirely -- confirms
        # it doesn't accidentally resolve to a same-named file elsewhere.
        assert safe_output_file_path(os.path.basename(secret)) is None


class TestResolveArtifactTarget:
    def test_cloudarch_keyword_resolves_when_the_diagram_exists(self):
        _write_output_file("cloudarch_drawio.xml")
        for phrase in ("cloudarch", "the cloud architecture DIAGRAM", "Architecture", "export the xml"):
            assert resolve_artifact_target(phrase) == "cloudarch_drawio.xml"

    def test_cloudarch_keyword_resolves_to_none_when_the_diagram_does_not_exist(self):
        assert resolve_artifact_target("diagram") is None

    def test_exact_filename_match(self):
        _write_output_file("Vendor_Onboarding.docx")
        assert resolve_artifact_target("Vendor_Onboarding.docx") == "Vendor_Onboarding.docx"

    def test_case_insensitive_substring_match(self):
        _write_output_file("Vendor_Onboarding.docx")
        assert resolve_artifact_target("onboarding") == "Vendor_Onboarding.docx"

    def test_empty_target_resolves_to_most_recent_document(self):
        old_path = _write_output_file("Older.docx")
        new_path = _write_output_file("Newer.docx")
        os.utime(old_path, (1000, 1000))
        os.utime(new_path, (2000, 2000))
        assert resolve_artifact_target(None) == "Newer.docx"
        assert resolve_artifact_target("") == "Newer.docx"

    def test_empty_target_resolves_to_none_when_nothing_generated(self):
        assert resolve_artifact_target(None) is None

    def test_unmatched_target_returns_none_rather_than_guessing(self):
        _write_output_file("Vendor_Onboarding.docx")
        assert resolve_artifact_target("something totally unrelated") is None


class TestCopyArtifactToDestination:
    def test_copies_into_an_existing_directory_keeping_the_filename(self, tmp_path):
        _write_output_file("Vendor_Onboarding.docx", b"real bytes")
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir()

        result = copy_artifact_to_destination("Vendor_Onboarding.docx", str(dest_dir))

        assert result == str(dest_dir / "Vendor_Onboarding.docx")
        assert (dest_dir / "Vendor_Onboarding.docx").read_bytes() == b"real bytes"

    def test_copies_to_a_full_target_file_path(self, tmp_path):
        _write_output_file("Vendor_Onboarding.docx", b"real bytes")
        dest_file = tmp_path / "renamed.docx"

        result = copy_artifact_to_destination("Vendor_Onboarding.docx", str(dest_file))

        assert result == str(dest_file)
        assert dest_file.read_bytes() == b"real bytes"

    def test_expands_user_home_in_the_destination(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        _write_output_file("Vendor_Onboarding.docx", b"real bytes")
        (tmp_path / "Desktop").mkdir()

        result = copy_artifact_to_destination("Vendor_Onboarding.docx", "~/Desktop")

        assert result == str(tmp_path / "Desktop" / "Vendor_Onboarding.docx")

    def test_raises_value_error_for_an_unknown_filename(self, tmp_path):
        with pytest.raises(ValueError, match="No generated file named"):
            copy_artifact_to_destination("nope.docx", str(tmp_path))

    def test_raises_for_a_path_traversal_attempt(self, tmp_path):
        with pytest.raises(ValueError):
            copy_artifact_to_destination("../../etc/passwd", str(tmp_path))
