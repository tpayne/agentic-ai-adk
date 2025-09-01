import logging
import os
import json
import uuid
import asyncio
import requests
import google.auth

from typing import AsyncGenerator
from typing_extensions import override

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event

from pydantic import BaseModel, Field, ValidationError
import sys

# --- Constants ---
# The application name for ADK. This should be unique to your application.
APP_NAME = "email_processing_app"

# ---- Load .env ----
load_dotenv()

# --- Configure Logging ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
# Suppress the specific ADK warning about output_schema and agent transfers
logging.getLogger("google_adk.google.adk.agents.llm_agent").setLevel(logging.ERROR)
# Get log level from environment variable, default to WARNING
LOGLEVEL = os.getenv("LOGLEVEL", "WARNING").upper()
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
logger.setLevel(LOGLEVEL)

# ---- Credentials ----
# Determine if authentication is required based on environment variables
AUTH_REQUIRED = os.getenv("GCP_LOGIN", "FALSE").upper() == "TRUE"
if AUTH_REQUIRED:
    SA_JSON = os.getenv("SA_JSON_FILE")
    if SA_JSON and os.path.exists(SA_JSON):
        credentials, _ = google.auth.load_credentials_from_file(SA_JSON)
        logging.debug("Loaded service-account credentials from JSON.")
    else:
        credentials, _ = google.auth.default()
        logging.debug("Using Application Default Credentials.")
else:
    credentials = None
    logging.debug("Authentication not required, proceeding without credentials.")

# --- Environment Variables ---
# Get project ID and location, with fallbacks
PROJECT_ID = os.getenv("PROJECT_ID") if os.getenv("PROJECT_ID") else os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION   = os.getenv("LOCATION")  if os.getenv("LOCATION") else os.getenv("GOOGLE_CLOUD_LOCATION")
MODEL      = os.getenv("MODEL", "gemini-2.0-flash")

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID environment variable is required")

