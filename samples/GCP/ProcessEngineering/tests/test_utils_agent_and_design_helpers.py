import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from test_grounding_agent import _install_dependency_stubs

_install_dependency_stubs()

if "pydantic" not in sys.modules:
    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = type("BaseModel", (), {})
    pydantic.Field = lambda default=None, **kwargs: default
    sys.modules["pydantic"] = pydantic

from process_agents.common import utils_agent  # noqa: E402

try:
    from process_agents.common.helpers import doc_design_sections  # noqa: E402
except ModuleNotFoundError as error:
    if error.name != "docx":
        raise
    doc_design_sections = None


class UtilsAgentTests(unittest.TestCase):
    def test_contains_marker_walks_nested_structures(self):
        with patch.object(utils_agent.time, "sleep"):
            self.assertTrue(
                utils_agent._contains_marker(
                    {"items": ["safe", {"message": "JSON APPROVED"}]},
                    "approved",
                )
            )
            self.assertFalse(utils_agent._contains_marker(["safe"], "approved"))

    def test_reset_stop_counter_removes_existing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "counter.json")
            Path(path).write_text(json.dumps({"count": 3}))
            utils_agent._reset_stop_counter(path)
            self.assertFalse(Path(path).exists())

    def test_status_logger_reports_current_counter(self):
        with patch.object(utils_agent.time, "sleep"):
            result = utils_agent.status_logger(3)
        self.assertIn("3 identified objectives", result)


@unittest.skipIf(doc_design_sections is None, "python-docx is not installed")
class DesignHelperTests(unittest.TestCase):
    def test_priority_and_natural_sort_keys(self):
        self.assertLess(
            doc_design_sections._priority_sort_key("high"),
            doc_design_sections._priority_sort_key("low"),
        )
        self.assertEqual(
            doc_design_sections._natural_sort_key("Requirement 12"),
            ["requirement ", 12, ""],
        )

    def test_bulleted_group_handles_empty_and_values(self):
        class FakeDoc:
            def __init__(self):
                self.paragraphs = []
                self.runs = []

            def add_paragraph(self, text="", style=None):
                self.paragraphs.append((text, style))

                def add_run(run_text="", **kwargs):
                    self.runs.append(run_text)
                    return types.SimpleNamespace(bold=None)

                return types.SimpleNamespace(
                    paragraph_format=types.SimpleNamespace(
                        left_indent=None, space_before=None, space_after=None
                    ),
                    add_run=add_run,
                )

        doc = FakeDoc()
        doc_design_sections._add_bulleted_group(doc, "Controls", ["one", "two"], 0.25)
        self.assertTrue(doc.paragraphs)
        self.assertEqual(doc.runs[0], "Controls:")


if __name__ == "__main__":
    unittest.main()
