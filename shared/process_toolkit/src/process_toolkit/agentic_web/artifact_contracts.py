"""ProcessEngineering's own Artifact Contracts & Registry.

Provides this project's own envelope metadata, artifact schemas, and contract discovery
for all engineering artifacts produced across the ProcessEngineering suite. This is a
self-contained convention for this project's Agent Discovery API -- it is not an
implementation of the external "Open Agentic Web" standard
(https://github.com/cognizant-ai-labs/agentic-web), which defines no such envelope/contract
concept at all.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class ArtifactContract:
    artifact_type: str
    name: str
    description: str
    version: str = "1.0"
    producer: str = ""
    file_format: str = "json"
    canonical_filename: str = ""
    schema_fields: List[str] = field(default_factory=list)
    mime_type: str = "application/json"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


ARTIFACT_CONTRACTS: Dict[str, ArtifactContract] = {
    "requirements_summary": ArtifactContract(
        artifact_type="requirements_summary",
        name="Requirements Register & Summary",
        description="Structured register of functional requirements, non-functional requirements, constraints, assumptions, and stakeholder needs.",
        version="1.0",
        producer="requirements_summary",
        file_format="json",
        canonical_filename="requirements_summary.json",
        schema_fields=["functional_requirements", "non_functional_requirements", "constraints", "assumptions", "stakeholders"],
        mime_type="application/json",
    ),
    "process_definition": ArtifactContract(
        artifact_type="process_definition",
        name="Business Process Definition",
        description="Business process specification including process steps, swimlanes, approval gates, KPIs, and responsible parties.",
        version="1.0",
        producer="process",
        file_format="json",
        canonical_filename="process_data.json",
        schema_fields=["process_name", "version", "introduction", "purpose", "scope", "process_owner", "process_steps"],
        mime_type="application/json",
    ),
    "high_level_design": ArtifactContract(
        artifact_type="high_level_design",
        name="High-Level Architecture Design",
        description="System architecture design covering components, topologies, integration points, security architecture, and quality attributes.",
        version="1.0",
        producer="design",
        file_format="json",
        canonical_filename="design_data.json",
        schema_fields=["document_metadata", "system_context", "high_level_design", "deployment_topology", "security_architecture"],
        mime_type="application/json",
    ),
    "low_level_design": ArtifactContract(
        artifact_type="low_level_design",
        name="Low-Level Technical Design",
        description="Detailed technical component specifications, API endpoint contracts, schemas, and database data models.",
        version="1.0",
        producer="design",
        file_format="json",
        canonical_filename="design_data.json",
        schema_fields=["low_level_design.component_specifications", "low_level_design.api_specifications", "low_level_design.database_design"],
        mime_type="application/json",
    ),
    "cloud_architecture": ArtifactContract(
        artifact_type="cloud_architecture",
        name="Cloud Architecture Model",
        description="Structured cloud infrastructure model mapping cloud services, VPCs, subnets, and data-plane relationships.",
        version="1.0",
        producer="cloudarch",
        file_format="xml",
        canonical_filename="cloudarch_drawio.xml",
        schema_fields=["mxGraphModel", "root", "mxCell"],
        mime_type="application/xml",
    ),
    "drawio_xml": ArtifactContract(
        artifact_type="drawio_xml",
        name="Draw.io / mxGraph Diagram XML",
        description="Raw XML representation of the visual cloud architecture diagram consumable by Draw.io and desktop editors.",
        version="1.0",
        producer="cloudarch",
        file_format="xml",
        canonical_filename="cloudarch_drawio.xml",
        schema_fields=["mxGraphModel"],
        mime_type="application/xml",
    ),
    "simulation_report": ArtifactContract(
        artifact_type="simulation_report",
        name="Architecture & Simulation Report",
        description="Simulation assessment report covering single points of failure (SPOF), latency budgets, resilience, and security boundaries.",
        version="1.0",
        producer="design_simulation_query",
        file_format="json",
        canonical_filename="iteration_feedback_simulation.json",
        schema_fields=["status", "data", "issues", "spofs", "latency_budget_risk", "security_risk"],
        mime_type="application/json",
    ),
    "finops_report": ArtifactContract(
        artifact_type="finops_report",
        name="FinOps Cost Assessment Report",
        description="Infrastructure cost modeling, itemized cloud service pricing, and cost-reduction recommendations.",
        version="1.0",
        producer="cloudarch_finops",
        file_format="json",
        canonical_filename="iteration_feedback.json",
        schema_fields=["estimated_monthly_cost_usd", "breakdown", "optimizations"],
        mime_type="application/json",
    ),
    "iac_package": ArtifactContract(
        artifact_type="iac_package",
        name="Infrastructure-as-Code Deployment Package",
        description="Zip archive containing syntactically validated Terraform/CloudFormation templates reflecting the architecture.",
        version="1.0",
        producer="cloudarch_iac",
        file_format="zip",
        canonical_filename="cloudarch_iac.zip",
        schema_fields=["main.tf", "variables.tf", "outputs.tf"],
        mime_type="application/zip",
    ),
    "test_specification": ArtifactContract(
        artifact_type="test_specification",
        name="Test Specification & Verification Matrix",
        description="System test plan, functional/integration test scenarios, assertions, and requirement traceability coverage.",
        version="1.0",
        producer="test_specification",
        file_format="json",
        canonical_filename="test_specification.json",
        schema_fields=["test_specification_metadata", "test_cases", "traceability_matrix", "verification_summary"],
        mime_type="application/json",
    ),
    "portfolio_backlog": ArtifactContract(
        artifact_type="portfolio_backlog",
        name="Enterprise Agile Portfolio Backlog",
        description="Hierarchical backlog of Epics, Features, and Stories with WSJF scoring, effort estimates, and labor costing.",
        version="1.0",
        producer="portfolio_backlog",
        file_format="json",
        canonical_filename="portfolio_backlog.json",
        schema_fields=["epics", "features", "stories", "assumptions", "financial_summary"],
        mime_type="application/json",
    ),
    "project_plan": ArtifactContract(
        artifact_type="project_plan",
        name="Project Plan (MSPDI XML)",
        description="Microsoft Project interchange format XML project plan with scheduled tasks, hierarchy, durations, calendar exceptions, resources, and assignments.",
        version="1.0",
        producer="project_plan_export",
        file_format="xml",
        canonical_filename="portfolio_backlog_project_plan.xml",
        schema_fields=["tasks", "resources", "assignments", "calendars", "start_date", "finish_date"],
        mime_type="application/xml",
    ),
    "pert_cpm": ArtifactContract(
        artifact_type="pert_cpm",
        name="PERT/CPM Network Diagram",
        description="Critical Path Method (CPM) and PERT network diagram displaying activity durations, early/late dates, slack/float, and critical path highlighting.",
        version="1.0",
        producer="project_plan_export",
        file_format="png",
        canonical_filename="portfolio_backlog_pert_cpm.png",
        schema_fields=["nodes", "critical_path", "float_calculations"],
        mime_type="image/png",
    ),
    "togaf_artifacts": ArtifactContract(
        artifact_type="togaf_artifacts",
        name="TOGAF Enterprise Architecture Artifacts",
        description="Comprehensive TOGAF ADM deliverable set: Architecture Vision, Architecture Requirements, Principles, Phases B/C/D/E/F/G.",
        version="1.0",
        producer="togaf",
        file_format="json",
        canonical_filename="togaf_data.json",
        schema_fields=["document_metadata", "architecture_vision", "architecture_requirements_specification", "business_architecture", "data_architecture", "application_architecture", "technology_architecture"],
        mime_type="application/json",
    ),
    "itsm_artifacts": ArtifactContract(
        artifact_type="itsm_artifacts",
        name="ITSM Process Document",
        description="Best-of-breed ITSM process document: service catalog, incident/problem/change management, request fulfillment, service level management, a light CMDB, and RACI governance.",
        version="1.0",
        producer="itsm",
        file_format="json",
        canonical_filename="itsm_data.json",
        schema_fields=["document_metadata", "service_catalog", "incident_management", "problem_management", "change_management", "request_fulfillment", "service_level_management", "configuration_management", "raci_matrix"],
        mime_type="application/json",
    ),
    "proposal_response": ArtifactContract(
        artifact_type="proposal_response",
        name="Commercial & Technical Proposal Response (RtP/RFP)",
        description="Structured formal bid response including executive summary, compliance matrix, technical solution, and pricing.",
        version="1.0",
        producer="proposal_response_pipeline",
        file_format="json",
        canonical_filename="proposal_response.json",
        schema_fields=["executive_summary", "compliance_matrix", "solution_overview", "implementation_plan", "pricing_and_terms"],
        mime_type="application/json",
    ),
}


def wrap_artifact_envelope(
    artifact_type: str,
    data: Any,
    producer: Optional[str] = None,
    artifact_id: Optional[str] = None,
    version: str = "1.0",
) -> Dict[str, Any]:
    """Wraps raw artifact data in this project's own standard artifact envelope."""
    contract = ARTIFACT_CONTRACTS.get(artifact_type)
    effective_producer = producer or (contract.producer if contract else "process_engineering")
    effective_id = artifact_id or f"{artifact_type[:3].upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"

    return {
        "artifact_id": effective_id,
        "artifact_type": artifact_type,
        "version": version,
        "producer": effective_producer,
        "created": datetime.now(timezone.utc).isoformat(),
        "contract_version": "1.0",
        "data": data,
    }


def get_artifact_contract(artifact_type: str) -> Optional[Dict[str, Any]]:
    """Returns the contract specification for a given artifact type (case-insensitive)."""
    if not artifact_type:
        return None
    if artifact_type in ARTIFACT_CONTRACTS:
        return ARTIFACT_CONTRACTS[artifact_type].to_dict()
    target = artifact_type.strip().lower().replace("-", "_")
    for ext in (".json", ".xml", ".zip", ".docx"):
        if target.endswith(ext):
            target = target[: -len(ext)]
    for key, contract in ARTIFACT_CONTRACTS.items():
        if key.lower() == target or contract.artifact_type.lower() == target:
            return contract.to_dict()
    return None


def list_all_artifact_contracts() -> List[Dict[str, Any]]:
    """Returns all registered artifact contracts."""
    return [contract.to_dict() for contract in ARTIFACT_CONTRACTS.values()]
