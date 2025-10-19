import logging
import os
import json
from queue import Full
import uuid
import asyncio
import httpx

from typing import AsyncGenerator
from typing_extensions import override

from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event
from google.adk.sessions import VertexAiSessionService

from pydantic import BaseModel, Field, ValidationError

from . import utils
from .utils import load_properties, getValue

import sys
import google.auth
import google.auth.transport.requests

# --- Constants ---
# The application name for ADK. This should be unique to your application.
APP_NAME = "email_processing_app"
MODEL="gemini-2.0-flash"

# --- Configure Logging ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
# Suppress the specific ADK warning about output_schema and agent transfers
logging.getLogger("google_adk.google.adk.agents.llm_agent").setLevel(logging.ERROR)
# Get log level from environment variable, default to WARNING
LOGLEVEL = os.getenv("LOGLEVEL", "WARNING").upper()
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
    if logger: logger.setLevel(LOGLEVEL)

# --- Utility Functions ---

async def get_answer_content(client: httpx.AsyncClient, project_id: str, app_id: str, query_text: str, query_id: str, session_name: str, region: str) -> dict:
    """
    Performs an answer generation query and returns a dictionary with the answer
    text and a list of content chunks.
    """
    url = (
        f"https://{region}-discoveryengine.googleapis.com/v1alpha/projects/"
        f"{project_id}/locations/{region}/collections/default_collection/engines/"
        f"{app_id}/servingConfigs/default_search:answer"
    )

    payload = {
        "query": {
            "text": query_text,
            "queryId": query_id
        },
        "session": session_name,
        "relatedQuestionsSpec": {
            "enable": "true"
        },
        "answerGenerationSpec": {
            "ignoreAdversarialQuery": "true",
            "ignoreNonAnswerSeekingQuery": "false",
            "ignoreLowRelevantContent": "true",
            "multimodalSpec": {},
            "includeCitations": "true",
            "modelSpec": {
                "modelVersion": "stable"
            }
        }
    }

    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        answer_text = data.get("answer", {}).get("answerText", "")
        references = data.get("answer", {}).get("references", [])
        content_array = []
        
        for ref in references:
            chunk_info = ref.get("chunkInfo", {})
            if chunk_info:
                content = chunk_info.get("content")
                if content:
                    content_array.append(content)

        if "A summary could not be generated for your search query" in answer_text:
            return {"answerText": "", "contentArray": []}

        return {
            "answerText": answer_text,
            "contentArray": content_array
        }

    except httpx.HTTPStatusError as e:
        if logger: logger.error(f"HTTP error during get_answer_content: {e.response.status_code} {e.response.text}")
        return {"answerText": f"An HTTP error occurred: {e.response.status_code}", "contentArray": []}
    except Exception as e:
        if logger: logger.error(f"Unexpected error during get_answer_content: {e}")
        return {"answerText": "An unexpected error occurred.", "contentArray": []}

async def get_authenticated_client() -> httpx.AsyncClient:
    """
    Returns an authenticated httpx.AsyncClient instance.
    """
    auth_required = getValue("gcp_login")
    isAuth = bool(auth_required == "true") if auth_required is not None else False
    
    if isAuth:
        if logger: logger.debug("- Doing GCP authentication...")
        sa_json_file = utils.getValue("sa_json_file")
        if sa_json_file and os.path.exists(sa_json_file):
            credentials, _ = google.auth.load_credentials_from_file(sa_json_file)
        else:
            credentials, _ = google.auth.default()
        
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        access_token = credentials.token
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        return httpx.AsyncClient(headers=headers, timeout=60.0)
    else:
        if logger: logger.debug("- Not doing GCP authentication...")
        headers = {"Content-Type": "application/json"}
        return httpx.AsyncClient(headers=headers, timeout=60.0)

