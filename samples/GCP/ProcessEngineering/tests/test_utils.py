import json
import re
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


def valid_design(document_type="LLD"):
    design = {
        "document_metadata": {
            "document_id": "D1",
            "document_type": document_type,
            "system_name": "System",
            "title": "Title",
            "version": "1.0",
            "status": "Draft",
        },
    }
    if document_type in ("HLD", "Combined"):
        design["high_level_design"] = {}
    if document_type in ("LLD", "Combined"):
        design["low_level_design"] = {}
    return design


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
        base = valid_design("Combined")
        self.assertEqual(utils._validate_design_json(base), [])
        del base["low_level_design"]
        issues = utils._validate_design_json(base)
        self.assertTrue(any("low_level_design" in issue["location"] for issue in issues))

    def test_design_validator_accepts_document_type_specific_sections(self):
        for document_type in ("HLD", "LLD", "Combined"):
            with self.subTest(document_type=document_type):
                result = utils.validate_design_json(valid_design(document_type))
                self.assertTrue(result["valid"])
                self.assertEqual(result["schema_type"], "design")

    def test_design_validator_reports_missing_metadata_and_invalid_type(self):
        design = valid_design()
        del design["document_metadata"]["system_name"]
        result = utils.validate_design_json(design)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any(
                "document_metadata.system_name" in issue["location"]
                for issue in result["issues"]
            )
        )

        design = valid_design()
        design["document_metadata"]["document_type"] = "Unknown"
        result = utils.validate_design_json(design)
        self.assertFalse(result["valid"])
        self.assertEqual(
            result["issues"][0]["location"],
            "$.document_metadata.document_type",
        )


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

    def test_persist_final_design_json_validates_before_writing(self):
        with patch.object(utils, "_save_raw_data_to_json", return_value="saved") as writer:
            result = utils.persist_final_design_json({"document_metadata": {}})

        self.assertIn("JSON validation failed", result)
        writer.assert_not_called()

    def test_persist_final_design_json_routes_valid_document_to_design_output(self):
        with patch.object(utils, "_save_raw_data_to_json", return_value="saved") as writer:
            result = utils.persist_final_design_json(valid_design("LLD"))

        self.assertEqual(result, "saved")
        writer.assert_called_once()
        self.assertEqual(writer.call_args.kwargs["schema_type"], "design")


def _labeled_box_with_icon(cell_id, label, icon_shape, x, y, w=240, h=130):
    """Builds the codebase's own mandated composition pattern: a labeled
    box plus a SEPARATE small icon child cell (empty value, bare shape=
    style) -- exactly what cloudarch_agent.txt tells the LLM to emit for
    every service box with an icon."""
    return f"""
        <mxCell id="{cell_id}" value="&lt;b&gt;{label}&lt;/b&gt;&lt;br/&gt;Detail line" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#4285F4;strokeWidth=1.5;verticalAlign=top;spacingTop=56;fontSize=11;" vertex="1" parent="1">
          <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />
        </mxCell>
        <mxCell id="{cell_id}_icon" value="" style="html=1;aspect=fixed;strokeColor=none;fillColor=#4285F4;shape={icon_shape};" vertex="1" parent="{cell_id}">
          <mxGeometry x="80" y="8" width="40" height="40" as="geometry" />
        </mxCell>
    """


class SaveDrawioShapeMappingTests(unittest.TestCase):
    """Regression coverage for a real bug found via a user's log: any
    leaf service box whose label happened to contain a container-map
    keyword (e.g. "Subnet", "VPC") was having its entire style silently
    replaced with a generic container fallback on every single save --
    permanently undoing the LLM's own correct icon composition and making
    the reviewer's flagged issue unfixable, because the box's ENTIRE
    style is REPLACED with a plain "shape=rect;...;spacingTop=3;..."
    style that collides with the 40px icon child at y=8. The root cause:
    _apply_shape_mappings' container-detection treated "this cell has ANY
    child" as evidence it's a container, but every correctly-composed
    service box has exactly one child -- its own icon cell -- which is
    not a container signal at all."""

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

    def _save_and_load(self, xml_content):
        result = utils.save_drawio(xml_content)
        self.assertIsInstance(result, dict, f"save_drawio returned an error: {result}")
        path = Path(self.temp_dir.name) / "output" / "cloudarch_drawio.xml"
        return path.read_text()

    def test_leaf_service_box_with_container_keyword_label_keeps_its_icon(self):
        # "Private Google Access (PGA) Subnet" contains "Subnet" and "VPC
        # Service Controls (Security Perimeter)" contains "VPC " -- both
        # real container_map keywords -- but neither is an actual
        # container: each is a single labeled service box with its own
        # icon, exactly like every other box in the diagram.
        xml = f"""<mxfile host="app.diagrams.net" agent="CloudArch_Agent">
  <diagram id="d1" name="GCP Test Architecture">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        {_labeled_box_with_icon("gcp_pga", "Private Google Access (PGA) Subnet", "mxgraph.gcp2.virtual_private_cloud", 410, 460)}
        {_labeled_box_with_icon("vpc_sc", "VPC Service Controls (Security Perimeter)", "mxgraph.gcp2.security_command_center", 410, 620)}
        {_labeled_box_with_icon("gcp_vpn", "Cloud HA VPN", "mxgraph.gcp2.cloud_vpn", 700, 460)}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""
        saved = self._save_and_load(xml)

        for cell_id in ("gcp_pga", "vpc_sc", "gcp_vpn"):
            box_style_match = re.search(rf'id="{cell_id}"[^>]*style="([^"]*)"', saved)
            self.assertIsNotNone(box_style_match, f"{cell_id} missing from saved XML")
            box_style = box_style_match.group(1)
            self.assertNotIn(
                "shape=rect", box_style,
                f"{cell_id} was corrupted into the generic container fallback style",
            )
            self.assertIn("verticalAlign=top", box_style)

            icon_style_match = re.search(rf'id="{cell_id}_icon"[^>]*style="([^"]*)"', saved)
            self.assertIsNotNone(icon_style_match, f"{cell_id}_icon missing from saved XML")
            self.assertIn("shape=mxgraph.gcp2.", icon_style_match.group(1))

    def test_genuine_container_with_real_nested_children_is_still_mapped(self):
        # A cell with a REAL nested labeled box as a child (not just its
        # own icon) is still legitimate container evidence and should
        # still be eligible for container mapping -- this fix narrows a
        # false positive, it doesn't remove real detection.
        xml = """<mxfile host="app.diagrams.net" agent="CloudArch_Agent">
  <diagram id="d1" name="GCP Test Architecture">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <mxCell id="my_subnet" value="Subnet Zone" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="400" height="300" as="geometry" />
        </mxCell>
        <mxCell id="nested_service" value="&lt;b&gt;Nested Service&lt;/b&gt;" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;" vertex="1" parent="my_subnet">
          <mxGeometry x="20" y="40" width="200" height="100" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""
        saved = self._save_and_load(xml)
        box_style_match = re.search(r'id="my_subnet"[^>]*style="([^"]*)"', saved)
        self.assertIsNotNone(box_style_match)
        # "subnet" is a real GCP_CONTAINERS keyword -- with a genuine
        # nested child (not just an icon), this SHOULD be mapped to the
        # container fallback style.
        self.assertIn("shape=rect", box_style_match.group(1))


if __name__ == "__main__":
    unittest.main()
