"""CodedTool: build + persist a cloud architecture diagram from structured
content (zones/components/edges, no coordinates) via the deterministic
layout engine. Ported from the ADK sample's save_drawio_structured
(utils.py), which itself just calls build_structured_drawio_xml then
persists the result.
"""

import asyncio
import logging
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.cloudarch.layout import build_structured_drawio_xml
from coded_tools.common.drawio_persistence import save_drawio_xml

logger = logging.getLogger("ProcessArchitect.SaveDrawioStructured")


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
                provider=args.get("provider") or "azure",
            )
        except Exception as e:
            # The full traceback is logged server-side only, not
            # returned to the caller -- it previously flowed into
            # neuro-san's own chat/progress stream as part of this
            # result, which the web client's "Thinking" panel renders
            # verbatim to whoever is watching the turn (file paths,
            # internal function/line detail, no real benefit to an
            # agent that's already told exactly what to check below).
            # None of the other CodedTool wrappers in this directory
            # echo a traceback into their result either. The exception's
            # own short message (e, not the traceback) IS still useful,
            # actionable detail, so that stays in "error" same as before.
            logger.exception("Failed to build the diagram from structured input.")
            return {
                "status": "ERROR",
                "error": (
                    f"Failed to build the diagram from the structured input -- {e}. "
                    "Check that every zone id and every component id is unique across "
                    "the whole diagram, that every component's zone_id references a "
                    "real zone id, and that every edge's source/target reference real "
                    "component or zone ids. Check logs for the full error."
                ),
            }

        return save_drawio_xml(xml_content)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
