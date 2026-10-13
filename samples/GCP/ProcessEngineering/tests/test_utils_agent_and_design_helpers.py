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

    def test_stop_if_ready_recognizes_approval_on_final_iteration(self):
        # Regression test: the approval-state check must run BEFORE the
        # max-iteration check. The reviewer's own turn (which writes
        # approval.json) always runs immediately before this tool call
        # within the same loop iteration, so a genuine approval and "this
        # is the last allowed iteration" can both be true at once -- if the
        # max-iteration check fired first, a real last-iteration approval
        # was reported as "exhausted" instead of "approved" (confirmed from
        # a real run's log).
        cloudarch_stop_if_ready = utils_agent._build_stop_if_ready(
            lambda: {"cloudarch_status": "APPROVED"}
        )
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "stop_counter.json").write_text(
                json.dumps({"count": 1})  # about to become 2/2 -- the last allowed iteration
            )
            (Path(directory) / "approval.json").write_text(
                json.dumps({"cloudarch_status": "APPROVED"})
            )
            tool_context = types.SimpleNamespace(
                actions=types.SimpleNamespace(escalate=False)
            )
            from process_toolkit import paths as shared_paths
            with patch.object(shared_paths, "OUTPUT_DIR", directory):
                result = cloudarch_stop_if_ready(tool_context)

        self.assertEqual(result, "All approvals present — exiting loop.")
        self.assertTrue(tool_context.actions.escalate)


if __name__ == "__main__":
    unittest.main()
