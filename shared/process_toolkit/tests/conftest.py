import pytest

from process_toolkit import paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway output/ directory, so tests never
    read or write the real repo's output/ files and never leak state
    between tests."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path
