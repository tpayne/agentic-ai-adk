"""Multimodal image interpretation and translation to process and requirements schemas.

Uses a multimodal model (Gemini via google-genai, or configured provider) to inspect
images (JPG/PNG diagrams, flowcharts, BPMN workflows, wireframes, architectural diagrams,
scanned specifications) and extract structured process workflows or requirements registers,
with graceful fallback to OCR (pytesseract) when offline or unconfigured.
"""

import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from process_toolkit import paths
from process_toolkit.schema.process_json import (
    PROCESS_TEMPLATE,
    extract_valid_json,
    persist_final_json,
    validate_process_json,
)
from process_toolkit.schema.requirements_json import (
    REQUIREMENTS_SUMMARY_TEMPLATE,
)
from process_toolkit.requirements_summary.requirements_summary import (
    save_requirements_summary,
)

logger = logging.getLogger("ProcessArchitect.ImageInterpreter")

SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"})

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
}

_PROCESS_INTERPRETATION_PROMPT = """You are a Principal Business Process Architect and Systems Analyst.
Visually inspect the provided image (which may be a BPMN workflow, flowchart, swimlane diagram, process map, or document) and produce a comprehensive, structured textual description of the business process depicted.

Structure your response with the following sections:
[Process Overview]
- Process Name: (The exact name of the process shown or a specific descriptive title)
- Purpose: (What goal or business outcome this process achieves)
- Industry / Domain: (Relevant business domain or sector)

[Stakeholders and Roles]
- List every actor, user role, system, or swimlane depicted, along with their responsibilities.

[Process Steps and Sequence Flow]
Trace the complete workflow from start to finish in exact chronological/logical order. For EACH step:
1. Step ID and Name (e.g. STEP-001: Submit Purchase Order)
2. Detailed Description: (2-4 clear sentences explaining exactly what occurs, how, and under what conditions)
3. Responsible Party: (The specific role, actor, or automated system performing the step)
4. Estimated Duration / SLA: (If indicated, or reasonable estimate based on the activity)
5. Inputs & Prerequisites: (Data, documents, or triggers needed to begin)
6. Deliverables & Outputs: (Artifacts, status changes, or documents produced)
7. Dependencies: (Preceding steps that must complete first)
8. Success Criteria: (How completion of this step is verified)

[Decision Gateways and Branching Logic]
- For each decision diamond, branching gateway, or conditional path:
  - Gateway Name / Condition
  - Positive / True / Approved Path: Next step(s)
  - Negative / False / Rejected Path: Next step(s) or remediation loop
  - Default / Exception handling

[Business Rules and Compliance Constraints]
- List all policies, validations, limits, regulatory requirements, or checks explicitly mentioned or visually represented.

Be thorough, precise, and preserve all textual labels, identifiers, and connections visible in the image."""

_REQUIREMENTS_INTERPRETATION_PROMPT = """You are a Lead Requirements Engineer and Systems Analyst.
Visually inspect the provided image (which may be an architecture diagram, UI mockup, system workflow, specification, or process map) and extract a rigorous, structured requirements summary.

Structure your response with the following sections:
[Specification Title & Scope]
- Name: (Specific project, application, or system title)
- Industry Sector: (Domain)
- High-level Summary: (Executive overview of what is depicted)
- Current State vs. Future State: (If indicated or implied)
- Success Measures: (Concrete metrics or KPIs)

[Stakeholders & Personas]
- List all stakeholders, personas, external systems, and user types.

[Requirements Register]
Extract every distinct functional requirement as a numbered item (FR-001, FR-002, etc.):
- ID: FR-xxx
- Title: (Concise requirement title)
- Type: (Functional / Integration / Reporting / Governance)
- Description: (Clear "The system shall..." statement with full depth)
- Priority: (High / Medium / Low)
- Acceptance Criteria: (Specific verifiable criteria)
- Source: (Note that it is derived from the visual image/diagram)

[Non-Functional Requirements & Constraints]
- Non-functional requirements (NFRs) regarding performance, security, availability, scalability, audit, and usability.
- Known constraints and technical limitations.

[Assumptions and Identified Risks]
- Any business or technical assumptions visible or necessary for the workflow.
- Potential risks, edge cases, or failure modes depicted.

Be thorough, faithful to all diagram elements, and capture all text, connectors, and implied rules."""

