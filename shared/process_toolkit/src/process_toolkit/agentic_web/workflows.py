"""ProcessEngineering's own engineering lifecycle workflow publication.

Exposes this project's own machine-readable workflow sequences, phase transitions, and
agent coordination graphs, consumable by external orchestration engines and multi-agent
frameworks via this project's Agent Discovery API. Not an implementation of the external
"Open Agentic Web" standard (https://github.com/cognizant-ai-labs/agentic-web), which
defines no such workflow-publication concept.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowDefinition:
    workflow: str
    name: str
    description: str
    version: str = "1.0.0"
    steps: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    produced_artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


WORKFLOW_DEFINITIONS: Dict[str, WorkflowDefinition] = {
    "architecture_lifecycle": WorkflowDefinition(
        workflow="architecture_lifecycle",
        name="Cloud & Software Architecture Lifecycle",
        description="End-to-end technical engineering lifecycle from requirements to HLD/LLD design, simulation, Draw.io diagramming, FinOps cost estimation, and IaC generation.",
        version="1.0.0",
        steps=[
            "requirements_summary",
            "design",
            "design_simulation_query",
            "cloudarch",
            "cloudarch_simulation_query",
            "cloudarch_finops",
            "cloudarch_iac",
        ],
        required_inputs=["system_brief", "document_directory"],
        produced_artifacts=["requirements_summary", "high_level_design", "low_level_design", "cloud_architecture", "drawio_xml", "simulation_report", "finops_report", "iac_package"],
    ),
    "process_engineering_lifecycle": WorkflowDefinition(
        workflow="process_engineering_lifecycle",
        name="Business Process Engineering & Optimization Lifecycle",
        description="Business process modeling lifecycle from requirements extraction to BPMN workflow generation, SLA simulation, what-if contingency testing, and iterative refinement.",
        version="1.0.0",
        steps=[
            "requirements_summary",
            "process",
            "process_simulation_query",
            "process_scenario_tester",
            "process_update",
        ],
        required_inputs=["process_description"],
        produced_artifacts=["requirements_summary", "process_definition", "simulation_report"],
    ),
    "enterprise_architecture_togaf_lifecycle": WorkflowDefinition(
        workflow="enterprise_architecture_togaf_lifecycle",
        name="TOGAF Enterprise Architecture Lifecycle",
        description="TOGAF ADM Phases A-G governance lifecycle producing Architecture Vision, Architecture Requirements, Principles, and Architecture Definition deliverables.",
        version="1.0.0",
        steps=[
            "requirements_summary",
            "design",
            "togaf",
            "togaf_scenario_tester",
        ],
        required_inputs=["requirements_summary", "high_level_design"],
        produced_artifacts=["requirements_summary", "high_level_design", "togaf_artifacts"],
    ),
    "test_assurance_lifecycle": WorkflowDefinition(
        workflow="test_assurance_lifecycle",
        name="Software Quality & Verification Lifecycle",
        description="Comprehensive testing lifecycle generating traceability-driven test cases, test specifications, and quality reviews mapped to requirements and designs.",
        version="1.0.0",
        steps=[
            "requirements_summary",
            "design",
            "cloudarch",
            "test_specification",
            "test_reviewer",
        ],
        required_inputs=["requirements_summary", "high_level_design"],
        produced_artifacts=["requirements_summary", "high_level_design", "test_specification"],
    ),
    "portfolio_planning_lifecycle": WorkflowDefinition(
        workflow="portfolio_planning_lifecycle",
        name="Enterprise Agile Portfolio Planning Lifecycle",
        description="Agile portfolio breakdown lifecycle decomposing requirements and technical designs into Epics, Features, and Stories with WSJF scoring, quality review, and project plan export.",
        version="1.0.0",
        steps=[
            "requirements_summary",
            "design",
            "portfolio_backlog",
            "portfolio_backlog_reviewer",
            "project_plan_export",
            "project_plan_reviewer",
        ],
        required_inputs=["requirements_summary", "high_level_design"],
        produced_artifacts=["requirements_summary", "high_level_design", "portfolio_backlog", "project_plan"],
    ),
    "itsm_management_lifecycle": WorkflowDefinition(
        workflow="itsm_management_lifecycle",
        name="ITSM Process Management Lifecycle",
        description="ITIL service-management lifecycle authoring a best-of-breed ITSM process document (incident/problem/change management, request fulfillment, service level management, a light CMDB, RACI governance), with structural risk/coverage simulation, what-if scenario testing, and iterative update.",
        version="1.0.0",
        steps=[
            "itsm",
            "itsm_simulation_query",
            "itsm_scenario_tester",
            "itsm_update",
        ],
        required_inputs=["itsm_brief", "document_directory"],
        produced_artifacts=["itsm_artifacts", "simulation_report"],
    ),
    "bid_proposal_lifecycle": WorkflowDefinition(
        workflow="bid_proposal_lifecycle",
        name="Commercial Bid & RFP Response Lifecycle",
        description="RFP solicitation response lifecycle from client requirements ingestion to compliance matrix formulation, solution drafting, and audit review.",
        version="1.0.0",
        steps=[
            "requirements_summary",
            "proposal_response_pipeline",
            "proposal_response_reviewer",
        ],
        required_inputs=["document_directory", "rfp_text"],
        produced_artifacts=["requirements_summary", "proposal_response"],
    ),
}


def get_all_workflows() -> List[Dict[str, Any]]:
    """Returns all workflow definitions in dictionary format."""
    return [wf.to_dict() for wf in WORKFLOW_DEFINITIONS.values()]


def get_workflow(workflow_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve a specific workflow definition by name (case-insensitive)."""
    if not workflow_name:
        return None
    if workflow_name in WORKFLOW_DEFINITIONS:
        return WORKFLOW_DEFINITIONS[workflow_name].to_dict()
    target = workflow_name.strip().lower()
    for key, wf in WORKFLOW_DEFINITIONS.items():
        if key.lower() == target or wf.workflow.lower() == target or wf.name.lower() == target:
            return wf.to_dict()
    return None
