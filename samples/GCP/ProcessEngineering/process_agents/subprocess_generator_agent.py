# process_agents/subprocess_generator_agent.py

from pydantic import BaseModel, Field
from typing import List, Optional

from .utils import (
    load_instruction,
    getProperty
)

from google.adk.agents import LlmAgent
from google.genai import types

MODEL = getProperty("MODEL")

# -----------------------------
# SUBPROCESS DATA SCHEMAS
# -----------------------------

class StepRiskControl(BaseModel):
    risk: str
    control: str

class ChangeManagement(BaseModel):
    change_request_process: str
    versioning_rules: str

class ContinuousImprovement(BaseModel):
    review_frequency: str
    improvement_inputs: List[str]

class SubprocessStep(BaseModel):
    substep_name: str = Field(description="Name of the sub-step.")
    description: str = Field(description="What happens in this sub-step.")
    responsible_party: str = Field(description="Roles or teams responsible for this sub-step.")
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    estimated_duration: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    purpose: str = Field(description="Why this sub-step exists.")
    scope: str = Field(description="Boundaries or limits of this sub-step.")
    process_owner: str = Field(description="Accountable role for this sub-step.")
    triggers: List[str] = Field(default_factory=list, description="Events that initiate this sub-step.")
    end_conditions: List[str] = Field(default_factory=list, description="Conditions defining completion.")

    step_risks_and_controls: List[StepRiskControl] = Field(
        default_factory=list,
        description="List of risks and their corresponding controls."
    )

    governance_requirements: List[str] = Field(
        default_factory=list,
        description="Oversight or compliance requirements for this sub-step."
    )

    change_management: List[ChangeManagement] = Field(
        default_factory=list,
        description="Change management processes for this sub-step."
    )

    continuous_improvement: List[ContinuousImprovement] = Field(
        default_factory=list,
        description="Continuous improvement processes for this sub-step."
    )


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
                temperature=0.1, # Lowered to 0.1 for maximum structural stability
                top_p=0.9,
                response_mime_type="application/json",
            ),
            instruction=load_instruction("subprocess_generator_agent.txt"),
            input_schema=None,
            output_schema=SubprocessFlow,
            output_key="current_subprocess_flow",
        )


# Keep the original singleton for the CREATE pipeline
subprocess_generator_agent = build_subprocess_generator_agent()
