"""Standalone "regenerate just the diagram" support -- see
doc_generation_tool.py's own module docstring for why this is a genuinely
separate implementation rather than a re-export of
coded_tools.process.edge_inference_tool.GenerateProcessFlowDiagramCodedTool
(which is hard-pinned to schema_type="process", wrong for this network's
own "regenerate whichever document applies" job -- a design-only request
routed through that pinned class would silently regenerate a PROCESS
diagram instead)."""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.edge_inference import generate_clean_diagram


class RegenerateFlowDiagramCodedTool(CodedTool):
    """Regenerates the flow/architecture diagram from whichever process/
    design JSON is already saved on disk. Pass {"schema_type":
    "process"|"design"} when the caller already knows which one the user
    asked for (e.g. "regenerate the DESIGN document"); omit it to
    auto-detect from whichever file is actually on disk -- correct only
    when at most one of the two exists, since the auto-detect fallback
    always resolves to "process" whenever both do."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return generate_clean_diagram(schema_type=args.get("schema_type"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
