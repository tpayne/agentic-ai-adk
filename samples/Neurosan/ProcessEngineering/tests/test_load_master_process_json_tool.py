import json
import time

from coded_tools.cloudarch.load_master_process_json_tool import LoadMasterProcessJsonCodedTool
from process_toolkit import paths


def _write(filename: str, content: dict) -> None:
    with open(paths.output_path(filename), "w", encoding="utf-8") as f:
        json.dump(content, f)


def test_returns_empty_dict_when_nothing_exists():
    assert LoadMasterProcessJsonCodedTool().invoke({}, {}) == {}


def test_with_no_schema_type_always_defaults_to_design_regardless_of_mtime():
    # Regression test: this used to auto-detect by "whichever file was
    # modified most recently" -- which silently grounded a cloud-
    # architecture answer in an unrelated, more-recently-touched PROCESS
    # document whenever one happened to exist. Pinned to "design" by
    # default instead (confirmed directly: every real caller of this
    # class is cloudarch-family, which only ever means the design
    # document) -- process_data.json being the more recent file here must
    # NOT change the result.
    _write("design_data.json", {"document_metadata": {"title": "Payments HLD"}})
    time.sleep(0.01)
    _write("process_data.json", {"process_name": "Onboarding"})

    assert LoadMasterProcessJsonCodedTool().invoke({}, {}) == {"document_metadata": {"title": "Payments HLD"}}


def test_explicit_schema_type_process_is_honored_over_the_design_default():
    _write("process_data.json", {"process_name": "Onboarding"})
    time.sleep(0.01)
    _write("design_data.json", {"document_metadata": {"title": "Payments HLD"}})

    assert LoadMasterProcessJsonCodedTool().invoke({"schema_type": "process"}, {}) == {"process_name": "Onboarding"}
