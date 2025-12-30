# process_agents/json_review_agent.py
from google.adk.agents import LlmAgent
from google.genai import types
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext

import logging

logger = logging.getLogger("ProcessArchitect.JsonReview")

# --- Tool Definition ---
def exit_loop(tool_context: ToolContext):
    """Tool to exit the normalization loop when JSON is approved."""
    logger.info("JSON approved. Exiting normalization loop.")
    tool_context.actions.escalate = True
    return {}

# -----------------------------
# JSON REVIEW AGENT
# -----------------------------
json_review_agent = LlmAgent(
    name='Json_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Review JSON for validity, compliance, and best practices.',
    include_contents="default",
    tools=[exit_loop],
    instruction=(
        "You are a JSON Review Officer. Your goal is to ensure the Process JSON is "
        "production-ready, schema-compliant, and professionally enriched.\n\n"

        "INPUT:\n"
        "- You will see a JSON object produced by the previous agent in the conversation history.\n"
        "- Review ONLY that JSON object. Ignore any tool calls or other agent messages that appear "
        "  before or after it in the history.\n\n"

        "CRITERIA FOR REVIEW:\n"
        "1. SCHEMA: Must match exactly:\n"
        "   {\n"
        "     \"process_name\": string,\n"
        "     \"industry_sector\": string,\n"
        "     \"version\": string,\n"
        "     \"introduction\": string,\n"
        "     \"stakeholders\": [],\n"
        "     \"process_steps\": [],\n"
        "     \"tools_summary\": {},\n"
        "     \"metrics\": [],\n"
        "     \"reporting_and_analytics\": {},\n"
        "     \"system_requirements\": [],\n"
        "     \"appendix\": {}\n"
        "   }\n"
        "2. COMPLETENESS: No empty strings or empty arrays if data exists in context.\n"
        "3. ENRICHMENT: The 'introduction' and all step descriptions must be multi-sentence, "
        "   professional paragraphs. Reject bullet points in these fields.\n"
        "4. QUALITY: Verify English grammar, spelling, and logical flow between steps.\n"
        "5. CONSISTENCY: Ensure tool names in 'tools_summary' match those mentioned in 'process_steps'.\n\n"

        "OUTPUT CONTRACT (STRICT):\n"
        "You MUST choose exactly ONE of the following formats:\n\n"
        "A) If ANY criteria fail, output EXACTLY:\n"
        "   REVISION REQUIRED\n"
        "   [\n"
        "     {\"error_type\": \"string\", \"line\": \"line_number\", "
        "\"location\": \"json_path\", \"instruction\": \"detailed fix instruction\"},\n"
        "     ...\n"
        "   ]\n\n"
        "B) If and ONLY if ALL criteria are met, output EXACTLY:\n"
        "   JSON APPROVED\n"
        "   {<THE FULL VALID JSON OBJECT>}\n\n"

        "STRUCTURE RULES (CRITICAL):\n"
        "- Your response MUST consist of exactly TWO top-level parts:\n"
        "    1) A single line starting with either 'REVISION REQUIRED' or 'JSON APPROVED'.\n"
        "    2) Immediately after that line, ONE and only ONE JSON structure:\n"
        "       - A JSON array of issue objects if revisions are required, OR\n"
        "       - A single JSON object if the JSON is approved.\n"
        "- You MUST NOT output more than one JSON object or array.\n"
        "- You MUST NOT repeat the JSON object later in the response.\n"
        "- You MUST NOT include any additional text, logs, or agent prefixes.\n\n"

        "FORBIDDEN CONTENT (ABSOLUTE):\n"
        "- Do NOT output markdown code blocks (no ```json, no ``` at all).\n"
        "- Do NOT wrap JSON in any kind of fence.\n"
        "- Do NOT output anything like '[Json_Review_Agent]:', '[JSON_Normalizer_Agent]:', "
        "  '[Edge_Inference_Agent]:', or '```tool_call'.\n"
        "- Do NOT output tool calls.\n"
        "- Do NOT output any commentary such as 'Here is the review' or 'The JSON looks good'.\n"
        "- Do NOT truncate the JSON object. If you approve it, you MUST echo the full, "
        "  syntactically complete JSON object.\n\n"

        "ROBUSTNESS RULE:\n"
        "- If the JSON object is very large, you MUST still output it in full when approved.\n"
        "- You MUST ensure that all braces and brackets are balanced and that all strings "
        "  are properly closed.\n\n"

        "SUMMARY OF BEHAVIOR (CRITICAL):\n"
        "- Inspect ONLY the JSON produced by the previous agent.\n"
        "- Decide if it passes or fails the criteria.\n"
        "- Then output either a single 'REVISION REQUIRED' + issues array, or 'JSON APPROVED' "
        "+ full JSON object, following ALL the structure and forbidden content rules above.\n"
        "- CRITICAL: If you output 'JSON APPROVED', then you MUST CALL the function 'exit_loop' immediately and STOP.\n\n"
    ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=1,
    ),
)
