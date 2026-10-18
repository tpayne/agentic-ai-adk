"""Shared sly_data key names for passing data between cli.py's web
service (which populates them) and CodedTools (which read them).

sly_data is intentionally invisible to the LLM's own prompt (see
chat.proto's own ChatMessage.sly_data field comment: its keys may appear
in the chat stream, but "the data itself does not") -- a CodedTool
explicitly reading one of these keys is the only way its content
actually reaches the agent. The key name itself is therefore a real
contract between two independently-loaded modules (cli.py, and whichever
CodedTool reads it) -- defining it in exactly one place means a typo or
a future rename can't silently desynchronize producer and consumer.
"""

# Set by cli.py's ChatSession._ingest_attachments; read by
# coded_tools/cloudarch/load_attached_files_tool.py.
ATTACHED_FILES_SLY_DATA_KEY = "attached_files"
