import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.master_json import load_master_json


class LoadMasterProcessJsonCodedTool(CodedTool):
    """Loads whichever of output/process_data.json or output/design_data.json
    exists, for supporting narrative context (what the diagram was generated
    from, if anything) -- the diagram's own XML remains the source of truth
    for what actually exists in it."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_master_json()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
