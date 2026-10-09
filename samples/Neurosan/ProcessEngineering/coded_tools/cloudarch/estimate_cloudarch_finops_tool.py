import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.cloudarch.finops import estimate_cloudarch_finops


class EstimateCloudarchFinopsCodedTool(CodedTool):
    """Estimates monthly costs and recommendations for the current diagram.

    Uses public provider catalog rates when a resource has an explicit SKU
    and monthly usage description, retaining heuristic estimates otherwise.
    Loads the diagram itself if no xml_content is passed.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return estimate_cloudarch_finops(args.get("xml_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
