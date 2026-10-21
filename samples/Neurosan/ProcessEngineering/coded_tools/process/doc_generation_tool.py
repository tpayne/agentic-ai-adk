import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.generation import create_standard_doc_from_file
from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY


class GenerateProcessDocumentCodedTool(CodedTool):
    """Generates a structured, ISO-formatted Word document from the current
    process design JSON. "process_name" is an optional fallback title --
    the design JSON's own "process_name" field takes precedence.

    This is process.hocon/process_update.hocon's own genuine last step
    (reset_loop_state -> generate/review loop -> subprocess expansion ->
    flow diagram -> THIS) -- on success, also releases the shared output/
    directory's pipeline lock (see process_toolkit.run_lock).
    release_pipeline_lock(None) is a safe no-op for any OTHER caller that
    never acquired a lock in the first place (none currently does)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        process_name = args.get("process_name") or "Process"
        result = create_standard_doc_from_file(process_name, schema_type="process")
        if isinstance(result, str) and result.startswith("SUCCESS:"):
            token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)
        return result

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