async def run_agentspace_url_query(client: httpx.AsyncClient, agentspace_ai_url: str, bodyText: str) -> str:
    """
    Calls the AgentSpace AI URL with the provided body text and returns the draft response.
    """
    try:
        if agentspace_ai_url and '/' not in agentspace_ai_url:
            return "" 
        
        url_parts = agentspace_ai_url.split('/')
        project_id = url_parts[5]
        app_id = url_parts[11]
        region = url_parts[7]
        
        combined_query = "" + " " + bodyText

        payload = {
            "query": combined_query,
            "pageSize": 100,
            "queryExpansionSpec": {"condition": "AUTO"},
            "spellCorrectionSpec": {"mode": "AUTO"},
            "languageCode": "en-US",
            "contentSearchSpec":{"extractiveContentSpec":{"maxExtractiveAnswerCount":1}},
            "userInfo":{"timeZone":"Europe/London"},
            "session": f"projects/{project_id}/locations/{region}/collections/default_collection/engines/{app_id}/sessions/-"
        }
        
        if logger: logger.debug(f"- Calling external agent URI: {agentspace_ai_url}")
        response = await client.post(agentspace_ai_url, json=payload)
        response.raise_for_status()
        if logger: logger.debug(f"- Parsing agent response...")
        
        data = response.json()
        session_info = data.get("sessionInfo", {})
        session_name = session_info.get("name")
        query_id = session_info.get("queryId")

        if session_name and query_id:
            draft_response_json = await get_answer_content(client, project_id, app_id, combined_query, query_id, session_name, region)
            draft_answer_text = draft_response_json.get("answerText", "")
            return draft_answer_text
        else:
            if logger: logger.warning("Session name or query ID not found in response.")
            return "No valid session or query ID found."
    
    except httpx.HTTPStatusError as e:
        if logger: logger.error(f"HTTP error during run_agentspace_url_query: {e.response.status_code} {e.response.text}")
        return f"An HTTP error occurred: {e.response.status_code}."
    except Exception as e:
        if logger: logger.error(f"General error during run_agentspace_url_query: {e}")
        return "An unexpected error occurred."
    
async def get_agentspace_draft_response(client: httpx.AsyncClient, ctx: InvocationContext) -> str:
    """
    Calls the AgentSpace AI URL with the topic from the context and returns the draft response.
    """
    try:            
        agentspace_ai_url = utils.getValue("AGENTSPACE_AI_URL")
        bodyText = ctx.session.state.get("topic", "No topic provided.")
        if agentspace_ai_url and bodyText and agentspace_ai_url != "<ENTERAGENTSPACEAPIURL_DEFAULTSEARCH>":
            draft_response = await run_agentspace_url_query(client, agentspace_ai_url, bodyText)
            if isinstance(draft_response, list):
                draft_response = "\n\n".join(draft_response)
            return draft_response
        return ""
    except Exception as e:
        if logger: logger.error(f"Error in get_agentspace_draft_response: {e}")
        return ""

# --- New Base Class for Tool Agents ---
class _BaseToolAgent(BaseAgent):
    """
    Base class for all specific tool agents.
    It contains the shared logic for calling the external Agentspace AI.
    """
    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        client = ctx.session.state.get("httpx_client")
        if not client:
            error_msg = "HTTP client not found in session state."
            if logger: logger.error(error_msg)
            ctx.session.state["tool_result"] = error_msg
            yield Event(author=self.name, content=types.Content(role="model", parts=[types.Part(text=error_msg)]))
            return

        try:
            rewritten_query = ctx.session.state.get("rewritten_query", ctx.session.state.get("topic"))
            draft_response = await run_agentspace_url_query(client, utils.getValue("AGENTSPACE_AI_URL"), rewritten_query)
            if isinstance(draft_response, list):
                draft_response = "\n\n".join(draft_response)
            ctx.session.state["tool_result"] = draft_response
            yield Event(author=self.name, content=types.Content(role="model", parts=[types.Part(text=draft_response)]))
        except Exception as e:
            error_msg = f"Exception in {self.name}: {e}"
            if logger: logger.error(error_msg)
            ctx.session.state["tool_result"] = error_msg
            yield Event(author=self.name, content=types.Content(role="model", parts=[types.Part(text=error_msg)]))

# --- Tool Agents that inherit from the new Base Class ---
class HardwareToolAgent(_BaseToolAgent):
    pass

class SoftwareToolAgent(_BaseToolAgent):
    pass

class GenericITToolAgent(_BaseToolAgent):
    pass

class WindowsToolAgent(_BaseToolAgent):
    pass

class UnixToolAgent(_BaseToolAgent):
    pass

class NetworkToolAgent(_BaseToolAgent):
    pass

class PolicyToolAgent(_BaseToolAgent):
    pass

