# process_agents/process/import_agent.py
#
# Imports an ALREADY-EXISTING business process document from a directory of
# source files directly into this toolkit's own process JSON schema --
# distinct from the directory-context mode embedded in create_process_agent's
# analysis stage, which treats a directory's contents as SUPPLEMENTARY
# background for a NEW process the user describes in the same request.
# Mirrors the neuro-san port's registries/process_import.hocon.

from ..common.utils import (
    load_directory_context,
    load_master_process_json,
    validate_process_json,
    persist_final_json,
)
from ..common.agent_wrappers import ProcessLlmAgent

process_import_agent = ProcessLlmAgent(
    name="Process_Import_Agent",
    description=(
        "Reads a directory of source documents (.txt/.md/.docx/.pdf/.eml/.msg/.xls/.xlsx) that "
        "already describe an existing business process, and imports their content directly into "
        "this toolkit's own structured process JSON -- not a fresh design from a brief, an "
        "extraction of what's actually in the documents."
    ),
    instruction_file="process/import_agent.txt",
    tools=[load_directory_context, load_master_process_json, validate_process_json, persist_final_json],
)
