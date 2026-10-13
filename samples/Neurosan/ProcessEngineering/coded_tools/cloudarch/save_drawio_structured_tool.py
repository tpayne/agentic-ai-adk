"""CodedTool: build + persist a cloud architecture diagram from structured
content (zones/components/edges, no coordinates) via the deterministic
layout engine. Ported from the ADK sample's save_drawio_structured
(utils.py), which itself just calls build_structured_drawio_xml then
persists the result.
"""

import asyncio
import traceback
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.cloudarch.layout import build_structured_drawio_xml
from coded_tools.common.drawio_persistence import save_drawio_xml


class SaveDrawioStructuredCodedTool(CodedTool):
    """Builds and saves a cloud architecture diagram from structured
    zones/components/edges content -- see cloudarch.hocon's own tool
    description for the full schema; this class just wires the call
    through to the layout engine then persists the result."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        try:
            xml_content = build_structured_drawio_xml(
                title=args.get("title", ""),
                subtitle=args.get("subtitle") or None,
                zones=args.get("zones") or [],
                components=args.get("components") or [],
                edges=args.get("edges") or [],
            )
        except Exception as e:
            return {
                "status": "ERROR",
                "error": (
                    f"Failed to build the diagram from the structured input -- {e}. "
                    "Check that every zone id and every component id is unique across "
                    "the whole diagram, that every component's zone_id references a "
                    "real zone id, and that every edge's source/target reference real "
                    "component or zone ids."
                ),
                "trace": traceback.format_exc(),
            }

        return save_drawio_xml(xml_content)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
