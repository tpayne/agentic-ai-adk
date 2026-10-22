import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.schema.design_json import load_master_design_json


class LoadMasterDesignJsonCodedTool(CodedTool):
    """Loads output/design_data.json (or the empty template if none exists
    yet), for supporting narrative context (what the diagram was generated
    from, if any) -- the diagram's own XML remains the source of truth for
    what actually exists in it.

    Deliberately pinned to the design schema only, with no schema_type
    argument -- a cloud architecture diagram is always generated from a
    design document's components/dependencies/integration points, never
    from a business process. Confirmed directly against a real session:
    the previous shared loader here (load_master_process_json_tool,
    schema_type=None) auto-detects by most-recent file modification time
    when both process_data.json and design_data.json exist in output/,
    which silently grounds a NEW cloud architecture request in whichever
    document was touched most recently -- an unrelated process document,
    if that's what the user worked on just before asking for a diagram."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_master_design_json()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
