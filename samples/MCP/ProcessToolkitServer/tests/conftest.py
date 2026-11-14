import pytest

from process_toolkit import paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway output directory -- mirrors
    process_toolkit's own tests/conftest.py and both agent apps' identical
    fixture, so this new server's tests never touch a real output/ dir."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path
