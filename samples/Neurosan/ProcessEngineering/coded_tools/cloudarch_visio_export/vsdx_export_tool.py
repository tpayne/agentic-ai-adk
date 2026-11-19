"""Standalone "export the cloud architecture diagram as Visio" support --
reads whatever cloudarch_drawio.xml is already saved on disk; never
re-runs the cloudarch generate/review loop, and never modifies the saved
diagram itself."""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_interface.docgen.vsdx_export import build_cloudarch_vsdx


class ExportCloudarchVsdxCodedTool(CodedTool):
    """Exports the current saved cloud architecture diagram as a Visio
    (.vsdx) file. Takes no meaningful arguments."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return build_cloudarch_vsdx()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
