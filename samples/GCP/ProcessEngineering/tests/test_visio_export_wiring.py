"""Regression coverage for the two standalone Visio-export agents
(Visio_Export_Agent, Cloudarch_Visio_Export_Agent), mirroring
test_cloudarch_iac_wiring.py's own style -- these never run a live LLM
call, just lock in root_agent registration, router instructions, and the
real tool-function round trip through process_interface.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# process_agents.common.agent validates model-provider credentials at
# import time -- same convention as test_cloudarch_iac_wiring.py.
os.environ.setdefault("GOOGLE_API_KEY", "test-key-unused")


def test_both_visio_export_agents_are_registered_on_root_agent():
    from process_agents.common.agent import root_agent

    names = [a.name for a in root_agent.sub_agents]
    assert "Visio_Export_Agent" in names
    assert "Cloudarch_Visio_Export_Agent" in names


def test_router_references_the_visio_export_section():
    router_text = (PROJECT_ROOT / "instructions" / "common" / "agent.txt").read_text(encoding="utf-8")
    assert "VISIO (.vsdx) EXPORT" in router_text
    assert "Visio_Export_Agent" in router_text
    assert "Cloudarch_Visio_Export_Agent" in router_text


def test_export_process_design_vsdx_exports_the_start_end_fallback():
    from process_agents.common.visio_export_agent import export_process_design_vsdx

    result = export_process_design_vsdx("process")
    assert result.startswith("Visio diagram successfully exported to "), result


def test_export_cloudarch_vsdx_errors_cleanly_with_nothing_saved():
    from process_agents.common.visio_export_agent import export_cloudarch_vsdx

    assert export_cloudarch_vsdx().startswith("ERROR:")


def test_visio_export_download_routes_registered():
    from process_agents.common.agent import build_web_app

    web_app = build_web_app(https=False)
    rules = {rule.rule for rule in web_app.url_map.iter_rules()}
    assert "/artifacts/process_flow_vsdx/download" in rules
    assert "/artifacts/design_flow_vsdx/download" in rules
    assert "/artifacts/cloudarch_vsdx/download" in rules
