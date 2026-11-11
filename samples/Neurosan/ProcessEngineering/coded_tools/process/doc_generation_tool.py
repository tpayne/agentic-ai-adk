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
    flow diagram -> THIS) -- releases the shared output/ directory's
    pipeline lock (see process_toolkit.run_lock) UNCONDITIONALLY, success
    or failure. release_pipeline_lock(None) is a safe no-op for any OTHER
    caller that never acquired a lock in the first place (none currently
    does).

    CONFIRMED PRODUCTION BUG (data corruption) on the design-document
    equivalent of this tool, fixed here too: releasing only on a
    "SUCCESS:"-prefixed result leaves the lock stuck -- for up to
    run_lock.DEFAULT_STALE_AFTER_SECONDS (20 minutes) -- on any exception
    or legitimate non-SUCCESS return. A `finally` block guarantees the
    release always fires, matching the ADK port's own equivalent fix
    (process_agents.common.utils_agent.release_pipeline_lock_after_run)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
        try:
            process_name = args.get("process_name") or "Process"
            return create_standard_doc_from_file(process_name, schema_type="process")
        finally:
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
