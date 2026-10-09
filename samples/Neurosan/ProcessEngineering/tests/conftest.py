import pytest

from coded_tools.common import paths
from process_toolkit import paths as shared_paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway output/ directory, so tests never
    read or write the real project's output/ files and never leak state
    between tests. Also isolates process_toolkit's own output-path
    resolution (used by the shared docgen/diagram functions), which is a
    separate module with its own OUTPUT_DIR."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(shared_paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path
