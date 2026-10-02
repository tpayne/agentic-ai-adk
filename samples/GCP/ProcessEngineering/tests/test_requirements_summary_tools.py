import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _install_google_stubs():
    """Make the utility module importable without installing the ADK runtime."""
    if "google.adk.models" in sys.modules:
        return

    google = types.ModuleType("google")
    adk = types.ModuleType("google.adk")
    models = types.ModuleType("google.adk.models")
    agents = types.ModuleType("google.adk.agents")
    callback_context = types.ModuleType("google.adk.agents.callback_context")
    tools = types.ModuleType("google.adk.tools")
    tool_context = types.ModuleType("google.adk.tools.tool_context")

    class LlmRequest:
        pass

    class LlmResponse:
        pass

    class CallbackContext:
        pass

    class ToolContext:
        pass

    models.LlmRequest = LlmRequest
    models.LlmResponse = LlmResponse
    callback_context.CallbackContext = CallbackContext
    tool_context.ToolContext = ToolContext
    agents.callback_context = callback_context
    tools.tool_context = tool_context
    adk.models = models
    adk.agents = agents
    adk.tools = tools
    google.adk = adk

    sys.modules.update(
        {
            "google": google,
            "google.adk": adk,
            "google.adk.models": models,
            "google.adk.agents": agents,
            "google.adk.agents.callback_context": callback_context,
            "google.adk.tools": tools,
            "google.adk.tools.tool_context": tool_context,
        }
    )


_install_google_stubs()
from process_agents.common import utils  # noqa: E402


class RequirementsSummaryToolsTests(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = patch.object(utils, "_safe_sleep_from_property")
        self.sleep_patch.start()
        self.log_patch = patch.object(utils, "_log_agent_activity")
        self.log_patch.start()
        self.addCleanup(self.sleep_patch.stop)
        self.addCleanup(self.log_patch.stop)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root_patch = patch.object(utils, "PROJECT_ROOT", self.temp_dir.name)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_load_without_a_prior_save_returns_not_found(self):
        result = utils.load_requirements_summary()
        self.assertEqual(result, {"status": "NOT_FOUND"})

    def test_save_then_load_round_trips_the_summary(self):
        summary = {
            "source_directory": "./vendor-docs",
            "source_files": ["notes.txt"],
            "summary": "Vendor onboarding requires KYC checks.",
            "stakeholders": ["Procurement Lead"],
            "functional_requirements": ["Run KYC checks within 5 business days"],
        }
        result = utils.save_requirements_summary(summary)
        self.assertTrue(result.startswith("SUCCESS:"))

        saved_path = Path(self.temp_dir.name) / "output" / "requirements_summary.json"
        on_disk = json.loads(saved_path.read_text())
        self.assertEqual(on_disk, summary)

        loaded = utils.load_requirements_summary()
        self.assertEqual(loaded["status"], "OK")
        self.assertEqual(loaded["source_directory"], "./vendor-docs")
        self.assertEqual(loaded["stakeholders"], ["Procurement Lead"])

    def test_save_rejects_non_dict_input(self):
        result = utils.save_requirements_summary(["not", "a", "dict"])
        self.assertTrue(result.startswith("ERROR:"))

        saved_path = Path(self.temp_dir.name) / "output" / "requirements_summary.json"
        self.assertFalse(saved_path.exists())

    def test_save_overwrites_a_previously_saved_summary(self):
        utils.save_requirements_summary({"summary": "first"})
        utils.save_requirements_summary({"summary": "second"})

        loaded = utils.load_requirements_summary()
        self.assertEqual(loaded["summary"], "second")

    def test_load_returns_error_status_on_corrupt_json(self):
        output_dir = Path(self.temp_dir.name) / "output"
        output_dir.mkdir(parents=True)
        (output_dir / "requirements_summary.json").write_text("{not-json")

        result = utils.load_requirements_summary()
        self.assertEqual(result["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
