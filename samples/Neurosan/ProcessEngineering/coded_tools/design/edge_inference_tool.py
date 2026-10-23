import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.edge_inference import generate_clean_diagram


class GenerateDesignFlowDiagramCodedTool(CodedTool):
    """Infers a component/integration diagram from the current design
    document and renders it to output/<name>_flow.png. Takes no
    meaningful arguments -- it loads the baseline itself.

    Pinned to schema_type="design" -- this tool only ever runs inside
    design.hocon's/design_update.hocon's own pipeline, so the domain is
    always known; never left to fall back to disk-based guessing.
    Regression fix: with no schema_type, generate_clean_diagram() resolves
    via detect_schema_type_from_disk(), which always prefers "process"
    whenever BOTH process_data.json and design_data.json exist -- so this
    design pipeline's own diagram step was silently rendering a stale
    PROCESS diagram instead of the design document it had just built,
    every time an unrelated process_data.json also existed in output/."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return generate_clean_diagram(schema_type="design")

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
