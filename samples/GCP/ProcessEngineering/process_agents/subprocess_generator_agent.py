# process_agents/subprocess_generator_agent.py

from pydantic import BaseModel, Field
from typing import List, Optional

from .utils import load_instruction

from google.adk.agents import LlmAgent
from google.genai import types

MODEL = "gemini-2.0-flash"

#-----------------------------
# SUBPROCESS DATA SCHEMAS
#-----------------------------
class SubprocessStep(BaseModel):
    """Single sub-step in a level-2/3 subprocess flow."""
    substep_name: str = Field(description="Name of the sub-step.")
    description: str = Field(description="What happens in this sub-step.")
    responsible_party: str = Field(description="Roles or teams responsible for this sub-step.")
    inputs: List[str] = Field(default_factory=list, description="Key inputs or prerequisites.")
    outputs: List[str] = Field(default_factory=list, description="Key outputs or artifacts.")
    estimated_duration: Optional[str] = Field(
        default=None,
        description="Rough duration (e.g., '1-2 days', '2 weeks')."
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Other sub-steps or conditions that must be completed first."
    )
    success_criteria: List[str] = Field(
        default_factory=list,
        description="How to know this sub-step is complete and successful."
    )


class SubprocessFlow(BaseModel):
    """Structured subprocess definition for a single top-level step."""
    step_name: str = Field(description="Name of the parent top-level process step.")
    subprocess_flow: List[SubprocessStep] = Field(
        description="Ordered list of sub-steps that make up this subprocess."
    )

#-----------------------------
# SUBPROCESS GENERATOR AGENT
#-----------------------------
subprocess_generator_agent = LlmAgent(
    name="Subprocess_Generator_Agent",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.6,
        top_p=0.9,
    ),
    instruction=load_instruction("subprocess_generator_agent.txt"),
    input_schema=None,
    output_schema=SubprocessFlow,
    output_key="current_subprocess_flow",
)