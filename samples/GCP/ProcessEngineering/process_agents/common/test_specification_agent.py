# process_agents/common/test_specification_agent.py
#
# Middle stage of Test_Specification_Pipeline (see
# test_specification_pipeline_agent.py): reads whichever of a saved
# requirements summary, design document, and cloud architecture diagram
# are present (a prior pipeline stage, Ensure_Requirements_Summary_Agent,
# may have just self-extracted the requirements summary from a named
# directory), synthesizes a structured test specification (test cases,
# traceability, coverage gap analysis) validating them, and saves it.
# Does NOT render a document itself, and does NOT produce the user-visible
# reply -- same OUTPUT CONTRACT (STRICT SILENCE) convention as
# requirements_synthesis_agent.py/proposal_response_agent.py; the
# pipeline's own LAST stage (Doc_Creation_Agent) does both, confirmed via
# live testing that a bare "create a test specification" request expects
# an actual rendered document, not just saved JSON (the earlier,
# standalone shape this module briefly had).
#
# Includes the same chunked map-reduce path as Requirements_Summary_Agent
# for large combined source material, via Test_Case_Chunk_Generator_Agent
# (the sibling of Requirements_Chunk_Extractor_Agent) -- except its own
# source material is already-structured saved JSON/XML serialized into one
# string, not files read from a directory, so chunk_source_material
# (chunk_and_wrap, re-exported under this task-specific name) is called
# directly rather than via load_directory_context's own chunking.

from google.genai import types
from google.adk.tools import AgentTool

from ..common.utils import (
    load_requirements_summary,
    load_full_design_context,
    load_drawio,
    chunk_source_material,
    save_test_specification,
)
from ..common.agent_wrappers import ProcessLlmAgent
from ..common.test_case_chunk_generator_agent import test_case_chunk_generator_agent

test_specification_agent = ProcessLlmAgent(
    name="Test_Specification_Agent",
    description=(
        "Internal pipeline stage: reads whichever of a saved requirements summary, design "
        "document, and cloud architecture diagram are currently present, generates test "
        "cases that validate them (with traceability back to the specific requirement/"
        "component each test case targets), and saves a reusable test specification. Does "
        "not create or modify the requirements, design, or cloud architecture themselves, "
        "and does not render a document itself -- Test_Specification_Pipeline's own later "
        "stage does that."
    ),
    instruction_file="common/test_specification_agent.txt",
    tools=[
        load_requirements_summary,
        load_full_design_context,
        load_drawio,
        chunk_source_material,
        save_test_specification,
        AgentTool(test_case_chunk_generator_agent),
    ],
    generate_content_config=types.GenerateContentConfig(temperature=0.2, top_p=1),
)
