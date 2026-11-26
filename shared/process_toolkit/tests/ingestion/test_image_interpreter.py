"""Tests for multimodal image interpretation and translation to process and requirements JSON."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from process_toolkit import paths
from process_toolkit.ingestion.extractors import load_directory_context
from process_toolkit.ingestion.image_interpreter import (
    IMAGE_MIME_TYPES,
    SUPPORTED_IMAGE_EXTENSIONS,
    import_image,
    interpret_image_with_model,
    translate_image_to_cloudarch_drawio,
    translate_image_to_process_json,
    translate_image_to_requirements_json,
)
from process_toolkit.schema.process_json import validate_process_json


def _create_test_image(path: Path, text: str = "Test Workflow Diagram") -> Path:
    img = Image.new("RGB", (400, 150), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 50), text, fill="black")
    img.save(path)
    return path


def test_supported_extensions_and_mime_types():
    assert ".png" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".jpg" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".jpeg" in SUPPORTED_IMAGE_EXTENSIONS
    assert IMAGE_MIME_TYPES[".png"] == "image/png"
    assert IMAGE_MIME_TYPES[".jpg"] == "image/jpeg"


def test_corrupt_image_raises_in_interpret_image_with_model():
    with tempfile.TemporaryDirectory() as d:
        corrupt = Path(d) / "bad.png"
        corrupt.write_bytes(b"not-an-image")
        try:
            interpret_image_with_model(str(corrupt))
            assert False, "Expected an exception for corrupt image"
        except Exception:
            pass


def test_interpret_image_with_mocked_model():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "diagram.png", "Process Order")
        mock_response = MagicMock()
        mock_response.text = "[Process Overview]\nProcess Name: Order Processing\n\n[Process Steps]\nSTEP-001: Receive Order"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=mock_client):
            result = interpret_image_with_model(str(img_path), target="process")

        assert "Order Processing" in result
        assert "Receive Order" in result
        mock_client.models.generate_content.assert_called_once()
        call_kwargs = mock_client.models.generate_content.call_args[1]
        assert call_kwargs["model"] == "gemini-3.8-flash"
        contents = call_kwargs["contents"]
        assert len(contents) == 2


def test_interpret_image_fallback_on_404_model_unavailable():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "diagram.png", "Process Order")
        mock_response = MagicMock()
        mock_response.text = "[Process Overview]\nProcess Name: Order Processing"

        mock_client = MagicMock()
        # First call fails with 404 NOT_FOUND, second call succeeds
        mock_client.models.generate_content.side_effect = [
            Exception("404 NOT_FOUND: This model models/gemini-foo is no longer available to new users."),
            mock_response,
        ]

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=mock_client):
            result = interpret_image_with_model(str(img_path), target="process", model_name="gemini-foo")

        assert "Order Processing" in result
        assert mock_client.models.generate_content.call_count == 2
        first_call = mock_client.models.generate_content.call_args_list[0][1]
        second_call = mock_client.models.generate_content.call_args_list[1][1]
        assert first_call["model"] == "gemini-foo"
        assert second_call["model"] == "gemini-3.8-flash"


def test_interpret_image_fallback_to_ocr_when_no_client():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "claim.png", "Approve Claim")

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=None):
            result = interpret_image_with_model(str(img_path), target="general")

        assert "Claim" in result


def test_translate_image_to_process_json_with_mocked_model():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "shipping_flow.png")
        sample_process = {
            "process_name": "Package Shipping Flow",
            "version": "1.0",
            "introduction": (
                "End-to-end package shipping and logistics workflow detailing every operational step from packing items "
                "through carrier handoff. This document establishes standard operating procedures for warehouse teams "
                "to ensure timely and accurate customer order delivery across all regional logistics fulfillment centers."
            ),
            "purpose": (
                "The purpose of this shipping process is to eliminate dispatch errors, maintain continuous parcel tracking, "
                "and ensure full compliance with freight carrier guidelines and customer service level agreements. "
                "By standardizing each packing and dispatch task, warehouse throughput is maximized and damages are minimized."
            ),
            "scope": (
                "This process covers all outbound parcel handling within the main distribution facility, encompassing "
                "container selection, label verification, carrier manifesting, and loading dock dispatch. Out-of-scope "
                "activities include supplier freight intake, raw inventory replenishment, and customer return triage."
            ),
            "process_owner": "Logistics Lead",
            "industry_sector": "Supply Chain",
            "stakeholders": [{"stakeholder_name": "Warehouse Worker", "role": "Packer", "responsibilities": ["Pack items"]}],
            "process_steps": [
                {
                    "step_id": "STEP-001",
                    "step_name": "Pack Items",
                    "description": (
                        "Secure items in a standard corrugated box according to fragility specifications, insert protective "
                        "cushioning materials, seal with reinforced packing tape, and affix the high-resolution barcode label."
                    ),
                    "responsible_party": "Packer",
                    "estimated_duration": "15 minutes",
                    "deliverables": ["Packed Box"],
                    "inputs": ["Pick List"],
                    "outputs": ["Labeled Package"],
                    "dependencies": [],
                    "success_criteria": "Barcode scans without errors.",
                },
                {
                    "step_id": "STEP-002",
                    "step_name": "Dispatch Package",
                    "description": (
                        "Hand over the packed parcel to the designated freight carrier representative, scan into the carrier portal, "
                        "record the unique tracking identifier, and obtain an authorized signature on the daily dispatch manifest."
                    ),
                    "responsible_party": "Dispatcher",
                    "estimated_duration": "30 minutes",
                    "deliverables": ["Carrier Manifest"],
                    "inputs": ["Labeled Package"],
                    "outputs": ["Dispatched Package"],
                    "dependencies": ["Pack Items"],
                    "success_criteria": "Manifest signed by carrier.",
                },
            ],
            "metrics": [{"metric": "On-Time Dispatch", "description": "Percentage of packages dispatched within SLA."}],
            "critical_success_factors": [{"factor": "Accurate Weight", "description": "Precise weighing prevents carrier delays."}],
            "critical_failure_factors": [{"factor": "Mislabeled Destination", "description": "Routing package to incorrect hub."}],
            "reporting_and_analytics": [{"report": "Daily Dispatch Summary", "description": "Volume of packages shipped per carrier."}],
        }

        mock_response = MagicMock()
        mock_response.text = f"```json\n{json.dumps(sample_process)}\n```"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=mock_client):
            process_json = translate_image_to_process_json(str(img_path))

        assert process_json["process_name"] == "Package Shipping Flow"
        assert len(process_json["process_steps"]) == 2
        validation = validate_process_json(process_json)
        assert validation["valid"] is True


def test_translate_image_to_process_json_offline_fallback():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "vendor_onboarding.png", "Vendor Verification")

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=None):
            process_json = translate_image_to_process_json(str(img_path))

        assert "Vendor Onboarding" in process_json["process_name"]
        assert len(process_json["process_steps"]) >= 1
        assert process_json["process_steps"][0]["step_name"]
        validation = validate_process_json(process_json)
        assert validation["valid"] is True


def test_translate_image_to_requirements_json_with_mocked_model():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "portal_wireframe.png")
        sample_requirements = {
            "name": "Customer Portal Requirements Specification",
            "source_directory": str(d),
            "source_files": ["portal_wireframe.png"],
            "summary": "Customer self-service portal specifications.",
            "industry_sector": "Fintech",
            "current_state": "Manual phone-based inquiries.",
            "future_state": "Digital self-service portal.",
            "success_measures": ["50% reduction in support calls"],
            "requirements_register": [
                {
                    "id": "FR-001",
                    "type": "functional",
                    "description": "The portal shall allow users to view current account balance.",
                    "source": "Image Analysis: portal_wireframe.png",
                    "priority": "high",
                    "status": "proposed",
                    "acceptance_criteria": ["Balance updates within 5 seconds of transaction."],
                }
            ],
            "stakeholders": ["End User", "Product Manager", "Core Banking Engineer"],
            "assumptions": ["API gateways are authenticated with OAuth2."],
            "risks": ["Session timeouts during active form completion."],
            "scope_in": ["Account overview and transaction history"],
            "scope_out": ["Direct international wire initiation"],
            "open_questions": [],
        }

        mock_response = MagicMock()
        mock_response.text = json.dumps(sample_requirements)
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=mock_client):
            req_json = translate_image_to_requirements_json(str(img_path))

        assert req_json["name"] == "Customer Portal Requirements Specification"
        assert len(req_json["requirements_register"]) == 1
        assert req_json["requirements_register"][0]["id"] == "FR-001"


def test_translate_image_to_requirements_json_offline_fallback():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "checkout_spec.png", "Payment Gateway")

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=None):
            req_json = translate_image_to_requirements_json(str(img_path))

        assert "Checkout Spec" in req_json["name"]
        assert len(req_json["requirements_register"]) >= 1
        assert req_json["requirements_register"][0]["type"] == "functional"


def test_import_image_end_to_end_process():
    with tempfile.TemporaryDirectory() as d:
        session_id = "test-session-image-process"
        img_path = _create_test_image(Path(d) / "incident_workflow.png", "Incident Escalation")

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=None):
            result = import_image(str(img_path), target_type="process", session_id=session_id)

        assert result["status"] == "OK"
        assert result["target_type"] == "process"
        assert os.path.exists(result["artifact_path"])
        with open(result["artifact_path"]) as f:
            saved = json.load(f)
        assert "Incident Workflow" in saved["process_name"]


def test_import_image_end_to_end_requirements():
    with tempfile.TemporaryDirectory() as d:
        session_id = "test-session-image-req"
        img_path = _create_test_image(Path(d) / "mobile_app_spec.png", "Push Notifications")

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=None):
            result = import_image(str(img_path), target_type="requirements", session_id=session_id)

        assert result["status"] == "OK"
        assert result["target_type"] == "requirements"
        assert os.path.exists(result["artifact_path"])
        with open(result["artifact_path"]) as f:
            saved = json.load(f)
        assert "Mobile App Spec" in saved["name"]


def test_import_image_end_to_end_cloudarch():
    with tempfile.TemporaryDirectory() as d:
        session_id = "test-session-image-cloudarch"
        img_path = _create_test_image(Path(d) / "serverless_arch.png", "AWS API Gateway Lambda DynamoDB")

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=None):
            result = import_image(str(img_path), target_type="cloudarch", session_id=session_id)

        assert result["status"] == "OK"
        assert result["target_type"] == "cloudarch"
        assert os.path.exists(result["artifact_path"])
        assert result["artifact_path"].endswith("cloudarch_drawio.xml")
        assert "<mxfile" in result["xml"]
        with open(result["artifact_path"], encoding="utf-8") as f:
            saved_xml = f.read()
        assert "<mxfile" in saved_xml


def test_translate_image_to_cloudarch_drawio_structured_json():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "payment_arch.png", "Payment Processing")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "title": "Payment Microservices Architecture",
            "subtitle": "Secure payment processing platform",
            "provider": "aws",
            "zones": [
                {"id": "zone_ingress", "name": "Ingress Zone", "type": "zone"},
                {"id": "zone_app", "name": "Payment VPC", "type": "vpc"},
            ],
            "components": [
                {"id": "c_gateway", "name": "API Gateway", "zone_id": "zone_ingress", "icon": "api_gateway", "bullets": ["Edge Ingress"]},
                {"id": "c_lambda", "name": "Payment Lambda", "zone_id": "zone_app", "icon": "lambda", "bullets": ["Card Authorization"]},
            ],
            "edges": [
                {"source": "c_gateway", "target": "c_lambda", "label": "HTTPS/POST"},
            ],
        })
        mock_client.models.generate_content.return_value = mock_response

        with patch("process_toolkit.ingestion.image_interpreter._get_genai_client", return_value=mock_client):
            drawio_xml = translate_image_to_cloudarch_drawio(str(img_path))

        assert "<mxfile" in drawio_xml
        assert "Payment Microservices Architecture" in drawio_xml
        assert "API Gateway" in drawio_xml
        assert "Payment Lambda" in drawio_xml


def test_import_image_validations():
    assert import_image("/non/existent/path.png")["status"] == "ERROR"

    with tempfile.TemporaryDirectory() as d:
        txt = Path(d) / "note.txt"
        txt.write_text("Hello")
        assert import_image(str(txt))["status"] == "ERROR"

        img = _create_test_image(Path(d) / "valid.png")
        assert import_image(str(img), target_type="unknown")["status"] == "ERROR"


def test_load_directory_context_supports_direct_image_file_path():
    with tempfile.TemporaryDirectory() as d:
        img_path = _create_test_image(Path(d) / "single_diagram.png", "Invoice Approval Flow")

        with patch("process_toolkit.ingestion.extractors.interpret_image_with_model", return_value="Invoice Approval Flow"):
            result = load_directory_context(str(img_path))

    assert result["status"] == "OK"
    assert result["files_processed"] == ["single_diagram.png"]
    assert len(result["images"]) == 1
    assert result["images"][0]["name"] == "single_diagram.png"
    assert result["images"][0]["mime_type"] == "image/png"
    assert "Invoice Approval" in result["combined_text"]
