# process_agents/requirements_summary_agent.py
#
# Standalone, on-demand counterpart to the directory-context mode embedded
# in the process/design/cloudarch creation pipelines' analysis stages: reads
# a directory of source documents and summarizes the requirements WITHOUT
# running a full creation pipeline. Schema-agnostic (not process_schema.json
# or design_document_schema.json shaped), so it lives here in common/
# alongside the other schema-agnostic shared agents (json_normalizer_agent.py,
# json_review_agent.py) rather than under process/ or design/.
#
# Unlike every other agent in this codebase except the Consultant/Simulation
# Query agents, this one's VISIBLE response is a human-readable narrative,
# not a terse status marker -- the user explicitly asked to see the summary
# on screen. It also performs a real save action (save_requirements_summary),
# which the narrative-only agents never do.

from google.genai import types

from ..common.utils import load_directory_context, save_requirements_summary
from ..common.agent_wrappers import ProcessLlmAgent

requirements_summary_agent = ProcessLlmAgent(
    name="Requirements_Summary_Agent",
    description=(
        "Reads the files in a directory (.txt/.md/.docx/.pdf/.eml/.msg/.xls/.xlsx), "
        "summarizes the requirements found in them, and saves a reusable requirements "
        "summary for a LATER process/design/cloudarch creation request to pick up. "
        "Does not create or modify a process, design document, or cloud architecture itself."
    ),
    instruction_file="common/requirements_summary_agent.txt",
    tools=[load_directory_context, save_requirements_summary],
    generate_content_config=types.GenerateContentConfig(temperature=0.2, top_p=1),
)
