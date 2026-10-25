"""Regression coverage for the Process_Architect_Orchestrator's own
download_artifact tool (process_agents/common/utils_agent.py) -- the
LLM-invokable "download the cloud architecture diagram to /tmp" path.
Developed in tandem with the neuro-san port's own
tests/test_download_artifact_tool.py."""

import os

import pytest

from process_agents.common import artifact_downloads
from process_agents.common.utils_agent import download_artifact


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact_downloads, "PROJECT_ROOT", str(tmp_path))
    yield tmp_path


def _write_output_file(name: str, content: bytes = b"content") -> None:
    output_dir = os.path.join(artifact_downloads.PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, name), "wb") as f:
        f.write(content)


@pytest.fixture
def dest_dir(tmp_path):
    # Distinct from tmp_path itself, which the autouse fixture above
    # already points PROJECT_ROOT at -- using tmp_path directly as a
    # download destination would make source and destination the same
    # directory (shutil.copy2 raising SameFileError).
    path = tmp_path / "downloads"
    path.mkdir()
    return path


def test_requires_a_destination():
    result = download_artifact(target="diagram", destination="")
    assert result.startswith("ERROR:")
    assert "destination" in result.lower()


def test_downloads_the_cloudarch_diagram_by_keyword(dest_dir):
    _write_output_file("cloudarch_drawio.xml", b"<mxfile></mxfile>")

    result = download_artifact(target="the cloud architecture diagram", destination=str(dest_dir))

    assert result.startswith("SUCCESS:")
    assert "cloudarch_drawio.xml" in result
    assert (dest_dir / "cloudarch_drawio.xml").read_bytes() == b"<mxfile></mxfile>"


def test_downloads_the_most_recent_document_when_target_is_omitted(dest_dir):
    _write_output_file("Vendor_Onboarding.docx", b"doc bytes")

    result = download_artifact(target="", destination=str(dest_dir))

    assert result.startswith("SUCCESS:")
    assert (dest_dir / "Vendor_Onboarding.docx").read_bytes() == b"doc bytes"


def test_reports_what_is_available_when_target_does_not_match(dest_dir):
    _write_output_file("Vendor_Onboarding.docx")
    _write_output_file("cloudarch_drawio.xml")

    result = download_artifact(target="something unrelated", destination=str(dest_dir))

    assert result.startswith("ERROR:")
    assert "Vendor_Onboarding.docx" in result
    assert "cloud architecture diagram" in result


def test_reports_nothing_generated_yet_when_output_is_empty(dest_dir):
    result = download_artifact(target="", destination=str(dest_dir))
    assert result.startswith("ERROR:")
    assert "nothing has been generated yet" in result


def test_reports_an_error_for_an_unwritable_destination(dest_dir):
    _write_output_file("Vendor_Onboarding.docx")
    bogus_dest = dest_dir / "does" / "not" / "exist" / "out.docx"

    result = download_artifact(target="Vendor_Onboarding.docx", destination=str(bogus_dest))

    assert result.startswith("ERROR:")
    assert "Vendor_Onboarding.docx" in result
