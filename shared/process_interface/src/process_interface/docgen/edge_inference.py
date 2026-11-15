"""Switchable -- generate_clean_diagram renders a real .png from the
session's persisted JSON baseline, for "design"/"process" only; every
other schema_type (including None resolving to neither via detect_schema_
type_from_disk) is a pure, side-effect-free early return in process_toolkit
itself, so those cases are delegated to the local function directly even
in MCP mode -- reconstructing their exact message text by hand here would
just be a second, driftable copy of wording process_toolkit already owns.
"""

from typing import Optional

from process_toolkit.docgen.edge_inference import _infer_edges_from_json
from process_toolkit.docgen.edge_inference import generate_clean_diagram as _toolkit_generate
from process_toolkit.schema.process_json import detect_schema_type_from_disk

from process_interface import config, paths, _transport, _artifacts

__all__ = ["generate_clean_diagram", "infer_edges_from_json"]

# Re-exported (without the leading underscore -- process_toolkit's own
# convention marks it private/internal, but one real caller, GCP's
# edge_inference_agent.py's __main__ debug harness, already depends on it
# directly) because it's pure introspection over an already-loaded local
# JSON file -- always-local, same as the rest of this module's non-
# diagram-rendering helpers.
infer_edges_from_json = _infer_edges_from_json


def generate_clean_diagram(schema_type: Optional[str] = None) -> str:
    if not config.is_mcp_mode():
        return _toolkit_generate(schema_type)

    resolved_type = schema_type or detect_schema_type_from_disk()
    if resolved_type not in ("design", "process"):
        # A pure, no-disk-access early return in process_toolkit's own
        # implementation for every other schema_type -- safe to call
        # directly regardless of mode, and the only way to guarantee its
        # exact message wording without duplicating it here.
        return _toolkit_generate(schema_type)

    try:
        result = _transport.call(
            "generate_diagram", {"schema_type": resolved_type, "session_id": paths.current_session_id()}
        )
    except Exception as e:
        return f"ERROR: {e}"

    message = result["message"]
    if message.startswith("SUCCESS"):
        _artifacts.materialize_one(result.get("diagram"))
    return message
