# process_agents/requirements_chunk_extractor_agent.py
#
# The MAP half of a map-reduce extraction strategy: given ONE bounded,
# token-budgeted, already-wrapped chunk of source material (see
# shared/process_toolkit's load_directory_context -> "chunks"), extracts
# whatever requirements-like content that chunk alone supports. Called
# once per chunk, via AgentTool, by each of the three requirements-
# extraction consumers (Requirements_Summary_Agent, Requirements_Synthesis_
# Agent, Ensure_Requirements_Summary_Agent) -- those agents REDUCE the
# partial results into one final requirements summary; this agent never
# sees more than one chunk at a time and never writes anything to disk
# itself, so it has no business reasoning about the document as a whole.
#
# Introduced to replace a flat max_chars truncation that silently dropped
# whatever didn't fit in a single LLM pass, and to give every chunk an
# explicit untrusted-data boundary (the chunk text load_directory_context
# hands back is already wrapped in <untrusted_source_document> markers --
# this agent's own instructions reinforce that framing rather than
# re-stating raw content as if it were trusted).

from ..common.agent_wrappers import ProcessLlmAgent

requirements_chunk_extractor_agent = ProcessLlmAgent(
    name="Requirements_Chunk_Extractor_Agent",
    description=(
        "Extracts requirements-like content (requirements_register items, inferred "
        "requirements, dependencies, glossary terms, and a short summary) from ONE CHUNK "
        "of a larger source document -- not the whole document, just this chunk. Used by "
        "the requirements-extraction agents as the map half of a map-reduce strategy for "
        "large directories; never called directly by a user request."
    ),
    instruction_file="common/requirements_chunk_extractor_agent.txt",
    tools=[],
)
