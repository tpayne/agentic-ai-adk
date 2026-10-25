"""Regression coverage for process_agents/common/artifact_downloads.py --
shared resolution/copy logic behind both agent.py's own "list"/"download"
control lines and the LLM-invokable download_artifact tool. Developed in
tandem with the neuro-san port's own
tests/test_artifact_downloads.py."""

import os

import pytest

from process_agents.common import artifact_downloads


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """artifact_downloads.PROJECT_ROOT (not process_toolkit.paths'
    OUTPUT_DIR) drives every path in this module -- see its own docstring
    for why it computes this independently rather than importing it from
    .utils_agent. Isolated the same way test_pipeline_lock_wiring.py
    isolates process_toolkit's own OUTPUT_DIR: per-file, not via a shared
    conftest.py (this project has none)."""
    monkeypatch.setattr(artifact_downloads, "PROJECT_ROOT", str(tmp_path))
    yield tmp_path


def _write_output_file(name: str, content: bytes = b"content") -> str:
    output_dir = os.path.join(artifact_downloads.PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, name)
    with open(path, "wb") as f:
        f.write(content)
    return path


class TestListOutputDocuments:
    def test_empty_output_dir_returns_empty_list(self):
        assert artifact_downloads.list_output_documents() == []

    def test_only_docx_files_are_listed(self):
        _write_output_file("Vendor_Onboarding.docx")
        _write_output_file("process_data.json")
        _write_output_file("cloudarch_drawio.xml")
        docs = artifact_downloads.list_output_documents()
        assert [d["filename"] for d in docs] == ["Vendor_Onboarding.docx"]

    def test_reports_real_size(self):
        _write_output_file("Vendor_Onboarding.docx", b"0123456789")
        docs = artifact_downloads.list_output_documents()
        assert docs[0]["size_bytes"] == 10

    def test_sorted_most_recently_modified_first(self):
        old_path = _write_output_file("Older.docx")
        new_path = _write_output_file("Newer.docx")
        os.utime(old_path, (1000, 1000))
        os.utime(new_path, (2000, 2000))
        docs = artifact_downloads.list_output_documents()
        assert [d["filename"] for d in docs] == ["Newer.docx", "Older.docx"]


class TestSafeOutputFilePath:
    def test_resolves_a_real_file(self):
        _write_output_file("Vendor_Onboarding.docx")
        resolved = artifact_downloads.safe_output_file_path("Vendor_Onboarding.docx")
        assert resolved is not None
        assert os.path.isfile(resolved)

    def test_none_for_a_missing_file(self):
        assert artifact_downloads.safe_output_file_path("nope.docx") is None

    def test_none_for_empty_filename(self):
        assert artifact_downloads.safe_output_file_path("") is None
        assert artifact_downloads.safe_output_file_path(None) is None

    def test_path_traversal_attempt_is_rejected(self, tmp_path):
        secret = os.path.join(tmp_path, "secret.txt")
        with open(secret, "w", encoding="utf-8") as f:
            f.write("do not leak me")
        assert artifact_downloads.safe_output_file_path("../secret.txt") is None
        assert artifact_downloads.safe_output_file_path(os.path.basename(secret)) is None


class TestResolveArtifactTarget:
    def test_cloudarch_keyword_resolves_when_the_diagram_exists(self):
        _write_output_file("cloudarch_drawio.xml")
        for phrase in ("cloudarch", "the cloud architecture DIAGRAM", "Architecture", "export the xml"):
            assert artifact_downloads.resolve_artifact_target(phrase) == "cloudarch_drawio.xml"

    def test_cloudarch_keyword_resolves_to_none_when_the_diagram_does_not_exist(self):
        assert artifact_downloads.resolve_artifact_target("diagram") is None

    def test_exact_filename_match(self):
        _write_output_file("Vendor_Onboarding.docx")
        assert artifact_downloads.resolve_artifact_target("Vendor_Onboarding.docx") == "Vendor_Onboarding.docx"

    def test_case_insensitive_substring_match(self):
        _write_output_file("Vendor_Onboarding.docx")
        assert artifact_downloads.resolve_artifact_target("onboarding") == "Vendor_Onboarding.docx"

    def test_empty_target_resolves_to_most_recent_document(self):
        old_path = _write_output_file("Older.docx")
        new_path = _write_output_file("Newer.docx")
        os.utime(old_path, (1000, 1000))
        os.utime(new_path, (2000, 2000))
        assert artifact_downloads.resolve_artifact_target(None) == "Newer.docx"
        assert artifact_downloads.resolve_artifact_target("") == "Newer.docx"

    def test_empty_target_resolves_to_none_when_nothing_generated(self):
        assert artifact_downloads.resolve_artifact_target(None) is None

    def test_unmatched_target_returns_none_rather_than_guessing(self):
        _write_output_file("Vendor_Onboarding.docx")
        assert artifact_downloads.resolve_artifact_target("something totally unrelated") is None


class TestCloudarchDiagramExists:
    def test_false_when_not_generated(self):
        assert artifact_downloads.cloudarch_diagram_exists() is False

    def test_true_once_generated(self):
        _write_output_file("cloudarch_drawio.xml")
        assert artifact_downloads.cloudarch_diagram_exists() is True


class TestCopyArtifactToDestination:
    def test_copies_into_an_existing_directory_keeping_the_filename(self, tmp_path):
        _write_output_file("Vendor_Onboarding.docx", b"real bytes")
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir()

        result = artifact_downloads.copy_artifact_to_destination("Vendor_Onboarding.docx", str(dest_dir))

        assert result == str(dest_dir / "Vendor_Onboarding.docx")
        assert (dest_dir / "Vendor_Onboarding.docx").read_bytes() == b"real bytes"

    def test_copies_to_a_full_target_file_path(self, tmp_path):
        _write_output_file("Vendor_Onboarding.docx", b"real bytes")
        dest_file = tmp_path / "renamed.docx"

        result = artifact_downloads.copy_artifact_to_destination("Vendor_Onboarding.docx", str(dest_file))

        assert result == str(dest_file)
        assert dest_file.read_bytes() == b"real bytes"

    def test_expands_user_home_in_the_destination(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        _write_output_file("Vendor_Onboarding.docx", b"real bytes")
        (tmp_path / "Desktop").mkdir()

        result = artifact_downloads.copy_artifact_to_destination("Vendor_Onboarding.docx", "~/Desktop")

        assert result == str(tmp_path / "Desktop" / "Vendor_Onboarding.docx")

    def test_raises_value_error_for_an_unknown_filename(self, tmp_path):
        with pytest.raises(ValueError, match="No generated file named"):
            artifact_downloads.copy_artifact_to_destination("nope.docx", str(tmp_path))

    def test_raises_for_a_path_traversal_attempt(self, tmp_path):
        with pytest.raises(ValueError):
            artifact_downloads.copy_artifact_to_destination("../../etc/passwd", str(tmp_path))
