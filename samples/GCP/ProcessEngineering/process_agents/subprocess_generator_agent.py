# process_agents/subprocess_generator_agent.py

from pydantic import BaseModel, Field
from typing import List, Optional

from .utils import load_instruction

from google.adk.agents import LlmAgent
from google.genai import types

MODEL = "gemini-2.0-flash"

# -----------------------------
# SUBPROCESS DATA SCHEMAS
# -----------------------------
class SubprocessStep(BaseModel):
    substep_name: str = Field(description="Name of the sub-step.")
    description: str = Field(description="What happens in this sub-step.")
    responsible_party: str = Field(description="Roles or teams responsible for this sub-step.")
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    estimated_duration: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)


class SubprocessFlow(BaseModel):
    step_name: str
    subprocess_flow: List[SubprocessStep]


# -----------------------------
# FACTORY FUNCTION (NEW)
# -----------------------------
def build_subprocess_generator_agent():
    return LlmAgent(
        name="Subprocess_Generator_Agent",
        model=MODEL,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.6,
            top_p=0.9,
            max_output_tokens=8192
        ),
        instruction=load_instruction("subprocess_generator_agent.txt"),
        input_schema=None,
        output_schema=SubprocessFlow,
        output_key="current_subprocess_flow",
    )


# Keep the original singleton for the CREATE pipeline
subprocess_generator_agent = build_subprocess_generator_agent()
