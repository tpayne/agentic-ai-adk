"""Shared sly_data key convention for threading a process_toolkit.run_lock
token between a pipeline's reset step (which acquires the lock) and its
own finalize step (which releases it) -- separate CodedTool classes,
possibly in different coded_tools/<network>/ packages, but the same
session's sly_data dict is handed to every tool call within it, so a key
written by one is readable by the other.
"""

PIPELINE_LOCK_TOKEN_KEY = "_pipeline_lock_token"
