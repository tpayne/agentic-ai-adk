"""CodedTool surfacing sly_data["attached_files"] -- set by cli.py's
POST /chat and /chat/stream routes when the user attaches one or more
files to a message (see ChatSession._ingest_attachments in cli.py) -- to
the cloudarch agent network.

sly_data is intentionally invisible to the LLM's own prompt (see
chat.proto's own ChatMessage.sly_data field comment: its keys may appear
in the chat stream, but "the data itself does not") -- a CodedTool
explicitly calling for it, and returning its content as a tool result, is
the only way this content actually reaches the agent. Same mechanism
load_directory_context/load_requirements_summary already use for getting
file content to the LLM.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

ATTACHED_FILES_SLY_DATA_KEY = "attached_files"


class LoadAttachedFilesCodedTool(CodedTool):
    """Returns the text extracted from any file(s) the user attached to
    this conversation, if any -- {"status": "NONE"} when nothing was
    attached (a cheap, safe no-op to call unconditionally every turn), or
    {"status": "OK", "files": [{"name", "mime_type", "status", "text" or
    "reason"}, ...]} -- one entry per attached file, "status": "OK" with
    extracted "text", or "status": "UNSUPPORTED" with a human-readable
    "reason" (e.g. an attached image has no text to extract at all)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        files = sly_data.get(ATTACHED_FILES_SLY_DATA_KEY) if isinstance(sly_data, dict) else None
        if not files:
            return {"status": "NONE"}
        return {"status": "OK", "files": files}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