class CustomerAccountToolAgent(_BaseToolAgent):
    pass

class FAQToolAgent(_BaseToolAgent):
    pass

class CustomerDataToolAgent(_BaseToolAgent):
    pass

class CustomerPaymentToolAgent(_BaseToolAgent):
    pass

class OtherToolAgent(_BaseToolAgent):
    pass

# --- Custom CustomerMeterToolAgent with specific logic ---
class CustomerMeterToolAgent(BaseAgent):
    """
    Agent for handling customer meter-related requests.
    Includes a method to add a custom acknowledgement to the response.
    """
    def _add_meter_update_acknowledgement(self, draft_response: str) -> str:
        """
        Adds a custom acknowledgement message to the end of the draft response.
        """
        acknowledgement_text = "\n\nNote: A meter update has been applied to the customer's record."
        return draft_response + acknowledgement_text

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        client = ctx.session.state.get("httpx_client")
        if not client:
            error_msg = "HTTP client not found in session state."
            ctx.session.state["tool_result"] = error_msg
            yield Event(author=self.name, content=types.Content(role="model", parts=[types.Part(text=error_msg)]))
            return

        try:
            customer_name = ctx.session.state.get("email_parser_obj",{}).get("customer_name","unknown")
            customer_id = ctx.session.state.get("email_parser_obj",{}).get("customer_id","unknown")
            date_range = ctx.session.state.get("email_parser_obj",{}).get("date_range","unknown")
            meter_reading = ctx.session.state.get("email_parser_obj",{}).get("meter_reading","unknown")
            
            if "unknown" in [customer_name, customer_id, date_range, meter_reading]:
                customized_response = "You have not specified all the required customer name, id, meter reading or date range details."
            else:
                rewritten_query = f"Is there a customer with the customer_id {customer_id}?"
                draft_response = await run_agentspace_url_query(client, utils.getValue("AGENTSPACE_AI_URL"), rewritten_query)
                
                if "An HTTP error occurred" in draft_response or "A request error occurred" in draft_response:
                     customized_response = f"An error occurred while checking the customer ID: {draft_response}"
                elif "yes" in draft_response.lower():
                    draft_response = "The customer exists in the system."
                    customized_response = self._add_meter_update_acknowledgement(draft_response)
                else:
                    customized_response = "The customer specified does not exist in the system."

            ctx.session.state["tool_result"] = customized_response
            yield Event(author=self.name, content=types.Content(role="model", parts=[types.Part(text=customized_response)]))
        except Exception as e:
            error_msg = f"Exception in CustomerMeterToolAgent: {e}"
            if logger: logger.error(error_msg)
            ctx.session.state["tool_result"] = error_msg
            yield Event(author=self.name, content=types.Content(role="model", parts=[types.Part(text=error_msg)]))

