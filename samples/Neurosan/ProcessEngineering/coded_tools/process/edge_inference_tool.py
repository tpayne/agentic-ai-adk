import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.edge_inference import generate_clean_diagram


class GenerateProcessFlowDiagramCodedTool(CodedTool):
    """Infers a swimlane flow diagram from the current process design and
    renders it to output/<process_name>_flow.png. Takes no meaningful
    arguments -- it loads the baseline itself."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return generate_clean_diagram()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
