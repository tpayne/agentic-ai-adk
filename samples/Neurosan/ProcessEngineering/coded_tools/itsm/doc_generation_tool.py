import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_interface.docgen.generation import create_standard_doc_from_file
from process_interface.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY


class GenerateItsmDocumentCodedTool(CodedTool):
    """Generates the ITSM process Word document from the current ITSM
    JSON. "process_name" is an optional fallback title -- the ITSM JSON's
    own document_metadata.title/system_name takes precedence. Always
    produces exactly ONE document (no Vision/Definition-style variant
    split the way TOGAF has).

    This is itsm.hocon's own genuine last step (reset_loop_state ->
    generate/review loop -> THIS) -- releases the shared output/
    directory's pipeline lock (see process_toolkit.run_lock)
    UNCONDITIONALLY, success or failure, in a `finally` block -- same
    confirmed-bug precedent as coded_tools/togaf/doc_generation_tool.py's
    own GenerateTogafDocumentCodedTool."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
        try:
            fallback_name = args.get("process_name") or "ITSM Process"
            return create_standard_doc_from_file(fallback_name, schema_type="itsm")
        finally:
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
