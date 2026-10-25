"""Regression coverage for the Process_Architect_Orchestrator's own
download_artifact tool -- the LLM-invokable "download the cloud
architecture diagram to /tmp" path, as opposed to cli.py's own "download"
control line (same underlying coded_tools.common.artifact_downloads, a
different, natural-language-friendly entry point)."""

import asyncio
import os

import pytest

from coded_tools.process_architect.download_artifact_tool import DownloadArtifactCodedTool
from process_toolkit import paths


def _write_output_file(name: str, content: bytes = b"content") -> None:
    with open(os.path.join(paths.output_dir(), name), "wb") as f:
        f.write(content)


@pytest.fixture
def dest_dir(tmp_path):
    # A directory DISTINCT from tmp_path itself -- the autouse
    # isolated_output_dir fixture (conftest.py) already points
    # process_toolkit.paths' own OUTPUT_DIR at this same tmp_path, so
    # using tmp_path directly as a download destination would make
    # source and destination the same directory (shutil.copy2 raising
    # SameFileError, surfaced as a spurious ERROR result).
    path = tmp_path / "downloads"
    path.mkdir()
    return path


def test_requires_a_destination():
    result = DownloadArtifactCodedTool().invoke({"target": "diagram"}, {})
    assert result["status"] == "ERROR"
    assert "destination" in result["message"].lower()


def test_downloads_the_cloudarch_diagram_by_keyword(dest_dir):
    _write_output_file("cloudarch_drawio.xml", b"<mxfile></mxfile>")

    result = DownloadArtifactCodedTool().invoke(
        {"target": "the cloud architecture diagram", "destination": str(dest_dir)}, {},
    )

    assert result["status"] == "OK"
    assert result["filename"] == "cloudarch_drawio.xml"
    assert (dest_dir / "cloudarch_drawio.xml").read_bytes() == b"<mxfile></mxfile>"


def test_downloads_the_most_recent_document_when_target_is_omitted(dest_dir):
    _write_output_file("Vendor_Onboarding.docx", b"doc bytes")

    result = DownloadArtifactCodedTool().invoke({"destination": str(dest_dir)}, {})

    assert result["status"] == "OK"
    assert result["filename"] == "Vendor_Onboarding.docx"
    assert (dest_dir / "Vendor_Onboarding.docx").read_bytes() == b"doc bytes"


def test_reports_what_is_available_when_target_does_not_match(dest_dir):
    _write_output_file("Vendor_Onboarding.docx")
    _write_output_file("cloudarch_drawio.xml")

    result = DownloadArtifactCodedTool().invoke(
        {"target": "something unrelated", "destination": str(dest_dir)}, {},
    )

    assert result["status"] == "ERROR"
    assert "Vendor_Onboarding.docx" in result["message"]
    assert "cloud architecture diagram" in result["message"]


def test_reports_nothing_generated_yet_when_output_is_empty(dest_dir):
    result = DownloadArtifactCodedTool().invoke({"destination": str(dest_dir)}, {})
    assert result["status"] == "ERROR"
    assert "nothing has been generated yet" in result["message"]


def test_reports_an_error_for_an_unwritable_destination(dest_dir):
    _write_output_file("Vendor_Onboarding.docx")
    bogus_dest = dest_dir / "does" / "not" / "exist" / "out.docx"

    result = DownloadArtifactCodedTool().invoke(
        {"target": "Vendor_Onboarding.docx", "destination": str(bogus_dest)}, {},
    )

    assert result["status"] == "ERROR"
    assert "Vendor_Onboarding.docx" in result["message"]


def test_async_invoke_delegates_to_invoke(dest_dir):
    _write_output_file("Vendor_Onboarding.docx", b"doc bytes")

    result = asyncio.run(
        DownloadArtifactCodedTool().async_invoke(
            {"target": "Vendor_Onboarding.docx", "destination": str(dest_dir)}, {},
        )
    )

    assert result["status"] == "OK"
    assert (dest_dir / "Vendor_Onboarding.docx").read_bytes() == b"doc bytes"
