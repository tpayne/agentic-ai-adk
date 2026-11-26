"""Switchable and local re-exports:
- load_directory_context reads an arbitrary caller-chosen local directory
- stage_attachments_to_directory stages attachments to a caller-chosen local path
- import_image runs locally in local mode; in MCP mode (PROCESS_TOOLKIT_MODE=mcp),
  it base64-encodes the image and delegates to the MCP server's import_image tool,
  mirroring the resulting process_data.json or requirements_summary.json locally.
"""

import base64
import os
from typing import Any, Dict, Optional

from process_toolkit.ingestion.extractors import (
    import_image as _toolkit_import_image,
    interpret_image_with_model,
    load_directory_context,
    stage_attachments_to_directory,
    translate_image_to_cloudarch_drawio,
    translate_image_to_process_json,
    translate_image_to_requirements_json,
)
from process_interface import _transport, config, paths
from process_interface.schema._common import mirror_local_copy

__all__ = [
    "import_image",
    "interpret_image_with_model",
    "load_directory_context",
    "stage_attachments_to_directory",
    "translate_image_to_cloudarch_drawio",
    "translate_image_to_process_json",
    "translate_image_to_requirements_json",
]


def import_image(
    path: str,
    target_type: str = "process",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Switchable import_image: runs locally in local mode; in MCP mode,
    base64-encodes the image, delegates to the MCP server's import_image tool,
    and mirrors the produced JSON or XML locally."""
    if not config.is_mcp_mode():
        return _toolkit_import_image(path, target_type=target_type, session_id=session_id)

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    filename = os.path.basename(path)
    active_session = session_id or paths.current_session_id()

    result = _transport.call(
        "import_image",
        {
            "image_base64": encoded,
            "filename": filename,
            "target_type": target_type,
            "session_id": active_session,
        },
    )

    if isinstance(result, dict) and result.get("status") == "OK":
        if target_type == "process" and isinstance(result.get("data"), dict):
            try:
                mirror_local_copy("process_data.json", result["data"])
            except Exception:
                pass
        elif target_type == "requirements" and isinstance(result.get("data"), dict):
            try:
                mirror_local_copy("requirements_summary.json", result["data"])
            except Exception:
                pass
        elif target_type in ("cloudarch", "architecture", "drawio"):
            xml_data = result.get("xml")
            if not xml_data and isinstance(result.get("data"), dict):
                xml_data = result["data"].get("xml")
            if xml_data and isinstance(xml_data, str):
                try:
                    xml_path = paths.output_path("cloudarch_drawio.xml")
                    out_dir = os.path.dirname(xml_path)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                    with open(xml_path, "w", encoding="utf-8") as f:
                        f.write(xml_data)
                except Exception:
                    pass

    return result