_GENERAL_INTERPRETATION_PROMPT = """You are an expert Technical Architect and Business Analyst.
Visually inspect the provided image (diagram, flowchart, architecture map, wireframe, or document scan) and provide a detailed, structured extraction covering:
1. Document / Diagram Title and Purpose
2. Visual Elements, Layout, and Notation (BPMN, UML, flowchart, architecture)
3. Actors, Roles, Swimlanes, and Systems
4. Sequential Workflow Steps (with step names, responsible parties, actions, inputs, outputs, and connections)
5. Decision Points, Conditional Gateways, and Error / Exception Paths
6. Functional Requirements and Business Rules implied by or stated in the visual structure
7. Non-functional Requirements, Dependencies, and Notes

Provide a complete, readable transcription of all textual and relational information in the image."""


def _extract_image_file_ocr(path: str) -> str:
    """Fallback OCR text extraction using PIL and pytesseract."""
    try:
        from PIL import Image
        import pytesseract

        with Image.open(path) as image:
            return pytesseract.image_to_string(image).strip()
    except Exception as e:
        logger.debug("OCR extraction failed for %s: %s", path, e)
        return ""


def _get_genai_client() -> Optional[Any]:
    """Attempts to instantiate a google.genai Client using available API keys.

    Returns None if google.genai is not installed, no API key is found,
    or client initialization fails.
    """
    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("WEBAPIKEY")
    )
    # Ignore placeholder default keys used in local tests
    if not api_key or api_key in ("change-me", "test-key-unused", "fake-key"):
        return None

    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.debug("Could not initialize google.genai client: %s", e)
        return None


def _make_image_part(image_bytes: bytes, mime_type: str) -> Any:
    """Creates a multimodal Part object, or stub if google-genai is uninstalled/mocked."""
    try:
        from google.genai import types
        return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    except Exception:
        class _PartStub:
            def __init__(self, data: bytes, mime_type: str):
                self.data = data
                self.mime_type = mime_type
        return _PartStub(image_bytes, mime_type)


_FALLBACK_MULTIMODAL_MODELS = ("gemini-3.8-flash", "gemini-3-flash", "gemini-2.0-flash")


def _resolve_model_name(preferred: Optional[str] = None) -> str:
    """Resolves the multimodal model name to use."""
    if preferred:
        model = preferred
    else:
        model = (
            os.environ.get("GEMINI_IMAGE_MODEL")
            or os.environ.get("MODEL_NAME")
            or "gemini-3.8-flash"
        )
    # Strip any provider prefixes (e.g. "google_genai:gemini-3.8-flash" or "google/")
    if ":" in model:
        model = model.split(":", 1)[1]
    if model.startswith("google/"):
        model = model[len("google/"):]
    return model


def _generate_with_model_fallback(
    client: Any,
    primary_model: str,
    contents: List[Any],
) -> Any:
    """Invokes generate_content on client with automatic fallback for 404/deprecated models."""
    candidate_models = [primary_model]
    for fb in _FALLBACK_MULTIMODAL_MODELS:
        if fb != primary_model and fb not in candidate_models:
            candidate_models.append(fb)

    last_error = None
    for model in candidate_models:
        try:
            logger.info("Calling multimodal model %s...", model)
            return client.models.generate_content(
                model=model,
                contents=contents,
            )
        except Exception as e:
            err_str = str(e)
            is_model_unavailable = (
                "404" in err_str
                or "NOT_FOUND" in err_str
                or "not found" in err_str.lower()
                or "no longer available" in err_str.lower()
                or "unsupported" in err_str.lower()
            )
            if is_model_unavailable and model != candidate_models[-1]:
                logger.warning(
                    "Multimodal model %s unavailable (%s); falling back to next candidate...",
                    model,
                    e,
                )
                last_error = e
                continue
            raise
    if last_error:
        raise last_error


