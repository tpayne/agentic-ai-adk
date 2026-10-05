from coded_tools.cloudarch.cloudarch_layout_engine import build_structured_drawio_xml
from coded_tools.common.drawio_persistence import load_drawio_xml, save_drawio_xml


def test_load_without_a_prior_save_returns_not_found():
    assert load_drawio_xml() == {"status": "NOT_FOUND", "xml": None}


def test_save_then_load_round_trips():
    xml = build_structured_drawio_xml(
        title="Test Architecture", subtitle=None,
        zones=[{"id": "edge", "label": "Edge"}],
        components=[{"id": "waf", "zone_id": "edge", "label": "WAF", "color": "#DD344C"}],
        edges=[],
    )
    result = save_drawio_xml(xml)
    assert result["status"] == "OK"

    loaded = load_drawio_xml()
    assert loaded["status"] == "OK"
    assert "WAF" in loaded["xml"]


def test_rejects_malformed_xml():
    result = save_drawio_xml("<not valid xml")
    assert result["status"] == "ERROR"


def test_unchanged_save_is_a_no_op():
    xml = build_structured_drawio_xml(
        title="T", subtitle=None, zones=[{"id": "z", "label": "Z"}],
        components=[{"id": "c", "zone_id": "z", "label": "C"}], edges=[],
    )
    save_drawio_xml(xml)
    second = save_drawio_xml(xml)
    assert "unchanged" in second["message"]
