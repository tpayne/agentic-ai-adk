# process_agents/doc_generation_agent.py
#
# Generates a structured, ISO-formatted Word document from the master
# process or design-document JSON. Logic lives in
# process_toolkit.docgen.generation (shared with the neuro-san port) --
# this file is just the ADK agent wrapper.

from typing import Optional

from google.adk.tools.tool_context import ToolContext

from process_toolkit.docgen.generation import create_standard_doc_from_file as _shared_create_standard_doc_from_file

from .agent_wrappers import ProcessAgent
from .utils_agent import release_pipeline_lock_for_turn


def create_standard_doc_from_file(
    process_name: str = "Process",
    schema_type: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> str:
    """Same contract as process_toolkit.docgen.generation's own function of
    this name (kept here under the identical name so this module's own
    instruction file, which tells the LLM to call "create_standard_doc_from_file"
    by that exact name, keeps working unchanged) -- plus one addition: on
    success, releases the shared output/ directory's pipeline lock (see
    process_toolkit.run_lock). This is every create/update pipeline's own
    genuine last step (Doc_Creation_Agent's own Document_Generation_Agent,
    after analysis -> design/compliance/simulation loop -> JSON
    normalization -> subprocess expansion -- see
    process/create_process_agent.py's full_design_pipeline), unlike the
    JSON-normalization stage earlier in the SAME pipeline, which persists
    on every loop iteration, not just the final one, so must NOT release
    the lock itself. tool_context is auto-injected by ADK and excluded
    from the LLM-facing schema -- the LLM still just calls this with
    process_name, exactly as the instruction file describes."""
    result = _shared_create_standard_doc_from_file(process_name, schema_type)
    if isinstance(result, str) and result.startswith("SUCCESS:"):
        release_pipeline_lock_for_turn(tool_context)
    return result


doc_generation_agent = ProcessAgent(
    name="Document_Generation_Agent",
    description="Generates a professional ISO-formatted Word document from normalized JSON.",
    instruction_file="common/doc_generation_agent.txt",
    tools=[create_standard_doc_from_file],
)

if __name__ == "__main__":
    import sys

    # Allow: python -m process_agents.doc_generation_agent <path>
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    else:
        from process_toolkit import paths as toolkit_paths

        input_path = toolkit_paths.output_path("process_data.json")

    try:
        result = _shared_create_standard_doc_from_file(input_path)
        print(result)
    except Exception as e:
        print(f"ERROR during document generation: {e}")
        raise