# --- Custom Orchestrator Agent ---
class CustomEmailProcessorAgent(BaseAgent):
    """
    An ADK agent that orchestrates a multi-step workflow for processing IT support emails.

    The workflow includes:
     1. Receives customer support requests.
     2. Drafts an email response to the customer.
     3. Reviews the email draft for tone and quality.
     4. Finalizes the draft for a human to review.
    """
    # --- Field Declarations for Pydantic ---
    sentimentReviewer: LlmAgent
    emailGenerator: LlmAgent
    emailReviewer: LlmAgent
    emailReviser: LlmAgent # New agent for revising the email
    loop_agent: LoopAgent
    sequential_agent: SequentialAgent
    revision_agent: SequentialAgent # New agent for the revision step

    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        sentimentReviewer: LlmAgent,
        emailGenerator: LlmAgent,
        emailReviewer: LlmAgent,
        emailReviser: LlmAgent,
    ):
        """
        Initializes the custom email processing agent and its sub-agents.

        Args:
            name: The name of the agent.
            sentimentReviewer: The agent for sentiment analysis.
            emailGenerator: The agent for generating the initial email draft.
            emailReviewer: The agent for reviewing the email draft.
            emailReviser: The agent for revising the email based on feedback.
        """
        # A sequential agent to perform the initial sentiment analysis and email generation
        sequential_agent = SequentialAgent(
            name="GenerateEmail", sub_agents=[sentimentReviewer, emailGenerator]
        )
        # A sequential agent for the review and revise loop
        revision_agent = SequentialAgent(
            name="ReviewAndReviseEmail", sub_agents=[emailReviewer, emailReviser]
        )
        # A loop agent that repeatedly calls the revision agent until a condition is met
        loop_agent = LoopAgent(
            name="ReviewEmail", sub_agents=[revision_agent], max_iterations=5
        )

        sub_agents_list = [
            sequential_agent,
            loop_agent,
        ]

        # Call the parent class's constructor with all sub-agents
        super().__init__(
            name=name,
            sentimentReviewer=sentimentReviewer,
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
        """
        Safely extracts the text content from the first event in a session.
        This handles different session event structures and returns None if text is not found.
        """
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
        """
        Implements the main asynchronous execution logic for the custom agent.

        Args:
            ctx: The invocation context containing session state and new messages.

        Yields:
            Event: An event representing a step in the agent's workflow.
        """
        logger.debug(f"[{self.name}] Starting email generation workflow.")

        # Set default values for optional email context fields to prevent KeyErrors later
        ctx.session.state.setdefault("from_email_address", "a customer")
        ctx.session.state.setdefault("subject", "a new support request")

        # Check for a new message and parse it
        bodyText = None
        user_message_text = None

        # Prefer new_message if present
        if getattr(ctx.session, "new_message", None) and getattr(ctx.session.new_message, "parts", None):
            part = ctx.session.new_message.parts[0]
            user_message_text = getattr(part, "text", None)

        # Fallback: extract from session events
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
                logger.debug("Saved JSON email context to session state.")
            except (json.JSONDecodeError, ValidationError):
                ctx.session.state["topic"] = user_message_text
                bodyText = user_message_text
                logger.debug(f"Saved plain text topic to session state: {user_message_text}")
        else:
            logging.warning("Could not extract user text for topic.")

        # Check for the AGENTSPACE_AI_URL environment variable
        agentspace_ai_url = os.getenv("AGENTSPACE_AI_URL")

        if agentspace_ai_url:
            # i) If the URL is specified, use the REST API call
            logger.info("AGENTSPACE_AI_URL specified. Using external API for email draft.")
            try:
                # Get a new access token
                credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
                auth_req = google.auth.transport.requests.Request()
                credentials.refresh(auth_req)
                access_token = credentials.token

                # Extract project_id and app_id from the URL
                url_parts = agentspace_ai_url.split('/')
                project_id = url_parts[5]
                app_id = url_parts[11]

                # Combine instructions with the topic for the query
                combined_query = helpbot_instruction + " " + bodyText
                logger.info(f"Sending query API - {combined_query}")

                # Construct the payload
                payload = {
                    "query": combined_query,
                    "pageSize": 10,
                    "queryExpansionSpec": {"condition": "AUTO"},
                    "spellCorrectionSpec": {"mode": "AUTO"},
                    "languageCode": "en-US",
                    "userInfo": {"timeZone": "Europe/London"},
                    "session": f"projects/{project_id}/locations/eu/collections/default_collection/engines/{app_id}/sessions/-"
                }

                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }

                # Make the API call
                response = requests.post(agentspace_ai_url, headers=headers, json=payload)
                response.raise_for_status() # Raise an exception for bad status codes

                # Process the response to get the draft
                search_results = response.json()
                logger.info(f"API Result is - {search_results}")
                draft_parts = []
                for result in search_results.get('results', []):
                    title = result.get('document', {}).get('derivedStructData', {}).get('title')
                    snippet = result.get('document', {}).get('derivedStructData', {}).get('snippet')
                    if title and snippet:
                        draft_parts.append(f"Subject: {title}\n\n{snippet}\n")
                
                # Use a simple combination of results as the draft
                if draft_parts:
                    email_draft = "\n---\n".join(draft_parts)
                else:
                    email_draft = "No relevant information found to create a draft. Please provide more details."
                
                # Save the new draft and other placeholder values to the session state
                ctx.session.state["email_draft"] = email_draft
                ctx.session.state["email_sentiment_obj"] = {"sentiment": "N/A"}
                ctx.session.state["email_review_comments"] = "No further comments."
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling external API: {e}")
                ctx.session.state["email_draft"] = f"Failed to get email draft from external API: {e}"
                ctx.session.state["email_sentiment_obj"] = {"sentiment": "N/A"}
                ctx.session.state["email_review_comments"] = "No further comments."
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                ctx.session.state["email_draft"] = f"An unexpected error occurred: {e}"
                ctx.session.state["email_sentiment_obj"] = {"sentiment": "N/A"}
                ctx.session.state["email_review_comments"] = "No further comments."

        else:
            # ii) If the URL isn't specified, use the current LlmAgent method
            logger.info("AGENTSPACE_AI_URL not specified. Using internal LLM agent.")
            
            # 1. Initial Email Generation and Sentiment Analysis
            logger.debug(f"[{self.name}] Running EmailGenerator...")
            async for event in self.sequential_agent.run_async(ctx):
                logger.debug(f"[{self.name}] Event from EmailGenerator: {event.model_dump_json(indent=2, exclude_none=True)}")
                yield event

            # Check if an email draft was successfully generated
            email_draft = ctx.session.state.get("email_draft")
            if not email_draft or not str(email_draft).strip():
                logger.error(f"[{self.name}] Failed to generate initial email. Aborting workflow.")
                return

            # 2. Reviewer Loop for continuous revision
            logger.debug(f"[{self.name}] Running Reviewer and Reviser loop...")
            # The LoopAgent calls the revision_agent (which contains the reviewer and reviser) until the condition is met.
            async for event in self.loop_agent.run_async(ctx):
                yield event
                email_review_comments = ctx.session.state.get("email_review_comments","").strip()
                # Stop the loop if reviewer says "No further comments"
                if "No further comments." in email_review_comments:
                    logger.debug(f"[{self.name}] Reviewer indicated completion. Stopping review loop.")
                    break

        # 3. Finalize and return the result
        final_session = ctx.session
        result = {
            "email_source": bodyText,
            "email_draft": final_session.state.get("email_draft"),
            "email_sentiment": final_session.state.get("email_sentiment_obj", {}).get("sentiment"),
            "email_review_comments": final_session.state.get("email_review_comments").split("\n\n")[-1].strip()
        }

        final_content = types.Content(
            role="model",
            parts=[types.Part(text=json.dumps(result, indent=2))]
        )

        # Yield the final event with the complete, structured response
        yield Event(
            author="CustomEmailProcessorAgent",
            content=final_content,
        )

        logger.debug(f"[{self.name}] Workflow finished.")
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

