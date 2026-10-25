import pytest

from process_toolkit import paths


@pytest.fixture(autouse=True)
def isolated_output_dir(tmp_path, monkeypatch):
    """Every test gets its own throwaway output/ directory, so tests never
    read or write the real project's output/ files and never leak state
    between tests. Previously this port had no such fixture at all -- any
    test exercising a function that resolves its own output path (e.g.
    _persist_simulation_metrics, the cloudarch pipeline's reset step,
    SubprocessWriterAgent) wrote into this repo's real output/ directory
    with zero isolation. Mirrors the neuro-san port's own identically-named
    fixture; both ports' production code now resolves exclusively through
    this one process_toolkit.paths.OUTPUT_DIR global (plus, when a web
    session is active via paths.use_session(), a subdirectory under it --
    no test here calls use_session(), so that layer never engages)."""
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    yield tmp_path