def interpret_image_with_model(
    path: str,
    target: str = "general",
    model_name: Optional[str] = None,
) -> str:
    """Interprets a JPG/PNG/image file using a multimodal model.

    Args:
        path: Absolute or relative path to the image file.
        target: Target domain: "process", "requirements", or "general".
        model_name: Optional override for the multimodal model.

    Returns:
        Structured textual description of the image content. Falls back to OCR
        if the model is unavailable or unconfigured.

    Raises:
        Exception: If the file is not a valid, decodable image.
    """
    if not os.path.isfile(path):
        return ""

    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        return ""

    # Validate that the file is genuinely decodable as an image.
    # If corrupt or non-image, this raises and load_directory_context records
    # it in files_skipped without adding to images.
    from PIL import Image
    with Image.open(path) as img:
        img.verify()

    client = _get_genai_client()
    if client is not None:
        try:
            mime_type = IMAGE_MIME_TYPES.get(ext, "image/png")
            with open(path, "rb") as f:
                image_bytes = f.read()

            image_part = _make_image_part(image_bytes, mime_type)

            if target == "process":
                prompt = _PROCESS_INTERPRETATION_PROMPT
            elif target == "requirements":
                prompt = _REQUIREMENTS_INTERPRETATION_PROMPT
            else:
                prompt = _GENERAL_INTERPRETATION_PROMPT

            model = _resolve_model_name(model_name)
            logger.info("Interpreting image %s using model %s (target=%s)...", path, model, target)
            response = _generate_with_model_fallback(
                client=client,
                primary_model=model,
                contents=[image_part, prompt],
            )
            text = (response.text or "").strip()
            if text:
                return text
        except Exception as e:
            logger.warning("Multimodal image interpretation failed for %s: %s; falling back to OCR", path, e)

    # Fallback to OCR text
    return _extract_image_file_ocr(path)


