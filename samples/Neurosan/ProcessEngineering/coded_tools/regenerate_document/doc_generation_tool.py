"""Standalone "regenerate just the document" support -- ports the ADK
original's Create_Doc_Agent (process_agents/common/doc_creation_agent.py):
re-render the flow diagram and final Word document from whatever
process/design JSON is ALREADY saved on disk, with no re-analysis, no
design regeneration, and no compliance/simulation review.

Unlike coded_tools/process/doc_generation_tool.py and
coded_tools/design/doc_generation_tool.py -- which each hardcode their own
schema_type since they only ever run inside their own network's pipeline,
where the domain is already known -- this one passes schema_type=None so
create_standard_doc_from_file auto-detects which JSON file is actually on
disk (process_toolkit.schema.process_json.detect_schema_type_from_disk),
the same way the ADK original's single Create_Doc_Agent "inspects
whichever baseline currently exists" rather than needing the caller to
know in advance.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.generation import create_standard_doc_from_file
from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat
from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY


class RegenerateDocumentCodedTool(CodedTool):
    """Regenerates the final Word document from whichever process/design
    JSON is already saved on disk, auto-detecting which one applies.
    "process_name" is an optional fallback title -- the saved JSON's own
    name/title field takes precedence. Returns "ERROR: ..." (containing
    "No such file") if neither output/process_data.json nor
    output/design_data.json exists yet -- there is nothing to regenerate."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        name = args.get("process_name") or "Process"
        result = create_standard_doc_from_file(name, schema_type=None)
        if isinstance(result, str) and result.startswith("SUCCESS:"):
            token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
            stop_pipeline_lock_heartbeat(token)
            release_pipeline_lock(token)
        return result

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
