# process_agents/design/import_agent.py
#
# Imports an ALREADY-EXISTING architectural/technical design document (HLD,
# LLD, or Combined) from a directory of source files directly into this
# toolkit's own design JSON schema -- distinct from the directory-context
# mode embedded in design_doc_create_agent's analysis stage, which treats a
# directory's contents as SUPPLEMENTARY background for a NEW design the
# user describes in the same request. Mirrors the neuro-san port's
# registries/design_import.hocon.

from ..common.utils import (
    load_directory_context,
    load_master_design_json,
    validate_design_json,
    persist_final_design_json,
)
from ..common.agent_wrappers import ProcessLlmAgent

design_import_agent = ProcessLlmAgent(
    name="Design_Import_Agent",
    description=(
        "Reads a directory of source documents (.txt/.md/.docx/.pdf/.eml/.msg/.xls/.xlsx) that "
        "already describe an existing architectural/technical design (HLD, LLD, or Combined), and "
        "imports their content directly into this toolkit's own structured design JSON -- not a "
        "fresh design from a brief, an extraction of what's actually in the documents."
    ),
    instruction_file="design/import_agent.txt",
    tools=[load_directory_context, load_master_design_json, validate_design_json, persist_final_design_json],
)
