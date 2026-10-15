import json
import time

from coded_tools.cloudarch.load_master_process_json_tool import LoadMasterProcessJsonCodedTool
from process_toolkit import paths


def _write(filename: str, content: dict) -> None:
    with open(paths.output_path(filename), "w", encoding="utf-8") as f:
        json.dump(content, f)


def test_returns_empty_dict_when_nothing_exists():
    assert LoadMasterProcessJsonCodedTool().invoke({}, {}) == {}


def test_with_no_schema_type_prefers_the_more_recently_modified_file():
    # Regression test: when both a process and a design document exist,
    # this must not silently always prefer one -- CloudArch's own
    # narrative-context/risk-gathering callers would otherwise ground
    # against the wrong document.
    _write("process_data.json", {"process_name": "Onboarding"})
    time.sleep(0.01)
    _write("design_data.json", {"document_metadata": {"title": "Payments HLD"}})

    assert LoadMasterProcessJsonCodedTool().invoke({}, {}) == {"document_metadata": {"title": "Payments HLD"}}


def test_explicit_schema_type_is_honored_over_auto_detection():
    _write("process_data.json", {"process_name": "Onboarding"})
    time.sleep(0.01)
    _write("design_data.json", {"document_metadata": {"title": "Payments HLD"}})

    assert LoadMasterProcessJsonCodedTool().invoke({"schema_type": "process"}, {}) == {"process_name": "Onboarding"}
