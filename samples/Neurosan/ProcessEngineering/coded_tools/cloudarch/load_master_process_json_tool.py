import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.schema.master_json import load_master_json


class LoadMasterProcessJsonCodedTool(CodedTool):
    """Loads output/process_data.json or output/design_data.json, for
    supporting narrative context (what the diagram was generated from, if
    any) -- the diagram's own XML remains the source of truth for what
    actually exists in it.

    Pass {"schema_type": "process"|"design"} when the caller already knows
    which document it wants (e.g. the user's own question names "the
    process" specifically). With no argument, defaults to "design" --
    cloud-architecture context is normally about the design document that
    drove it, and NOT "whichever of the two files was modified most
    recently" (load_master_json's own schema_type=None behavior): that
    mtime tie-break silently grounds an answer in an unrelated process
    document whenever one happens to exist and was touched more recently,
    confirmed directly against a real session where it was."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_master_json(schema_type=args.get("schema_type") or "design")

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
