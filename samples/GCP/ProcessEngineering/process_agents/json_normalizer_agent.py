from google.adk.agents import LlmAgent
from google.genai import types

import logging

logger = logging.getLogger("ProcessArchitect.JsonNormalizer")

# -----------------------------
# JSON NORMALIZER AGENT
# -----------------------------
json_normalizer_agent = LlmAgent(
    name="JSON_Normalizer_Agent",
    model="gemini-2.0-flash-001",
    include_contents="default",   # <-- REQUIRED so the agent sees the Reviewer output
    description="Normalizes arbitrary business process JSON into a stable enriched schema.",
    instruction=(
        "You are a JSON expert at normalization, formatting, and professional enrichment.\n\n"

        "=============================\n"
        "CONTROL LOGIC (CRITICAL)\n"
        "=============================\n"
        "You ALWAYS see the previous agent's message in the conversation history.\n"
        "Use ONLY the MOST RECENT previous message to determine your behavior.\n\n"

        "1. If the most recent previous message begins with 'JSON APPROVED':\n"
        "     - You MUST NOT output any JSON or text as your task is complete and you can STOP.\n\n"

        "2. If the most recent previous message begins with 'REVISION REQUIRED':\n"
        "     - Read the list of issues.\n"
        "     - Fix ONLY those issues.\n"
        "     - Produce a corrected JSON object.\n\n"

        "3. If there is no review message yet (first iteration):\n"
        "     - Produce the first normalized JSON object.\n\n"

        "=============================\n"
        "NORMALIZATION REQUIREMENTS\n"
        "=============================\n"
        "You MUST transform the input into this EXACT schema:\n"
        "{\n"
        "  \"process_name\": string,\n"
        "  \"version\": string,\n"
        "  \"introduction\": string,\n"
        "  \"stakeholders\": [\n"
        "      { \"role\": string, \"responsibilities\": [string] }\n"
        "  ],\n"
        "  \"process_steps\": [\n"
        "      {\n"
        "        \"step_name\": string,\n"
        "        \"description\": string,\n"
        "        \"responsible_party\": string or list,\n"
        "        \"estimated_duration\": string,\n"
        "        \"deliverables\": [string],\n"
        "        \"dependencies\": [string],\n"
        "        \"success_criteria\": [string]\n"
        "      }\n"
        "  ],\n"
        "  \"tools_summary\": {},\n"
        "  \"metrics\": [ { \"name\": string, \"description\": string } ],\n"
        "  \"reporting_and_analytics\": {},\n"
        "  \"system_requirements\": [string],\n"
        "  \"appendix\": {}\n"
        "}\n\n"

        "=============================\n"
        "ENRICHMENT RULES\n"
        "=============================\n"
        "- Expand ALL descriptions and the introduction into multi‑sentence professional paragraphs.\n"
        "- NO bullet points inside description fields.\n"
        "- Flatten ANY nested structures (phases, sub_steps, dicts-as-steps) into a flat list.\n"
        "- Ensure all fields exist, even if empty.\n"
        "- Ensure all arrays contain only strings or objects as required.\n"
        "- Ensure all JSON is syntactically valid.\n\n"

        "=============================\n"
        "JSON OUTPUT CONTRACT\n"
        "=============================\n"
        "- When producing JSON, output ONLY the raw JSON object.\n"
        "- NO markdown.\n"
        "- NO ```json fences.\n"
        "- NO commentary.\n"
        "- MUST start with '{' and end with '}'.\n"
    ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.4,
        top_p=1,
    ),
)
