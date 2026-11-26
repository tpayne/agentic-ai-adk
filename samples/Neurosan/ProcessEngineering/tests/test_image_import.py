"""Tests for image import wiring and execution in Neurosan ProcessEngineering."""

from pathlib import Path
import tempfile
from unittest.mock import patch
from PIL import Image, ImageDraw

from coded_tools.process_import.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as ProcessImportLoadDirectoryContextCodedTool,
)
from coded_tools.requirements_summary.load_directory_context_tool import (
    LoadDirectoryContextCodedTool as RequirementsLoadDirectoryContextCodedTool,
)
from process_interface.ingestion.extractors import import_image, load_directory_context

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _create_test_image(path: Path, text: str = "Test Workflow") -> Path:
    img = Image.new("RGB", (400, 150), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 50), text, fill="black")
    img.save(path)
    return path


def test_router_mentions_image_import():
    router_text = (PROJECT_ROOT / "registries" / "process_architect.hocon").read_text(encoding="utf-8")
    assert "IMAGE IMPORT (JPG/PNG)" in router_text
    assert "workflow.png" in router_text
    assert "Process_Import_Agent" in router_text
    assert "Requirements_Summary_Agent" in router_text
    assert "CloudArch_Import_Agent" in router_text


def test_process_import_hocon_mentions_image_interpretation():
    import_hocon = (PROJECT_ROOT / "registries" / "process_import.hocon").read_text(encoding="utf-8")
    assert "multimodal model" in import_hocon
    assert "swimlanes" in import_hocon
    assert "sequence flow" in import_hocon


def test_requirements_summary_hocon_mentions_image_interpretation():
    req_hocon = (PROJECT_ROOT / "registries" / "requirements_summary.hocon").read_text(encoding="utf-8")
    assert "multimodal model" in req_hocon
    assert "specifications" in req_hocon


def test_cloudarch_import_hocon_mentions_image_interpretation():
    arch_hocon = (PROJECT_ROOT / "registries" / "cloudarch_import.hocon").read_text(encoding="utf-8")
    assert "architecture image" in arch_hocon
    assert "import_image" in arch_hocon


def test_load_directory_context_coded_tool_accepts_image_file():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "process_diagram.png", "Approval Workflow")

        with patch("process_toolkit.ingestion.extractors.interpret_image_with_model", return_value="Approval Workflow"):
            tool = ProcessImportLoadDirectoryContextCodedTool()
            result = tool.invoke({"directory": str(img_path)}, {})
            assert result["status"] == "OK"
            assert result["files_processed"] == ["process_diagram.png"]
            assert len(result["images"]) == 1
            assert "Approval Workflow" in result["combined_text"]

            # Also test with 'path' alias
            req_tool = RequirementsLoadDirectoryContextCodedTool()
            result_alias = req_tool.invoke({"path": str(img_path)}, {})
            assert result_alias["status"] == "OK"
            assert result_alias["files_processed"] == ["process_diagram.png"]


def test_import_image_tool_execution():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "incident_management.png", "Incident Management")

        process_result = import_image(str(img_path), target_type="process")
        assert process_result["status"] == "OK"
        assert "Incident Management" in process_result["data"]["process_name"]

        req_result = import_image(str(img_path), target_type="requirements")
        assert req_result["status"] == "OK"
        assert "Incident Management" in req_result["data"]["name"]

        arch_result = import_image(str(img_path), target_type="cloudarch")
        assert arch_result["status"] == "OK"
        assert arch_result["target_type"] == "cloudarch"
        assert "<mxfile" in arch_result["xml"]
        assert Path(arch_result["artifact_path"]).exists()


def test_cloudarch_import_image_coded_tool():
    from coded_tools.cloudarch_import.import_image_tool import ImportImageCodedTool
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "infra.png", "Microservices Architecture")
        tool = ImportImageCodedTool()
        res = tool.invoke({"path": str(img_path)}, {})
        assert res["status"] == "OK"
        assert "<mxfile" in res["xml"]
