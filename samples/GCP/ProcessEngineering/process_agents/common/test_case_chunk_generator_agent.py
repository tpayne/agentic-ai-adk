# process_agents/test_case_chunk_generator_agent.py
#
# The MAP half of a map-reduce test generation strategy -- the sibling of
# requirements_chunk_extractor_agent.py (see that module's own header for
# the full rationale): given ONE bounded, token-budgeted, already-wrapped
# chunk of combined source material (requirements/design/cloud-
# architecture content, serialized and split via chunk_source_material --
# not a directory of files, since this agent's own source material is
# already-structured saved JSON/XML, not raw documents), generates
# whatever test cases that chunk alone supports. Test_Specification_Agent
# calls this once per chunk, via AgentTool, and REDUCES the partial
# results into one final test specification -- this agent never sees
# more than one chunk at a time, and never writes anything to disk
# itself, so it has no business reasoning about the document as a whole.

from ..common.agent_wrappers import ProcessLlmAgent

test_case_chunk_generator_agent = ProcessLlmAgent(
    name="Test_Case_Chunk_Generator_Agent",
    description=(
        "Generates test cases from ONE CHUNK of a larger combined requirements/design/"
        "cloud-architecture payload -- not the whole payload, just this chunk. Used by "
        "Test_Specification_Agent as the map half of a map-reduce strategy for large "
        "combined source material; never called directly by a user request."
    ),
    instruction_file="common/test_case_chunk_generator_agent.txt",
    tools=[],
)
