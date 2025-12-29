# process_agents/subprocess_generator_agent.py

from pydantic import BaseModel, Field
from typing import List, Optional

from google.adk.agents import LlmAgent
from google.genai import types

MODEL = "gemini-2.0-flash"


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


subprocess_instruction = (
    "You are an expert process engineer. You are given a single top-level process step "
    "from a broader SDLC, migration, or business process. Your task is to expand that step "
    "into a detailed level-2/3 subprocess.\n\n"
    "You will be given these fields:\n"
    "- step_name: name of the top-level step (e.g., 'Planning')\n"
    "- description: narrative of what happens in this step\n"
    "- responsible_party: roles or teams responsible\n"
    "- deliverables: list of key deliverables\n"
    "- success_criteria: list of success measures\n\n"
    "Your job is to break this into 3–10 ordered sub-steps that could be implemented "
    "by a delivery team. For each sub-step, specify:\n"
    "- substep_name\n"
    "- description\n"
    "- responsible_party\n"
    "- inputs (relevant artifacts, information, or outputs from previous steps)\n"
    "- outputs (artifacts or decisions produced)\n"
    "- estimated_duration (rough, human-friendly)\n"
    "- dependencies (names of prior sub-steps, if any)\n"
    "- success_criteria (how to know the sub-step is complete)\n\n"
    "Return ONLY a JSON object matching the SubprocessFlow schema. Do not include any "
    "extra text, explanations, or formatting."
)


subprocess_generator_agent = LlmAgent(
    name="Subprocess_Generator_Agent",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.6,
        top_p=0.9,
    ),
    instruction=(
        subprocess_instruction +
        "\n\nThe current top-level step JSON is in {{current_process_step}}."
    ),
    input_schema=None,
    output_schema=SubprocessFlow,
    output_key="current_subprocess_flow",
)
