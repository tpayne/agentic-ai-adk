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
