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


def test_artifact_browser_exposes_itsm_json():
    html = (WEBCLIENT_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    app = (WEBCLIENT_ROOT / "public" / "app.js").read_text(encoding="utf-8")

    assert '<option value="itsm">ITSM JSON</option>' in html
    # No explicit ARTIFACT_FILENAMES entry is expected for "itsm" either -- same reasoning
    # as "togaf" above (itsm_data.json already follows the default convention).
    assert '"itsm"' in app


def test_diagrams_tab_options_and_labels():
    html = (WEBCLIENT_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    app = (WEBCLIENT_ROOT / "public" / "app.js").read_text(encoding="utf-8")

    # Verify Draw.io label distinction
    assert '<option value="cloudarch" selected>Cloud Architecture (Draw.io)</option>' in html
    assert 'label: "cloud architecture (Draw.io) diagram"' in app

    # Verify all 8 diagram options are present in HTML select
    expected_options = [
        '<option value="cloudarch" selected>Cloud Architecture (Draw.io)</option>',
        '<option value="process_flow_vsdx">Process Flow (Visio)</option>',
        '<option value="design_flow_vsdx">Design Flow (Visio)</option>',
        '<option value="cloudarch_vsdx">Cloud Architecture (Visio)</option>',
        '<option value="portfolio_backlog_project_plan">Portfolio Backlog (Project Plan)</option>',
        '<option value="proposal_response_project_plan">Proposal Response (Project Plan)</option>',
        '<option value="portfolio_backlog_pert_cpm">Portfolio Backlog (PERT/CPM)</option>',
        '<option value="proposal_response_pert_cpm">Proposal Response (PERT/CPM)</option>',
    ]
    for opt in expected_options:
        assert opt in html

    # Verify DIAGRAM_META entries exist for all 8 keys
    for key in (
        "cloudarch", "process_flow_vsdx", "design_flow_vsdx", "cloudarch_vsdx",
        "portfolio_backlog_project_plan", "proposal_response_project_plan",
        "portfolio_backlog_pert_cpm", "proposal_response_pert_cpm",
    ):
        assert f"{key}: {{" in app

