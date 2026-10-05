"""CodedTool wrapper for load_directory_context, resolvable from the
requirements_summary network (neuro-san resolves a HOCON "class" entry
relative to coded_tools/<network_name>/, so this thin wrapper lives here
even though the real logic is shared from coded_tools/common/).
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.directory_extractors import load_directory_context


class LoadDirectoryContextCodedTool(CodedTool):
    """Reads every supported file directly inside a directory and returns
    their combined extracted text, for use as requirements source material."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        directory = args.get("directory")
        if not directory:
            return {"status": "ERROR", "error": "Missing required argument: directory"}
        return load_directory_context(directory)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