# --- Custom Orchestrator Agent ---
class CustomEmailProcessorAgent(BaseAgent):
    """
    An ADK agent that orchestrates a multi-step workflow for processing IT support emails.
    """
    queryRewriter: LlmAgent
    sentimentReviewer: LlmAgent
    emailParser: LlmAgent
    emailGenerator: LlmAgent
    emailReviewer: LlmAgent
    emailReviser: LlmAgent
    loop_agent: LoopAgent
    sequential_agent: SequentialAgent
    revision_agent: SequentialAgent

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        queryRewriter: LlmAgent,
        sentimentReviewer: LlmAgent,
        emailParser: LlmAgent,
        emailGenerator: LlmAgent,
        emailReviewer: LlmAgent,
        emailReviser: LlmAgent,
    ):
        sequential_agent = SequentialAgent(
            name="GenerateEmail", sub_agents=[sentimentReviewer, emailParser, queryRewriter]
        )
        revision_agent = SequentialAgent(
            name="ReviewAndReviseEmail", sub_agents=[emailReviewer, emailReviser]
        )
        loop_agent = LoopAgent(
            name="ReviewEmail", sub_agents=[revision_agent], max_iterations=5
        )

        sub_agents_list = [
            sequential_agent,
            loop_agent,
        ]

        super().__init__(
            name=name,
            queryRewriter=queryRewriter,
            sentimentReviewer=sentimentReviewer,
            emailParser=emailParser,
            emailGenerator=emailGenerator,
            emailReviewer=emailReviewer,
            emailReviser=emailReviser,
            sequential_agent=sequential_agent,
            revision_agent=revision_agent,
            loop_agent=loop_agent,
            sub_agents=sub_agents_list,
        )

    @staticmethod
    def extract_user_text(session) -> str | None:
        try:
            events = session["events"]
            first_part = events[0]["content"]["parts"][0]
            return first_part["text"]
        except (KeyError, IndexError, TypeError):
            pass

        try:
            ev = session.events[0]
            part = ev.content.parts[0]
            return part.text
        except (AttributeError, IndexError):
            return None

    @override
    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        
        ctx.session.state.setdefault("from_email_address", "a customer")
        ctx.session.state.setdefault("subject", "a new support request")
        ctx.session.state["httpx_client"] = await get_authenticated_client()

        bodyText = None
        user_message_text = None

        if getattr(ctx.session, "new_message", None) and getattr(ctx.session.new_message, "parts", None):
            part = ctx.session.new_message.parts[0]
            user_message_text = getattr(part, "text", None)

        if user_message_text is None:
            user_message_text = CustomEmailProcessorAgent.extract_user_text(ctx.session)

        if user_message_text is not None:
            try:
                payload = json.loads(user_message_text)
                email_context = EmailContext.model_validate(payload)
                ctx.session.state["from_email_address"] = email_context.fromEmailAddress
                ctx.session.state["subject"] = email_context.subject
                user_input_topic = email_context.body
                bodyText = email_context.body
                ctx.session.state["topic"] = user_input_topic
            except (json.JSONDecodeError, ValidationError):
                ctx.session.state["topic"] = user_message_text
                bodyText = user_message_text
        
        original_query = bodyText
        
        async for event in self.sequential_agent.run_async(ctx):
            yield event

        rewritten_query = ctx.session.state.get("rewritten_query", original_query)
        email_intention = ctx.session.state.get("email_sentiment_obj", {}).get("intention")

        tool_agent_map = {
            'Hardware Issue': HardwareToolAgent,
            'Software Issue': SoftwareToolAgent,
            'Windows IT Issue': WindowsToolAgent,
            'Unix IT Issue': UnixToolAgent,
            'Network Issue': NetworkToolAgent,
            'Policy Question': PolicyToolAgent,
            'Customer Account Issue': CustomerAccountToolAgent,
            'FAQ Request': FAQToolAgent,
            'Customer Data Request': CustomerDataToolAgent,
            'Customer Payment Request': CustomerPaymentToolAgent,
            'Customer Meter Request': CustomerMeterToolAgent,
            'Other': OtherToolAgent,
        }
        
        selected_agent = tool_agent_map.get(email_intention, GenericITToolAgent)
        async for event in selected_agent(name=selected_agent.__name__).run_async(ctx):
            yield event

        async for event in self.emailGenerator.run_async(ctx):
            yield event

        email_draft = ctx.session.state.get("email_draft")
        if not email_draft or not str(email_draft).strip():
            return
        
        async for event in self.loop_agent.run_async(ctx):
            yield event
            email_review_comments = ctx.session.state.get("email_review_comments","").strip()
            if "No further comments." in email_review_comments:
                break

        final_session = ctx.session
        result = {
            "email_data": {
                "fromEmailAddress": final_session.state.get("from_email_address"),
                "subject": final_session.state.get("subject"),
                "body": bodyText,
            },
            "answer": {
                "email_draft": final_session.state.get("email_draft"),
                "tool_results": final_session.state.get("tool_result", "No tool was explicitly called."),
            },
            "metadata": {
                "email_sentiment": final_session.state.get("email_sentiment_obj", {}).get("sentiment"),
                "email_intention": final_session.state.get("email_sentiment_obj", {}).get("intention"),
                "email_urgency": final_session.state.get("email_sentiment_obj", {}).get("urgency"),
                "email_keystatements": final_session.state.get("email_sentiment_obj", {}).get("keystatement"),
                "email_review_comments": final_session.state.get("email_review_comments").split("\n\n")[-1].strip()
            }
        }
        final_content = types.Content(
            role="model",
            parts=[types.Part(text=json.dumps(result, indent=2))]
        )

        yield Event(
            author="CustomEmailProcessorAgent",
            content=final_content,
        )
        
        await ctx.session.state["httpx_client"].aclose()

        return

