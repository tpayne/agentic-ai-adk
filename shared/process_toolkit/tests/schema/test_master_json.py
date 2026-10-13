import json
import os
import time

from process_toolkit import paths
from process_toolkit.schema.master_json import load_master_json


def _write(filename: str, content: dict) -> None:
    path = paths.output_path(filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f)


def test_returns_empty_dict_when_nothing_exists():
    assert load_master_json() == {}


def test_loads_the_only_file_that_exists():
    _write("process_data.json", {"process_name": "Onboarding"})
    assert load_master_json() == {"process_name": "Onboarding"}


def test_explicit_schema_type_loads_exactly_that_file_even_if_the_other_is_newer():
    # Regression test: an explicit schema_type must not be overridden by
    # auto-detection, even when the OTHER file is more recently modified --
    # a caller that already knows which document it wants (e.g. the
    # diagram's own provenance) must get exactly that one.
    _write("process_data.json", {"process_name": "Onboarding"})
    time.sleep(0.01)
    _write("design_data.json", {"document_metadata": {"title": "Payments HLD"}})

    assert load_master_json(schema_type="process") == {"process_name": "Onboarding"}
    assert load_master_json(schema_type="design") == {"document_metadata": {"title": "Payments HLD"}}


def test_explicit_schema_type_returns_empty_dict_when_that_file_is_missing():
    _write("process_data.json", {"process_name": "Onboarding"})
    assert load_master_json(schema_type="design") == {}


def test_auto_detect_prefers_the_more_recently_modified_file_when_both_exist():
    # Regression test: when both process_data.json and design_data.json
    # exist, auto-detection must not silently always prefer one -- the
    # genuinely more recent document wins instead.
    _write("process_data.json", {"process_name": "Onboarding"})
    time.sleep(0.01)
    _write("design_data.json", {"document_metadata": {"title": "Payments HLD"}})

    assert load_master_json() == {"document_metadata": {"title": "Payments HLD"}}

    # Touch process_data.json again so it's now the newer of the two.
    time.sleep(0.01)
    os.utime(paths.output_path("process_data.json"), None)

    assert load_master_json() == {"process_name": "Onboarding"}
