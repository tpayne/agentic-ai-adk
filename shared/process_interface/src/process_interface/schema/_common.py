"""Shared helper for the three persist-capable schema modules
(design_json, togaf_json, process_json). process_toolkit's own
persist_final_*_json functions accept either an already-parsed dict or a
raw JSON string (coercing the latter internally) and short-circuit on
empty content -- pure, local checks that must happen identically in both
local and mcp mode, since the MCP server's persist_json tool declares its
`data` parameter as a dict and sending it a raw string would be a schema
mismatch at the transport layer, not the clear "ERROR: ..."/"INFO: ..."
message process_toolkit's own callers already expect.
"""

import json
from typing import Any, Optional, Tuple

from process_interface import paths


def mirror_local_copy(filename: str, data: dict) -> None:
    """After a successful remote persist_json call, also writes `data` to
    the same local filename process_toolkit's own persist_final_*_json
    would have used. Needed because detect_schema_type_from_disk (an
    always-local convenience fallback the real "regenerate whichever
    document already exists" caller relies on) reads design_data.json/
    process_data.json directly off local disk, bypassing load_master_*_
    json/load_full_*_context entirely -- those two DO redirect to the MCP
    server's load_context tool, but a raw os.path.exists/mtime check
    doesn't go through them at all."""
    with open(paths.output_path(filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def coerce_json_content(json_content: Any) -> Tuple[Optional[dict], Optional[str]]:
    """Returns (dict, None) on success, or (None, message) for the two
    cases process_toolkit's own persist_final_*_json functions handle
    before ever touching disk: empty content ("INFO: ...") and an
    unparseable string ("ERROR: ...")."""
    if not json_content or (isinstance(json_content, dict) and len(json_content) == 0):
        return None, "INFO: No JSON content provided, so nothing has been done."

    if isinstance(json_content, str):
        try:
            json_content = json.loads(json_content)
        except Exception as e:
            return None, f"ERROR: Could not parse JSON content: {e}"

    return json_content, None