# --- Pydantic Schemas for structured input/output ---
class EmailContext(BaseModel):
    """Pydantic model for structured JSON email input."""
    fromEmailAddress: str = Field(None, description="The sender's email address.")
    subject: str = Field(None, description="The subject line of the email.")
    body: str = Field(..., description="The body of the email.")
    dateTime: str = Field(None, description="The date and time the email was sent.")

class EmailSentiment(BaseModel):
    """Pydantic model for structured sentiment output from the LLM."""
    sentiment: str = Field(description="The single word sentiment label of the email.")
    intention: str = Field(description="The single action statement about what the action is this email needs to result in doing.")
    urgency:   str = Field(description="Optional urgency level of the email.")
    keystatement: str = Field(description="A key statement about what the email is about and what is it asking.")

class EmailParser(BaseModel):
    """Pydantic model for structured parser output from the LLM."""
    customer_name: str = Field(description="The customer name.")
    customer_id: str = Field(description="The customer id.")
    date_range:   str = Field(description="The date range.")
    meter_reading: str = Field(description="The meter reading.")

# --- LLM Agent Instructions ---
helpbot_instruction = (
    "You are HelpBot, an automated IT helpdesk email chatbot for a corporate IT support desk. "
    "You know common IT problems with Windows and Linux. "
    "Respond professionally and empathetically in email format for semi-IT literate users. "
    "Limit responses to IT, HR, FAQ, Customer issues, Customer meter updates and policy topics only. "
    "Be truthful, never lie or make up facts; if unsure, explain why. "
    "Cite references when possible. "
    "Request further info with clear steps if needed. "
    "If unable to resolve, state any additional info needed to escalate or other sources to consult. "
    "When providing instructions or lists, use numbered lists. Use **bold** for emphasis on key words or phrases. "
    "Return the full email text as HTML only, do not return any other text. Wrap the response in <html><body>...</body></html> tags. "
    "You may use multiple paragraphs, headings, and ordered/unordered lists to structure your response, and you may use simple HTML tags like <b> and <p> for emphasis."
)

reviewer_instruction = (
    "You are an expert email reviewer. Review the email provided: {{email_draft}}. Provide 1-2 sentences of constructive criticism "
    "on how to improve it. Focus on clarity, tone, and professionalism."
    "When your are finished reviewing and have nothing more to add, respond with 'No further comments.'"
)

reviser_instruction = (
    "You are an expert email reviser. You have been given an email draft: {{email_draft}} and review comments: {{email_review_comments}}. "
    "Your task is to apply the review comments to the email draft to create a new, improved draft. "
    "Return only the revised email draft, with no additional commentary."
)

sentiment_instruction = (
    "You are an expert in analyzing email sentiment. Review the email provided: {{topic}}. "
    "Output ONLY the following: "
    "1. A single sentiment label as specified in the schema. "
    "2. A single action statement about what the action is this email needs to result in doing. You will need to catagorize the intention. "
    "   into the following categories: 'Generic IT Issue', ''Windows IT Issue', 'Unix IT Issue', 'Hardware Issue', 'Software Issue', 'Network Issue', "
    "   'Policy Question', 'Customer Account Issue', 'FAQ Request', 'Customer Data Request', 'Customer Payment Request', "
    "   'Customer Meter Request', 'Other'. "
    "3. A single urgency label for the email, depending on if it is clearly urgent or high priority. Categories are 'Low', 'Medium', 'High', or 'Critical'. "
    "   If not clearly specified, return 'Normal'. "
    "4. A key statement about what the email is about and what is it asking. Make the summary concise and capture the key actions and facts. "
    "Format your response as a JSON object matching the EmailSentiment schema. "
    "Do not output anything else."
)

query_rewriter_instruction = (
    "You are an expert on Agentspace AI apps. "
    "Your role is to ensure Agentspace AI apps RESTful API will return a relevant answer. "
    "Rewrite the following text - {{topic}} - into a direct, succinct question that an AI knowledge base can easily answer. "
    "The question should begin with 'what' or a similar interrogative. Return only the rephrased question."
)

