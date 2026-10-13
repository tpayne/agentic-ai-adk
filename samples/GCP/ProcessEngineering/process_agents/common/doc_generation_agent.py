# process_agents/doc_generation_agent.py
#
# Generates a structured, ISO-formatted Word document from the master
# process or design-document JSON. Logic lives in
# process_toolkit.docgen.generation (shared with the neuro-san port) --
# this file is just the ADK agent wrapper.

from process_toolkit.docgen.generation import create_standard_doc_from_file

from .agent_wrappers import ProcessAgent

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
        input_path = "output/process_data.json"

    try:
        result = create_standard_doc_from_file(input_path)
        print(result)
    except Exception as e:
        print(f"ERROR during document generation: {e}")
        raise
