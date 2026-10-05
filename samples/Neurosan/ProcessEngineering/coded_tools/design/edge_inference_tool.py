import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.docgen.edge_inference import generate_clean_diagram


class GenerateDesignFlowDiagramCodedTool(CodedTool):
    """Infers a component/integration diagram from the current design
    document and renders it to output/<name>_flow.png. Takes no
    meaningful arguments -- it loads the baseline itself and dispatches
    on whichever schema (process/design) is actually on disk."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return generate_clean_diagram()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