parser_instruction = (
    "You are an expert in analyzing email contents. Review the email provided: {{topic}}. "
    "Output ONLY the following: "
    "1. A single customer name as specified in the schema. "
    "2. A single customer id as specified in the schema."
    "3. A date range for an account as specified in the schema. This must have a start date and an end date. "
    "   If only one is specified, use the same date for start and end. "
    "   If not specified, return 'unknown'. "
    "4. A single meter reading as specified in the schema. "
    "Format your response as a JSON object matching the EmailParser schema. "
    "If not specified, return 'unknown'. "
    "Do not output anything else."
)

# --- Define the individual LLM agents ---
queryRewriter = LlmAgent(
    name="QueryRewriter",
    model=MODEL,
    instruction=query_rewriter_instruction,
    output_key="rewritten_query"
)

emailGenerator = LlmAgent(
    name="EmailGenerator",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
    instruction=helpbot_instruction + (
        " Generate the complete email draft for the following customer inquiry: {{topic}}. "
        "The original email was from {{from_email_address}} with the subject '{{subject}}'."
        "Use the tool result if available: {{tool_result}} to help inform your response. "
        "Provide ONLY the email content, with no introductory or concluding remarks."
    ),
    input_schema=None,
    output_schema=None,
    output_key="email_draft",
)

emailReviewer = LlmAgent(
    name="EmailReviewer",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
    instruction=reviewer_instruction,
    input_schema=None,
    output_schema=None,
    output_key="email_review_comments",
)

emailReviser = LlmAgent(
    name="EmailReviser",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
    instruction=reviser_instruction,
    input_schema=None,
    output_schema=None,
    output_key="email_draft",
)

sentimentReviewer = LlmAgent(
    name="EmailSentimentReviewer",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
    instruction=sentiment_instruction,
    input_schema=None,
    output_schema=EmailSentiment,
    output_key="email_sentiment_obj",
)

emailParser = LlmAgent(
    name="EmailParser",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
    instruction=parser_instruction,
    input_schema=None,
    output_schema=EmailParser,
    output_key="email_parser_obj",
)

# --- Create the custom agent instance ---
root_agent = CustomEmailProcessorAgent(
    name="CustomEmailProcessorAgent",
    queryRewriter=queryRewriter,
    sentimentReviewer=sentimentReviewer,
    emailParser=emailParser,
    emailGenerator=emailGenerator,
    emailReviewer=emailReviewer,
    emailReviser=emailReviser,
)

# --- Main Execution Block for a local, working example ---
async def setup_session_and_runner(user_id: str, session_id: str, email_topic: str):
    """
    Sets up an ADK session and a Runner for local testing.
    """
    INITIAL_STATE = {"topic": email_topic}

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME,
                                                   user_id=user_id,
                                                   session_id=session_id,
                                                   state=INITIAL_STATE)

    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service
    )
    return session_service, runner

# --- Function to Interact with the Agent ---
async def call_agent_async(user_input_topic: str, logger: logging.Logger = None):
    """
    Sends a new topic to the agent and runs the workflow.
    """
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    session_service, runner = await setup_session_and_runner(user_id, session_id, user_input_topic)

    current_session = await session_service.get_session(app_name=APP_NAME,
                                                  user_id=user_id,
                                                  session_id=session_id)
    if not current_session:
        return

    current_session.state["topic"] = user_input_topic

    content = types.Content(
        role='user',
        parts=[types.Part(text=user_input_topic)]
    )

    events = runner.run_async(user_id=user_id,
                              session_id=session_id,
                              new_message=content)

    final_response = "No final response captured."
    async for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text
    
    return final_response

# --- Main Execution Block for a local, working example ---
if __name__ == "__main__":
    # Example for JSON input
    json_message = json.dumps({
        "fromEmailAddress": "johndoe@example.com",
        "subject": "Urgent: My laptop is not turning on",
        "body": "Hi, my laptop is not turning on. I've tried charging it and pressing the power button multiple times."
    }, indent=2)

    # Example for plain string input for a software issue
    string_message_software = "My web browser keeps crashing when I open a new tab."

    # Example for plain string input for a hardware issue
    string_message_hardware = "My mouse isn't working at all."

    # Choose which message to run based on command-line argument
    # Default to the JSON message if no argument is provided
    user_message = sys.argv[1] if len(sys.argv) > 1 else json_message

    final_state_json = asyncio.run(call_agent_async(user_message))
    print(final_state_json)
