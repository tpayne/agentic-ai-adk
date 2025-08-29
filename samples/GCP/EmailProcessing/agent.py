import logging
import os
import json
import uuid
import asyncio

from typing import AsyncGenerator
from typing_extensions import override

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event

import google.auth
from pydantic import BaseModel, Field
import sys

# --- Constants ---
APP_NAME = "email_processing_app"

# ---- Load .env ----
load_dotenv()

# --- Configure Logging ---
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
LOGLEVEL = os.getenv("LOGLEVEL", "WARNING").upper()
if LOGLEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    LOGLEVEL = "WARNING"
logger.setLevel(LOGLEVEL)

# ---- Credentials ----
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
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION   = os.getenv("LOCATION", "us-central1")
MODEL      = os.getenv("MODEL", "gemini-2.0-flash")

if not PROJECT_ID:
    raise RuntimeError("PROJECT_ID environment variable is required")

# --- Custom Orchestrator Agent ---
class CustomEmailProcessorAgent(BaseAgent):
    """
    A stable-GA ADK agent that:
     1. Receives customer support requests
     2. Drafts an email response to the customer
     3. Reviews the email draft for tone and quality
     4. Finalizes the draft for a human to review.
    """
    # --- Field Declarations for Pydantic ---
    # Declare the agents passed during initialization as class attributes with type hints
    sentimentReviewer: LlmAgent
    emailGenerator: LlmAgent
    emailReviewer: LlmAgent
    loop_agent: LoopAgent
    sequential_agent: SequentialAgent

    # model_config allows setting Pydantic configurations if needed, e.g., arbitrary_types_allowed
    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        sentimentReviewer: LlmAgent,
        emailGenerator: LlmAgent,
        emailReviewer: LlmAgent,
    ):
        # Create internal agents *before* calling super().__init__
        sequential_agent = SequentialAgent(
            name="GenerateEmail", sub_agents=[sentimentReviewer, emailGenerator]
        )
        loop_agent = LoopAgent(
            name="ReviewEmail", sub_agents=[emailReviewer], max_iterations=2
        )

        # Define the sub_agents list for the framework
        sub_agents_list = [
            sequential_agent,
            loop_agent,
        ]

        # Pydantic will validate and assign them based on the class annotations.
        super().__init__(
            name=name,
            sentimentReviewer=sentimentReviewer,
            emailGenerator=emailGenerator,
            emailReviewer=emailReviewer,
            sequential_agent=sequential_agent,
            loop_agent=loop_agent,
            sub_agents=sub_agents_list, # Pass the sub_agents list directly
        )

    @staticmethod
    def extract_user_text(session) -> str | None:
        """
        Safely grab the first `text` from session.events[0].content.parts[0].
        Returns None if any level is missing.
        """
        try:
            # If session is a dict:
            events = session["events"]
            first_part = events[0]["content"]["parts"][0]
            return first_part["text"]
        except (KeyError, IndexError, TypeError):
            pass

        try:
            # If session is an object:
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
        logger.debug(f"[{self.name}] Starting email generation workflow.")
    
        logger.debug(f"[{self.name}] InvocationContext structure: {json.dumps(ctx.session.model_dump(), indent=2, default=str)}")
        if hasattr(ctx.session, "new_message") and ctx.session.new_message:
            if ctx.session.new_message.parts and ctx.session.new_message.parts[0].text:
                user_input_topic = ctx.session.new_message.parts[0].text
                ctx.session.state["topic"] = user_input_topic
                logger.info(f"Saved user message to session state as `topic`: {user_input_topic}")
        else:
            user_input_topic = CustomEmailProcessorAgent.extract_user_text(ctx.session)
            if user_input_topic is not None:
                ctx.session.state["topic"] = user_input_topic
            else:
                logging.warning("Could not extract user text for topic.")

        # 1. Initial Email Generation
        logger.debug(f"[{self.name}] Running EmailGenerator...")
        async for event in self.sequential_agent.run_async(ctx):
            logger.debug(f"[{self.name}] Event from EmailGenerator: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event        

        sentiment_check_result = ctx.session.state.get("sentiment_check_result")
        current_email_result = ctx.session.state.get("current_email")

        # Check if email was generated before proceeding
        if not current_email_result or not str(current_email_result).strip():
            logger.error(f"[{self.name}] Failed to generate initial email. Aborting workflow.")
            return  # Stop processing if initial email failed
        
        logger.debug(f"[{self.name}] Sentiment check result: {sentiment_check_result}")
        logger.debug(f"[{self.name}] Email state after generator: {current_email_result}")

        # 2. Reviewer Loop
        logger.debug(f"[{self.name}] Running EmailReviewerLoop...")
        # Use the loop_agent instance attribute assigned during init
        async for event in self.loop_agent.run_async(ctx):
            logger.debug(f"[{self.name}] Event from EmailReviewerLoop: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event

        current_email_result = ctx.session.state.get("current_email")
        logger.debug(f"[{self.name}] Email state after loop: {current_email_result}")
        logger.debug(f"[{self.name}] Workflow finished.")

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
    "You are an expert email reviewer. Review the email provided: {{current_email}}. Provide 1-2 sentences of constructive criticism "
    "on how to improve it. Focus on clarity, tone, and professionalism."
)

sentiment_instruction = (
    "You are an expert in analyzing email sentiment. Review the email provided: {{topic}}. "
    "Identify the overall sentiment of the email as one of the following labels: Professional, Frustrated, Impatient, or Eeutral. "
    "Output ONLY the single sentiment label and NOTHING else."
)

# --- Define the individual LLM agents ---
emailGenerator = LlmAgent(
    name="EmailGenerator",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        top_p=1,
    ),
    instruction=helpbot_instruction + " Write a concise email response to the following customer inquiry: {{topic}}",
    input_schema=None,
    output_key="current_email",
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
    output_key="current_reviewer",
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
    output_key="sentiment_check_result",
)

# --- Create the custom agent instance ---
root_agent = CustomEmailProcessorAgent(
    name="CustomEmailProcessorAgent",
    sentimentReviewer=sentimentReviewer,
    emailGenerator=emailGenerator,
    emailReviewer=emailReviewer,
)

# --- Main Execution Block for a local, working example ---
async def setup_session_and_runner(user_id: str, session_id: str, email_topic: str):
    """
    A simple async function to demonstrate the agent's capabilities.
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
    Sends a new topic to the agent (overwriting the initial one if needed)
    and runs the workflow.
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
        parts=[types.Part(text=f"Generate a draft email in response to: {user_input_topic}")]
    )

    events = runner.run_async(user_id=user_id, 
                              session_id=session_id, 
                              new_message=content)

    final_response = "No final response captured."
    async for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            logger.debug(f"Potential final response from [{event.author}]: {event.content.parts[0].text}")
            final_response = event.content.parts[0].text

    logger.debug("\n--- Agent Interaction Result ---")
    logger.debug("Agent Final Response: ", final_response)

    final_session = await session_service.get_session(app_name=APP_NAME, 
                                                user_id=user_id, 
                                                session_id=session_id)
    logger.debug("Final Session State:")
    logger.debug(json.dumps(final_session.state, indent=2))
    logger.debug("-------------------------------\n")
    print("\n--- Agent Processed email ---")

# --- Main Execution Block for a local, working example ---
if __name__ == "__main__":
    user_message = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Hi, I need help with my laptop that won't turn on. I've tried charging it and pressing the power button multiple times. Can you help me draft an email to tech support?"
    )

    asyncio.run(call_agent_async(user_message))
