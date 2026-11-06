"""CodedTool: split a large piece of combined source text (serialized
requirements/design/cloud-architecture content, not a file on disk) into
bounded, token-budgeted, untrusted-data-wrapped chunks for a map-reduce
test-case generation pass -- the same mechanism load_directory_context
uses for a directory's own combined extracted text, but for an agent
that built its own combined text from already-loaded JSON/XML rather
than reading files itself.

Logic lives in process_toolkit.ingestion.chunking.chunk_and_wrap (shared
with the ADK port and with load_directory_context's own chunking).
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.ingestion.chunking import chunk_and_wrap


class ChunkSourceMaterialCodedTool(CodedTool):
    """Splits `text` into chunks of at most `max_tokens` tokens (default
    30000), each wrapped in an explicit untrusted-data boundary, capped
    at `max_chunks` (default 20) total."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return "ERROR: text must be a non-empty string."
        max_tokens = args.get("max_tokens") or 30000
        overlap_tokens = args.get("overlap_tokens") or 200
        max_chunks = args.get("max_chunks") or 20
        return chunk_and_wrap(
            text, max_tokens=max_tokens, overlap_tokens=overlap_tokens, max_chunks=max_chunks,
        )

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
