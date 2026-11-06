# process_agents/common/test_specification_agent.py
#
# Standalone, on-demand counterpart to requirements_summary_agent.py:
# reads whichever of a saved requirements summary, design document, and
# cloud architecture diagram are present, synthesizes a structured test
# specification (test cases, traceability, coverage gap analysis)
# validating them, and saves it for later reuse. Same standalone,
# save-only shape as Requirements_Summary_Agent -- it does NOT render a
# document itself; that is deferred to a separate, later "regenerate the
# test specification document" request through the existing generic
# Regenerate_Document_Agent/regenerate_document mechanism.
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
        "Reads whichever of a saved requirements summary, design document, and cloud "
        "architecture diagram are currently present, generates test cases that validate "
        "them (with traceability back to the specific requirement/component each test case "
        "targets), and saves a reusable test specification. Does not create or modify the "
        "requirements, design, or cloud architecture themselves."
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
