"""Always-local re-export -- load_directory_context reads an arbitrary,
caller-chosen local directory (the user's own source-document folder),
not the canonical session/output state; stage_attachments_to_directory
writes to an equally caller-chosen local path. Neither is portable to a
remote MCP server unless that server's filesystem happens to be
co-located with the caller's own input directory, which this phase
doesn't assume -- so these stay always-local, same reasoning as paths.py.
"""

from process_toolkit.ingestion.extractors import load_directory_context, stage_attachments_to_directory

__all__ = ["load_directory_context", "stage_attachments_to_directory"]