# --- LLM Agent Instructions ---
helpbot_instruction = (
    "You are HelpBot, an automated IT helpdesk email chatbot for a corporate IT support desk. "
    "You know common IT problems with Windows and Linux. "
    "Respond professionally and empathetically in email format for semi-IT literate users. "
    "Limit responses to IT topics only. "
    "Be truthful, never lie or make up facts; if unsure, explain why. "
    "Cite references when possible. "
    "Request further info with clear steps if needed. "
    "If unable to resolve, state you will create an IT ticket and provide: summary, description, priority, and classification (e.g., hardware, software, licensing, OS, user login)."
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
    "Output ONLY the single sentiment label as specified in the schema. Do not output anything else."
)

# --- Define the individual LLM agents ---
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

# NEW: Agent for revising the email
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
    output_key="email_draft", # Overwrite the email_draft with the revised version
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

# --- Create the custom agent instance ---
root_agent = CustomEmailProcessorAgent(
    name="CustomEmailProcessorAgent",
    sentimentReviewer=sentimentReviewer,
    emailGenerator=emailGenerator,
    emailReviewer=emailReviewer,
    emailReviser=emailReviser, # Pass the new agent here
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

    logger.debug(f"Initial session state: {session.state}")
    runner = Runner(
        agent=root_agent, # Pass the custom orchestrator agent
        app_name=APP_NAME,
        session_service=session_service
    )
    return session_service, runner

# --- Function to Interact with the Agent ---
async def call_agent_async(user_input_topic: str):
    """
    Sends a new topic to the agent and runs the workflow.
    
    Args:
        user_input_topic: The user's input, which can be a JSON string or plain text.
    """
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    session_service, runner = await setup_session_and_runner(user_id, session_id, user_input_topic)

    current_session = await session_service.get_session(app_name=APP_NAME,
                                                  user_id=user_id,
                                                  session_id=session_id)
    if not current_session:
        logger.error("Session not found!")
        return

    current_session.state["topic"] = user_input_topic
    logger.debug(f"Updated session state topic to: {user_input_topic}")

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
            logger.debug(f"Potential final response from [{event.author}]: {event.content.parts[0].text}")
            final_response = event.content.parts[0].text
    
    # Return the captured final response directly
    return final_response

# --- Main Execution Block for a local, working example ---
if __name__ == "__main__":
    # Example for JSON input
    json_message = json.dumps({
        "fromEmailAddress": "johndoe@example.com",
        "subject": "Urgent: Laptop is not turning on",
        "body": "Hi, I need help with my laptop that won't turn on. I've tried charging it and pressing the power button multiple times. Can you help me draft an email to tech support?"
    }, indent=2)

    # Example for plain string input
    string_message = "My printer is not working."

    # Choose which message to run based on command-line argument
    user_message = sys.argv[1] if len(sys.argv) > 1 else json_message

    final_state_json = asyncio.run(call_agent_async(user_message))
    print(final_state_json)
