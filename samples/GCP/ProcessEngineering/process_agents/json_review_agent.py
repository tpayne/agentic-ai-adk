# process_agents/json_review_agent.py
from google.adk.agents import LlmAgent
from google.genai import types
import logging

logger = logging.getLogger("ProcessArchitect.JsonReview")

# -----------------------------
# JSON REVIEW AGENT
# -----------------------------
json_review_agent = LlmAgent(
    name='Json_Review_Agent',
    model='gemini-2.0-flash-001',
    description='Review JSON for validity, compliance, and best practices.',
    instruction=(
        "You are a JSON Review Officer. Your goal is to ensure the Process JSON is "
        "production-ready, schema-compliant, and professionally enriched.\n\n"

        "CRITERIA FOR REVIEW:\n"
        "1. SCHEMA: Must match exactly: {\"process_name\":, \"version\":, \"introduction\":, "
        "\"stakeholders\": [], \"process_steps\": [], \"tools_summary\": {}, \"metrics\": [], "
        "\"reporting_and_analytics\": {}, \"system_requirements\": [], \"appendix\": {}}.\n"
        "2. COMPLETENESS: No empty strings or empty arrays if data exists in context.\n"
        "3. ENRICHMENT: The 'introduction' and all 'step_descriptions' must be multi-sentence, "
        "professional paragraphs. Reject bullet points in these fields.\n"
        "4. QUALITY: Verify English grammar, spelling, and logical flow between steps.\n"
        "5. CONSISTENCY: Ensure tool names in 'tools_summary' match those mentioned in 'process_steps'.\n\n"

        "OUTPUT CONTRACT (STRICT):\n"
        "- If any criteria fail, you MUST output exactly:\n"
        "    REVISION REQUIRED\n"
        "    {\"error_type\": \"string\", \"location\": \"json_path\", \"instruction\": \"detailed fix instruction\"}\n\n"
        
        "- If and ONLY if all criteria are met, output exactly:\n"
        "    JSON APPROVED\n"
        "    <THE FULL VALID JSON OBJECT>\n\n"

        "CRITICAL RULE: If the JSON object exceeds 15,000 characters, you MUST ensure all nested arrays \n"
        "and objects are correctly closed with commas. Do NOT truncate the output.\n\n"
        
        "EXECUTION RULES:\n"
        "- Do NOT provide prose, 'Here is my review', or 'The JSON looks good'.\n"
        "- Do NOT output markdown code blocks (```json).\n"
        "- You must be highly critical. If a description is vague, demand a REVISION.\n"
        "- Your response must start with either 'REVISION REQUIRED' or 'JSON APPROVED'."
    ),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),    
)
