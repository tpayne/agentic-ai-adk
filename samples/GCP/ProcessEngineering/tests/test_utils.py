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


def valid_process():
    top_level = {
        "process_name": "Example",
        "industry_sector": "Technology",
        "version": "1.0",
        "introduction": "Intro",
        "stakeholders": [],
        "process_steps": [],
        "tools_summary": [],
        "metrics": [],
        "critical_success_factors": [],
        "critical_failure_factors": [],
        "reporting_and_analytics": {},
        "system_requirements": [],
        "assumptions": [],
        "constraints": [],
        "appendix": {},
        "purpose": "Purpose",
        "scope": "Scope",
        "process_owner": "Owner",
        "process_triggers": [],
        "process_end_conditions": [],
        "risks_and_controls": [],
        "governance_requirements": [],
        "change_management": {},
        "continuous_improvement": {},
    }
    top_level["process_steps"] = [
        {
            "step_name": "Step one",
            "description": "Do the work",
            "responsible_party": "Team",
            "estimated_duration": 1,
            "deliverables": [],
            "inputs": [],
            "outputs": [],
            "dependencies": [],
            "success_criteria": [],
        }
    ]
    return top_level


class UtilsValidationTests(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = patch.object(utils, "_safe_sleep_from_property")
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def test_extract_json_brace_balanced_handles_nested_object(self):
        value = utils._extract_json_brace_balanced('prefix {"outer": {"inner": 1}} suffix')
        self.assertEqual(json.loads(value), {"outer": {"inner": 1}})

    def test_extract_json_brace_balanced_rejects_missing_or_unbalanced_json(self):
        with self.assertRaises(ValueError):
            utils._extract_json_brace_balanced("no object")
        with self.assertRaises(ValueError):
            utils._extract_json_brace_balanced('{"broken": true')

    def test_validate_process_json_accepts_complete_document(self):
        self.assertEqual(utils._validate_process_json(valid_process()), [])
        self.assertEqual(utils.validate_process_json(valid_process())["valid"], True)

    def test_validate_process_json_reports_missing_and_malformed_steps(self):
        issues = utils._validate_process_json({"process_name": "Incomplete"})
        self.assertTrue(any(issue["location"] == "$.process_steps" for issue in issues))

        document = valid_process()
        document["process_steps"] = [{"step_name": "Incomplete"}]
        issues = utils._validate_process_json(document)
        self.assertTrue(any("responsible_party" in issue["location"] for issue in issues))

    def test_validate_process_json_rejects_non_object(self):
        result = utils.validate_process_json(["not", "an", "object"])
        self.assertFalse(result["valid"])
        self.assertEqual(result["issues"][0]["location"], "$")

    def test_json_equal_is_semantic_and_defensive(self):
        self.assertTrue(utils._json_equal({"b": 2, "a": 1}, {"a": 1, "b": 2}))
        self.assertFalse(utils._json_equal({"a": object()}, {"a": object()}))

    def test_schema_detection_and_safe_filename(self):
        self.assertEqual(
            utils._detect_schema_type({"document_metadata": {}}), "design"
        )
        self.assertEqual(
            utils._detect_schema_type({"process_name": "Example"}), "process"
        )
        self.assertEqual(
            utils.safe_filename_component("A/B: C?.doc"),
            "A_B__C_.doc",
        )

    def test_design_validator_enforces_document_type_sections(self):
        base = {
            "document_metadata": {
                "document_id": "D1",
                "document_type": "Combined",
                "system_name": "System",
                "title": "Title",
                "version": "1.0",
                "status": "Draft",
            },
            "high_level_design": {},
            "low_level_design": {},
        }
        self.assertEqual(utils._validate_design_json(base), [])
        del base["low_level_design"]
        issues = utils._validate_design_json(base)
        self.assertTrue(any("low_level_design" in issue["location"] for issue in issues))


class UtilsPersistenceTests(unittest.TestCase):
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

    def test_save_and_load_iteration_feedback_tracks_approval(self):
        result = utils.save_iteration_feedback(
            {"status": "COMPLIANCE APPROVED", "issues": ["fixed"]}
        )
        self.assertTrue(result.startswith("SUCCESS:"))

        feedback_path = Path(self.temp_dir.name) / "output" / "iteration_feedback.json"
        approval_path = Path(self.temp_dir.name) / "output" / "approval.json"
        saved = json.loads(feedback_path.read_text())
        approval = json.loads(approval_path.read_text())
        self.assertEqual(saved, {"status": "COMPLIANCE APPROVED", "data": ["fixed"]})
        self.assertEqual(approval["compliance_status"], "APPROVED")

        loaded = utils.load_iteration_feedback(reset_data=True)
        self.assertEqual(loaded["data"], ["fixed"])
        reset = json.loads(feedback_path.read_text())
        self.assertEqual(reset["data"], [])

    def test_load_master_process_json_uses_template_when_master_missing(self):
        template = Path(self.temp_dir.name) / "template.json"
        template.write_text(json.dumps(valid_process()))
        with patch.object(utils, "_load_template_json", return_value=valid_process()) as loader:
            result = utils.load_master_process_json()
        self.assertEqual(result["process_name"], "Example")
        loader.assert_called_once()

    def test_load_master_process_json_rejects_invalid_disk_json(self):
        output = Path(self.temp_dir.name) / "output"
        output.mkdir()
        (output / "process_data.json").write_text("{not-json")
        self.assertIsNone(utils.load_master_process_json())

    def test_load_full_process_context_returns_master_and_subprocesses(self):
        output = Path(self.temp_dir.name) / "output"
        subprocesses = output / "subprocesses"
        subprocesses.mkdir(parents=True)
        (output / "process_data.json").write_text(json.dumps({"process_name": "Master"}))
        (subprocesses / "one.json").write_text(json.dumps({"step_name": "One"}))
        result = utils.load_full_process_context()
        self.assertEqual(result["system_status"], "OK")
        self.assertEqual(result["master_process"]["process_name"], "Master")
        self.assertEqual(result["subprocesses"], [{"step_name": "One"}])


if __name__ == "__main__":
    unittest.main()
