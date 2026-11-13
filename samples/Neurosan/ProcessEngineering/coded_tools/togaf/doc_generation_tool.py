import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.generation import create_standard_doc_from_file
from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY


class GenerateTogafDocumentCodedTool(CodedTool):
    """Generates the TOGAF architecture artifact Word document(s) from the
    current TOGAF JSON. "process_name" is an optional fallback title --
    the TOGAF JSON's own document_metadata.title/system_name takes
    precedence. "togaf_variant" ("vision"|"definition"|"both", default
    "both") selects which document(s) to render -- the Architecture
    Vision Document and the Architecture Definition Document are always
    SEPARATE documents (see process_toolkit.docgen.generation's own
    _build_togaf_documents).

    This is togaf.hocon's own genuine last step (reset_loop_state ->
    generate/review loop -> THIS) -- releases the shared output/
    directory's pipeline lock (see process_toolkit.run_lock)
    UNCONDITIONALLY, success or failure, in a `finally` block -- same
    confirmed-bug precedent as coded_tools/design/doc_generation_tool.py's
    own GenerateDesignDocumentCodedTool (releasing only on a "SUCCESS:"
    string left the lock stuck for up to DEFAULT_STALE_AFTER_SECONDS on
    any error path)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
        try:
            fallback_name = args.get("process_name") or "TOGAF Architecture"
            return create_standard_doc_from_file(
                fallback_name, schema_type="togaf", togaf_variant=args.get("togaf_variant"),
            )
        finally:
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
