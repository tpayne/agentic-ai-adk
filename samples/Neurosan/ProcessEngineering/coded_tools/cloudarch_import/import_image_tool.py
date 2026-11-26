"""CodedTool wrapper: imports an architecture image file (JPG/PNG) into
output/cloudarch_drawio.xml via multimodal interpretation or structured layout.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_interface.ingestion.extractors import import_image


class ImportImageCodedTool(CodedTool):
    """Imports an image file (JPG/PNG) as a cloud architecture diagram (cloudarch_drawio.xml),
    translating it into valid drawio XML via multimodal interpretation or structured layout."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        path = args.get("path") or args.get("image_path") or args.get("file")
        if not path:
            return {"status": "ERROR", "error": "path is required."}
        target_type = args.get("target_type") or "cloudarch"
        return import_image(path, target_type=target_type)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
