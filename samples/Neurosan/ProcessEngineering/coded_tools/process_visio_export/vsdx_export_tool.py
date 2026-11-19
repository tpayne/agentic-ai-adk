"""Standalone "export the process/design flow diagram as Visio" support --
developed in tandem with samples/GCP/ProcessEngineering's own
Visio_Export_Agent. Reads whatever process/design JSON is already saved on
disk; never re-runs analysis, design generation, or review, and never
modifies the saved JSON itself -- same discipline as process_subprocess_
regenerate/regenerate_document's own standalone actions."""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_interface.docgen.vsdx_export import build_process_design_vsdx


class ExportProcessDesignVsdxCodedTool(CodedTool):
    """Exports the current saved process/design flow diagram as a Visio
    (.vsdx) file. Pass {"schema_type": "process"|"design"} -- the
    front-man determines this from the user's own request wording, the
    same way Regenerate_Document_Agent determines it for "regenerate the
    document"."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        schema_type = args.get("schema_type")
        if schema_type not in ("process", "design"):
            return "ERROR: schema_type must be 'process' or 'design'."
        return build_process_design_vsdx(schema_type)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
