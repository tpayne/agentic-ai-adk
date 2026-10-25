import pytest

from process_toolkit import paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway output/ directory, so tests never
    read or write the real project's output/ files and never leak state
    between tests. No test here calls paths.use_session(), so this is
    the ONLY output-path global in play -- every coded_tool and cli.py
    route ultimately resolves through this same process_toolkit.paths
    module (the former second, independent coded_tools/common/paths.py
    copy was retired once multi-session support made keeping two
    implementations in sync a real liability, not just duplication)."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path