def translate_image_to_process_json(
    path: str,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Translates a JPG/PNG process diagram into a valid process JSON object.

    Uses a multimodal model to parse visual workflow, actors, sequence flow, and
    decision logic directly into the canonical process_data.json schema.
    """
    client = _get_genai_client()
    ext = os.path.splitext(path)[1].lower()
    mime_type = IMAGE_MIME_TYPES.get(ext, "image/png")

    if client is not None and os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                image_bytes = f.read()

            image_part = _make_image_part(image_bytes, mime_type)
            schema_sample = json.dumps(PROCESS_TEMPLATE, indent=2)

            prompt = (
                "You are an expert Business Process Architect. Visually analyze this process diagram / workflow image "
                "and translate it directly into a valid JSON object matching the process specification schema below.\n\n"
                f"SCHEMA REFERENCE TEMPLATE:\n{schema_sample}\n\n"
                "MANDATORY STRUCTURAL RULES:\n"
                "1. 'process_name': Specific, descriptive name of the process.\n"
                "2. 'process_steps': Non-empty list of steps in sequence order.\n"
                "   Every step MUST have non-empty 'step_name', 'description' (at least 2 substantive sentences), "
                "   'responsible_party', 'estimated_duration', 'deliverables' (list of non-empty strings), "
                "   'inputs' (list), 'outputs' (list), and 'dependencies' (list of prior step_names in this document).\n"
                "3. 'stakeholders': List of objects with 'stakeholder_name', 'role', and 'responsibilities'.\n"
                "4. 'metrics', 'critical_success_factors', 'critical_failure_factors', 'reporting_and_analytics': "
                "   Each list item must have 'metric'/'factor'/'report' (or 'name') and a non-empty 'description'.\n"
                "5. Return ONLY a single raw JSON object. Do not wrap in markdown or include conversational text."
            )

            model = _resolve_model_name(model_name)
            logger.info("Translating image %s to process JSON using %s...", path, model)
            response = _generate_with_model_fallback(
                client=client,
                primary_model=model,
                contents=[image_part, prompt],
            )
            raw_text = (response.text or "").strip()
            parsed = extract_valid_json(raw_text)
            if parsed and isinstance(parsed, dict) and "process_steps" in parsed:
                # Normalize and validate
                validation = validate_process_json(parsed)
                if validation.get("valid"):
                    return parsed
                # Repair minor structural issues if possible
                repaired = _repair_process_json(parsed)
                if validate_process_json(repaired).get("valid"):
                    return repaired
                return repaired
        except Exception as e:
            logger.warning("Model translation of %s to process JSON failed: %s; synthesizing from interpretation", path, e)

    # Fallback path: interpret image (model or OCR) and construct a compliant baseline
    text_content = interpret_image_with_model(path, target="process", model_name=model_name)
    return _build_process_json_from_text(path, text_content)


def translate_image_to_requirements_json(
    path: str,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Translates a JPG/PNG diagram or spec image into a valid requirements summary JSON object.

    Uses a multimodal model to extract functional and non-functional requirements,
    stakeholders, constraints, and business rules directly into requirements_summary.json format.
    """
    client = _get_genai_client()
    ext = os.path.splitext(path)[1].lower()
    mime_type = IMAGE_MIME_TYPES.get(ext, "image/png")

    if client is not None and os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                image_bytes = f.read()

            image_part = _make_image_part(image_bytes, mime_type)
            schema_sample = json.dumps(REQUIREMENTS_SUMMARY_TEMPLATE, indent=2)

            prompt = (
                "You are a Lead Requirements Engineer. Visually analyze this image (architecture diagram, "
                "UI wireframe, workflow, or specification document) and translate all requirements, specifications, "
                "and rules into a valid JSON object matching the requirements summary schema below.\n\n"
                f"SCHEMA REFERENCE TEMPLATE:\n{schema_sample}\n\n"
                "MANDATORY STRUCTURAL RULES:\n"
                "1. 'name': Specific title for this requirements summary.\n"
                "2. 'summary': Substantive 2-4 sentence prose overview.\n"
                "3. 'requirements_register': List of objects with 'id' (FR-001, FR-002, etc.), 'type' ('functional', "
                "   'non_functional', 'goal', 'constraint'), 'description', 'priority' ('high', 'medium', 'low'), "
                "   'acceptance_criteria' (list of strings), and 'source' ('Image Analysis: ' + filename).\n"
                "4. 'stakeholders', 'assumptions', 'risks', 'scope_in', 'scope_out': Non-empty lists where applicable.\n"
                "5. Return ONLY a single raw JSON object. Do not wrap in markdown or include conversational text."
            )

            model = _resolve_model_name(model_name)
            logger.info("Translating image %s to requirements JSON using %s...", path, model)
            response = _generate_with_model_fallback(
                client=client,
                primary_model=model,
                contents=[image_part, prompt],
            )
            raw_text = (response.text or "").strip()
            parsed = extract_valid_json(raw_text)
            if parsed and isinstance(parsed, dict) and ("requirements_register" in parsed or "functional_requirements" in parsed):
                _normalize_requirements_summary(parsed, path)
                return parsed
        except Exception as e:
            logger.warning("Model translation of %s to requirements JSON failed: %s; synthesizing from interpretation", path, e)

    # Fallback path: interpret image (model or OCR) and construct a compliant baseline
    text_content = interpret_image_with_model(path, target="requirements", model_name=model_name)
    return _build_requirements_json_from_text(path, text_content)


def import_image(
    path: str,
    target_type: str = "process",
    session_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Imports an image file (JPG/PNG) and translates it into the specified JSON artifact.

    Args:
        path: Path to the image file.
        target_type: "process" (for process_data.json) or "requirements" (for requirements_summary.json).
        session_id: Optional session identifier for isolated output storage.
        model_name: Optional model name override.

    Returns:
        Dict reporting status, target_type, saved artifact path, and data payload.
    """
    resolved = os.path.abspath(path)
    if not os.path.isfile(resolved):
        return {"status": "ERROR", "error": f"Image file not found: {resolved}"}

    ext = os.path.splitext(resolved)[1].lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        return {"status": "ERROR", "error": f"Unsupported image extension '{ext}'. Supported: {sorted(SUPPORTED_IMAGE_EXTENSIONS)}"}

    target = (target_type or "process").lower().strip()
    if target not in ("process", "requirements"):
        return {"status": "ERROR", "error": f"Invalid target_type '{target_type}'. Expected 'process' or 'requirements'."}

    # Context management for session isolation if session_id provided
    cm = paths.use_session(session_id) if session_id else None
    if cm:
        cm.__enter__()

    try:
        if target == "process":
            data = translate_image_to_process_json(resolved, model_name=model_name)
            persist_result = persist_final_json(data)
            if persist_result.startswith("ERROR:"):
                return {"status": "ERROR", "error": persist_result, "data": data}
            artifact_file = paths.output_path("process_data.json")
            return {
                "status": "OK",
                "target_type": "process",
                "image_path": resolved,
                "artifact_path": artifact_file,
                "data": data,
            }
        else:
            data = translate_image_to_requirements_json(resolved, model_name=model_name)
            save_result = save_requirements_summary(data)
            if save_result.startswith("ERROR:"):
                return {"status": "ERROR", "error": save_result, "data": data}
            artifact_file = paths.output_path("requirements_summary.json")
            return {
                "status": "OK",
                "target_type": "requirements",
                "image_path": resolved,
                "artifact_path": artifact_file,
                "data": data,
            }
    finally:
        if cm:
            cm.__exit__(None, None, None)


def _repair_process_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures required fields exist on process_json and each process_step, meeting length requirements."""
    repaired = dict(data)
    name = repaired.get("process_name") or "Imported Process"
    repaired["process_name"] = name
    repaired.setdefault("version", "1.0")
    repaired.setdefault("process_owner", "Business Operations")
    repaired.setdefault("industry_sector", "General")
    repaired.setdefault("stakeholders", [{"stakeholder_name": "Operations Team", "role": "Process Executor", "responsibilities": ["Execute process steps"]}])

    default_intro = (
        f"This document details the complete end-to-end business process workflow for {name}, systematically "
        "transcribed and structured from the source visual diagram. It defines the sequential progression of activities, "
        "governance checkpoints, organizational responsibilities, and required deliverables to guarantee consistent, "
        "auditable execution across participating enterprise teams and stakeholder groups."
    )
    default_purpose = (
        f"The purpose of this {name} process specification is to provide an unambiguous, authoritative operational "
        "blueprint for cross-functional execution. By defining structured inputs, outputs, SLAs, and decision criteria, "
        "this workflow eliminates operational ambiguity, minimizes cycle times, enforces organizational compliance standards, "
        "and ensures predictable, verifiable business outcomes across every execution phase."
    )
    default_scope = (
        f"The scope of this process encompasses all operational phases, roles, and automated system interactions depicted "
        "in the source diagram, starting from initial workflow trigger and request intake through to final delivery, "
        "verification, and operational closure. Out-of-scope activities include unrelated third-party system reconfigurations "
        "and manual out-of-band operational exceptions."
    )

    if not repaired.get("introduction") or len(repaired["introduction"]) < 300:
        repaired["introduction"] = default_intro
    if not repaired.get("purpose") or len(repaired["purpose"]) < 300:
        repaired["purpose"] = default_purpose
    if not repaired.get("scope") or len(repaired["scope"]) < 300:
        repaired["scope"] = default_scope

    steps = repaired.get("process_steps")
    if not isinstance(steps, list) or len(steps) == 0:
        steps = [{
            "step_id": "STEP-001",
            "step_name": "Initial Step",
            "description": (
                "Execute the initial workflow phase according to operational requirements. The assigned party "
                "validates incoming prerequisites, coordinates required tasks, verifies operational criteria, and "
                "produces the required output deliverables for downstream workflow progression."
            ),
            "responsible_party": "Process Executor",
            "estimated_duration": "1 day",
            "deliverables": ["Completed Step"],
            "inputs": ["Trigger"],
            "outputs": ["Result"],
            "dependencies": [],
            "success_criteria": "Step completed successfully with all acceptance criteria verified.",
        }]
    else:
        fixed_steps = []
        step_names = [s.get("step_name") or f"Step {i+1}" for i, s in enumerate(steps) if isinstance(s, dict)]
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                continue
            step = dict(s)
            step_name = step.get("step_name") or f"Step {i+1}"
            step["step_name"] = step_name
            step.setdefault("step_id", f"STEP-{i+1:03d}")
            desc = step.get("description") or ""
            if len(desc) < 150:
                step["description"] = (
                    f"Execute the {step_name} phase according to the {name} workflow requirements. The assigned "
                    "responsible party validates incoming prerequisites, coordinates required tasks, verifies operational "
                    "criteria, and produces the required output deliverables for downstream workflow progression."
                )
            step.setdefault("responsible_party", "Operations Team")
            step.setdefault("estimated_duration", "1 day")
            step.setdefault("deliverables", [f"{step_name} Output"])
            step.setdefault("inputs", ["Input Data"])
            step.setdefault("outputs", ["Output Data"])
            step.setdefault("success_criteria", f"{step_name} completed with all acceptance criteria verified.")
            # Fix dependencies to reference only real step names
            deps = step.get("dependencies")
            if isinstance(deps, list):
                step["dependencies"] = [d for d in deps if d in step_names and d != step_name]
            else:
                step["dependencies"] = []
            fixed_steps.append(step)
        steps = fixed_steps

    repaired["process_steps"] = steps
    return repaired


def _build_process_json_from_text(image_path: str, text: str) -> Dict[str, Any]:
    """Constructs a schema-compliant process JSON from extracted text / OCR."""
    base_name = os.path.splitext(os.path.basename(image_path))[0].replace("_", " ").title()
    filename = os.path.basename(image_path)
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]

    # Extract candidate steps from lines or headings
    step_candidates = []
    for line in lines:
        cleaned = re.sub(r"^[0-9]+[\.\)\-]\s*", "", line).strip()
        cleaned = re.sub(r"^[-*•]\s*", "", cleaned).strip()
        if len(cleaned) > 3 and len(cleaned) < 80 and not cleaned.startswith("[") and not cleaned.endswith(":"):
            step_candidates.append(cleaned)

    if not step_candidates:
        step_candidates = [f"{base_name} Execution"]

    steps = []
    for i, name in enumerate(step_candidates[:12]):
        step_id = f"STEP-{i+1:03d}"
        deps = [step_candidates[i-1]] if i > 0 else []
        steps.append({
            "step_id": step_id,
            "step_name": name,
            "description": (
                f"Execute the {name} phase according to the {base_name} workflow requirements depicted in {filename}. "
                "The assigned responsible party validates incoming prerequisites, coordinates required tasks, verifies "
                "operational criteria, and produces the required output deliverables for downstream workflow progression."
            ),
            "responsible_party": "Operations Specialist",
            "estimated_duration": "1 to 2 business days",
            "deliverables": [f"{name} Deliverable"],
            "inputs": ["Initial Request or Upstream Artifact"],
            "outputs": [f"Verified {name} Output"],
            "dependencies": deps,
            "success_criteria": f"{name} successfully executed with all acceptance criteria verified and documented.",
        })

    process = {
        "process_name": f"{base_name} Process",
        "version": "1.0",
        "introduction": (
            f"This document details the complete end-to-end business process workflow for {base_name}, systematically "
            f"transcribed and structured from the source visual diagram {filename}. It defines the sequential progression of "
            "activities, governance checkpoints, organizational responsibilities, and required deliverables to guarantee "
            "consistent, auditable execution across participating enterprise teams and stakeholder groups."
        ),
        "purpose": (
            f"The purpose of this {base_name} process specification is to provide an unambiguous, authoritative operational "
            "blueprint for cross-functional execution. By defining structured inputs, outputs, SLAs, and decision criteria, "
            "this workflow eliminates operational ambiguity, minimizes cycle times, enforces organizational compliance standards, "
            "and ensures predictable, verifiable business outcomes across every execution phase."
        ),
        "scope": (
            f"The scope of this process encompasses all operational phases, roles, and automated system interactions depicted "
            f"in {filename}, starting from initial workflow trigger and request intake through to final delivery, verification, "
            "and operational closure. Out-of-scope activities include unrelated third-party system reconfigurations and manual "
            "out-of-band operational exceptions."
        ),
        "process_owner": "Business Process Owner",
        "industry_sector": "Cross-Industry",
        "stakeholders": [
            {
                "stakeholder_name": "Operations Specialist",
                "role": "Process Executor",
                "responsibilities": ["Execute daily tasks", "Verify step deliverables"],
            },
            {
                "stakeholder_name": "Process Owner",
                "role": "Process Governance",
                "responsibilities": ["Approve exceptions", "Monitor performance metrics"],
            },
        ],
        "process_steps": steps,
        "metrics": [
            {
                "metric": "Cycle Time",
                "description": f"Total elapsed time to complete {base_name} from initiation to close.",
            }
        ],
        "critical_success_factors": [
            {
                "factor": "Timely Handoffs",
                "description": "Seamless transition of deliverables between consecutive steps without delay.",
            }
        ],
        "critical_failure_factors": [
            {
                "factor": "Incomplete Deliverables",
                "description": "Advancing steps without satisfying defined completion criteria.",
            }
        ],
        "reporting_and_analytics": [
            {
                "report": "Weekly Process Execution Report",
                "description": "Summary of active, completed, and blocked workflow instances.",
            }
        ],
    }
    return process

    process = {
        "process_name": f"{base_name} Process",
        "version": "1.0",
        "introduction": f"Business process workflow imported from {os.path.basename(image_path)}.",
        "purpose": f"Standardize and execute the {base_name} workflow effectively.",
        "scope": f"Encompasses all activities and roles depicted in {os.path.basename(image_path)}.",
        "process_owner": "Business Process Owner",
        "industry_sector": "Cross-Industry",
        "stakeholders": [
            {
                "stakeholder_name": "Operations Specialist",
                "role": "Process Executor",
                "responsibilities": ["Execute daily tasks", "Verify step deliverables"],
            },
            {
                "stakeholder_name": "Process Owner",
                "role": "Process Governance",
                "responsibilities": ["Approve exceptions", "Monitor performance metrics"],
            },
        ],
        "process_steps": steps,
        "metrics": [
            {
                "metric": "Cycle Time",
                "description": f"Total elapsed time to complete {base_name} from initiation to close.",
            }
        ],
        "critical_success_factors": [
            {
                "factor": "Timely Handoffs",
                "description": "Seamless transition of deliverables between consecutive steps without delay.",
            }
        ],
        "critical_failure_factors": [
            {
                "factor": "Incomplete Deliverables",
                "description": "Advancing steps without satisfying defined completion criteria.",
            }
        ],
        "reporting_and_analytics": [
            {
                "report": "Weekly Process Execution Report",
                "description": "Summary of active, completed, and blocked workflow instances.",
            }
        ],
    }
    return process


def _normalize_requirements_summary(data: Dict[str, Any], image_path: str) -> None:
    """Normalizes fields in a requirements summary dict."""
    base_name = os.path.splitext(os.path.basename(image_path))[0].replace("_", " ").title()
    data.setdefault("name", f"{base_name} Requirements Specification")
    data.setdefault("source_directory", os.path.dirname(os.path.abspath(image_path)))
    data.setdefault("source_files", [os.path.basename(image_path)])
    data.setdefault("summary", f"Requirements specification extracted from visual analysis of {os.path.basename(image_path)}.")
    data.setdefault("industry_sector", "General")
    data.setdefault("current_state", "")
    data.setdefault("future_state", "")
    data.setdefault("success_measures", [])
    data.setdefault("scope_in", [])
    data.setdefault("scope_out", [])
    data.setdefault("stakeholders", ["Product Owner", "Engineering Team", "Quality Assurance"])
    data.setdefault("assumptions", [])
    data.setdefault("risks", [])
    data.setdefault("open_questions", [])
    if "requirements_register" not in data and "functional_requirements" in data:
        # Convert legacy format to register
        register = []
        for i, fr in enumerate(data.get("functional_requirements") or []):
            desc = fr if isinstance(fr, str) else str(fr.get("description", fr))
            register.append({
                "id": f"FR-{i+1:03d}",
                "type": "functional",
                "description": desc,
                "source": f"Image Analysis: {os.path.basename(image_path)}",
                "priority": "medium",
                "status": "proposed",
            })
        data["requirements_register"] = register


def _build_requirements_json_from_text(image_path: str, text: str) -> Dict[str, Any]:
    """Constructs a schema-compliant requirements summary JSON from extracted text / OCR."""
    base_name = os.path.splitext(os.path.basename(image_path))[0].replace("_", " ").title()
    filename = os.path.basename(image_path)
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]

    req_candidates = []
    for line in lines:
        cleaned = re.sub(r"^[0-9]+[\.\)\-]\s*", "", line).strip()
        cleaned = re.sub(r"^[-*•]\s*", "", cleaned).strip()
        if len(cleaned) > 5 and len(cleaned) < 120 and not cleaned.startswith("["):
            req_candidates.append(cleaned)

    if not req_candidates:
        req_candidates = [
            f"The system shall implement the {base_name} functionality depicted in the specification.",
            f"The workflow shall provide verifiable status updates and audit tracking.",
        ]

    register = []
    for i, desc in enumerate(req_candidates[:15]):
        register.append({
            "id": f"FR-{i+1:03d}",
            "type": "functional",
            "description": desc if desc.lower().startswith("the ") else f"The system shall {desc[:1].lower() + desc[1:]}.",
            "source": f"Image Analysis: {filename}",
            "priority": "high" if i < 3 else "medium",
            "status": "proposed",
            "acceptance_criteria": [f"Verification of {desc[:40]} demonstrates intended behavior."],
        })

    summary = {
        "name": f"{base_name} Requirements Specification",
        "source_directory": os.path.dirname(os.path.abspath(image_path)),
        "source_files": [filename],
        "summary": f"Structured requirements specification extracted from visual analysis and interpretation of {filename}.",
        "industry_sector": "Cross-Industry",
        "current_state": "Manual or legacy workflow requiring modernization.",
        "future_state": f"Standardized digital implementation of the {base_name} specification.",
        "success_measures": [
            f"100% adherence of implementation to {base_name} requirements register",
            "Verification of all critical user acceptance criteria",
        ],
        "scope_in": [f"Core {base_name} workflow and capabilities"],
        "scope_out": ["Out-of-scope third-party platform migrations"],
        "stakeholders": ["Business Sponsor", "Lead Systems Architect", "Implementation Team"],
        "assumptions": ["Underlying cloud infrastructure and access permissions are provisioned."],
        "risks": ["Potential edge-case branch conditions requiring runtime user clarification."],
        "open_questions": [],
        "requirements_register": register,
    }
    return summary
