# process_agents/itsm/import_agent.py
#
# Imports an ALREADY-EXISTING ITSM process document from a directory of
# source files directly into this toolkit's own itsm_data.json schema --
# distinct from the directory-context mode embedded in
# create_itsm_agent's analysis stage, which treats a directory's contents
# as SUPPLEMENTARY background for a NEW ITSM process document the user
# describes in the same request. Mirrors process/import_agent.py /
# design/import_agent.py. TOGAF has no equivalent at all, so this has no
# TOGAF precedent to mirror -- only process/design's.

from ..common.utils import (
    load_directory_context,
    load_master_itsm_json,
    validate_itsm_json,
    persist_final_itsm_json,
)
from ..common.agent_wrappers import ProcessLlmAgent

itsm_import_agent = ProcessLlmAgent(
    name="ITSM_Import_Agent",
    description=(
        "Reads a directory of source documents (.txt/.md/.docx/.pptx/.pdf/.eml/.msg/.xls/.xlsx/.xml/"
        ".json/.vsdx/.vsdm, plus images [.png/.jpg/.jpeg/.gif/.webp/.bmp/.tiff] -- OCR'd visible text "
        "only) that already describe an existing ITSM process (runbooks, incident/change/problem "
        "procedures, SLAs, a CMDB export), and imports their content directly into this toolkit's "
        "own structured ITSM JSON -- not a fresh design from a brief, an extraction of what's "
        "actually in the documents."
    ),
    instruction_file="itsm/import_agent.txt",
    tools=[load_directory_context, load_master_itsm_json, validate_itsm_json, persist_final_itsm_json],
)
