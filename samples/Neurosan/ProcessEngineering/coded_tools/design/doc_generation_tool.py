import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.generation import create_standard_doc_from_file
from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY


class GenerateDesignDocumentCodedTool(CodedTool):
    """Generates a structured, ISO-formatted Word document from the
    current design-document JSON. "process_name" is an optional fallback
    title -- the design JSON's own document_metadata.title/system_name
    takes precedence. "design_variant" ("hld"|"lld"|"both", default
    "both") selects which document(s) to render -- design generation now
    always produces the HLD and LLD as two SEPARATE documents rather than
    one combined file (see process_toolkit.docgen.generation's own
    _build_design_documents).

    This is design.hocon/design_update.hocon's own genuine last step
    (reset_loop_state -> generate/review loop -> flow diagram -> THIS) --
    releases the shared output/ directory's pipeline lock (see
    process_toolkit.run_lock) UNCONDITIONALLY, success or failure.
    release_pipeline_lock(None) is a safe no-op for any OTHER caller that
    never acquired a lock in the first place (none currently does).

    CONFIRMED PRODUCTION BUG (data corruption), fixed here: this used to
    release the lock ONLY when `result` started with "SUCCESS:" -- an
    exception from create_standard_doc_from_file, or any of its own
    legitimate "ERROR: ..." returns (e.g. _resolve_design_variant's own
    explicit LLD-with-no-low_level_design-content case), left the lock
    stuck for up to run_lock.DEFAULT_STALE_AFTER_SECONDS (20 minutes) --
    refusing every later request against this output/ directory with
    "another pipeline run is already in progress" for that whole window.
    Confirmed directly: this is also what let TWO genuinely concurrent
    runs interleave their writes to design_data.json in the first place
    (the run_lock module's own documented corruption scenario) -- the
    losing run's own generate_design_document call never reached a
    "SUCCESS:" string (its write collided with the other run's), so its
    lock was never released either, and the next request after that
    inherited a stuck lock instead of a clean error. A `finally` block
    guarantees the release always fires, on every exit path, matching
    the ADK port's own equivalent fix (process_agents.common.utils_agent.
    release_pipeline_lock_after_run)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
        try:
            fallback_name = args.get("process_name") or "Design"
            return create_standard_doc_from_file(
                fallback_name, schema_type="design", design_variant=args.get("design_variant"),
            )
        finally:
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
