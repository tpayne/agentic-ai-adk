from pathlib import Path


WEBCLIENT_ROOT = Path(__file__).resolve().parents[1]


def test_artifact_browser_exposes_test_specification_and_backlog_json():
    html = (WEBCLIENT_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    app = (WEBCLIENT_ROOT / "public" / "app.js").read_text(encoding="utf-8")

    assert '<option value="test_specification">Test Specification JSON</option>' in html
    assert '<option value="portfolio_backlog">Portfolio Backlog JSON</option>' in html
    assert '"test_specification"' in app
    assert '"portfolio_backlog"' in app
    assert 'test_specification: "test_specification.json"' in app
    assert 'portfolio_backlog: "portfolio_backlog.json"' in app


def test_artifact_browser_exposes_togaf_json():
    html = (WEBCLIENT_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    app = (WEBCLIENT_ROOT / "public" / "app.js").read_text(encoding="utf-8")

    assert '<option value="togaf">TOGAF JSON</option>' in html
    # No explicit ARTIFACT_FILENAMES entry is expected for "togaf" -- its real filename
    # (togaf_data.json) already follows the "<artifact>_data.json" convention the download
    # helper falls back to, the same reason "process"/"design" have no entry either.
    assert '"togaf"' in app
