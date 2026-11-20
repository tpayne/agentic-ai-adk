"""ProcessEngineering's own Agent Card descriptors.

This is this project's own machine-readable capability-discovery metadata, designed for
MCP-style clients (Claude, Cursor, VS Code, OpenAI Agent SDK) to inspect what each
specialist agent/pipeline does -- purpose, inputs, outputs, produced/consumed artifacts,
operational permissions, provenance, and semantic versioning. It is NOT an implementation
of the external "Open Agentic Web" standard (https://github.com/cognizant-ai-labs/agentic-web),
which has a different model entirely (a resolved Neuro-San HOCON network published as
portable JSON, executed by a browser runtime with visitor-supplied LLM credentials). It
also predates, and is not an implementation of, the A2A protocol's own "Agent Card" concept.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class AgentProvenance:
    owner: str = "Agentic-AI-ADK"
    provider: str = "ProcessEngineering Platform"
    license: str = "Apache-2.0"
    trust_level: str = "verified"
    permissions: List[str] = field(default_factory=lambda: ["read_workspace", "write_artifacts"])


@dataclass
class AgentCard:
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    agent_type: str = "generator"  # generator, consultant, reviewer, simulator, orchestrator
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    provenance: AgentProvenance = field(default_factory=AgentProvenance)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        return result

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "agent_type": self.agent_type,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "artifacts": self.artifacts,
        }


AGENT_CARDS: Dict[str, AgentCard] = {
    # -------------------------------------------------------------
    # Orchestrator
    # -------------------------------------------------------------
    "process_architect": AgentCard(
        name="process_architect",
        description="Top-level master orchestrator that routes user requests across all ProcessEngineering specialist pipelines.",
        category="orchestration",
        agent_type="orchestrator",
        inputs=["user_prompt", "attachment_directory", "file_context"],
        outputs=["routed_response", "lifecycle_report"],
        artifacts=["process_definition", "high_level_design", "cloud_architecture", "requirements_summary", "proposal_response", "test_specification", "portfolio_backlog", "togaf_artifacts", "itsm_artifacts"],
        dependencies=[],
        tags=["orchestrator", "router", "intent_classification", "multi_domain"],
    ),

    # -------------------------------------------------------------
    # Requirements Domain
    # -------------------------------------------------------------
    "requirements_summary": AgentCard(
        name="requirements_summary",
        description="Extracts and synthesizes functional and non-functional requirements from document directories or text briefs.",
        category="requirements",
        agent_type="generator",
        inputs=["document_directory", "plain_text_brief", "extracted_chunks"],
        outputs=["requirements_summary"],
        artifacts=["requirements_summary"],
        dependencies=[],
        tags=["srs", "iso_29148", "functional_requirements", "non_functional_requirements"],
    ),
    "requirements_consultant": AgentCard(
        name="requirements_consultant",
        description="Explains, searches, and answers questions about the saved requirements register without mutating state.",
        category="requirements",
        agent_type="consultant",
        inputs=["requirements_summary", "query"],
        outputs=["explanation_report"],
        artifacts=["requirements_summary"],
        dependencies=["requirements_summary"],
        tags=["query", "qa", "read_only"],
    ),
    "requirements_reviewer": AgentCard(
        name="requirements_reviewer",
        description="Audits saved requirements for quality against ISO 29148 / IEEE 830 criteria (vagueness, testability, atomicity).",
        category="requirements",
        agent_type="reviewer",
        inputs=["requirements_summary"],
        outputs=["review_feedback"],
        artifacts=["requirements_summary"],
        dependencies=["requirements_summary"],
        tags=["audit", "quality_review", "iso_29148"],
    ),
    "requirements_simulation_query": AgentCard(
        name="requirements_simulation_query",
        description="Simulates requirements completeness, gap analysis, and conflicting constraint detection.",
        category="requirements",
        agent_type="simulator",
        inputs=["requirements_summary", "scenario_query"],
        outputs=["simulation_report"],
        artifacts=["requirements_summary", "simulation_report"],
        dependencies=["requirements_summary"],
        tags=["gap_analysis", "conflict_detection", "completeness"],
    ),
    "requirements_doc_pipeline": AgentCard(
        name="requirements_doc_pipeline",
        description="End-to-end pipeline to extract, synthesize, format, and generate a Word document for the Requirements Specification.",
        category="requirements",
        agent_type="generator",
        inputs=["source_directory", "plain_text_brief"],
        outputs=["requirements_summary", "requirements_document_docx"],
        artifacts=["requirements_summary"],
        dependencies=["requirements_summary"],
        tags=["pipeline", "docx_generation", "iso_table_formatting"],
    ),

    # -------------------------------------------------------------
    # Business Process Domain
    # -------------------------------------------------------------
    "process": AgentCard(
        name="process",
        description="Generates end-to-end business process models, roles, steps, approval gates, and BPMN-style swimlane diagrams.",
        category="process",
        agent_type="generator",
        inputs=["process_description", "requirements_summary"],
        outputs=["process_definition", "process_flow_diagram"],
        artifacts=["process_definition"],
        dependencies=[],
        tags=["bpmn", "swimlane", "workflow", "sop", "governance"],
    ),
    "process_update": AgentCard(
        name="process_update",
        description="Applies natural-language modifications to an existing business process while preserving step IDs and structure.",
        category="process",
        agent_type="generator",
        inputs=["process_definition", "modification_request"],
        outputs=["process_definition", "process_flow_diagram"],
        artifacts=["process_definition"],
        dependencies=["process"],
        tags=["update", "delta_patch", "refinement"],
    ),
    "process_consultant": AgentCard(
        name="process_consultant",
        description="Explains process steps, responsibilities, approval gates, and compliance rules from saved process definitions.",
        category="process",
        agent_type="consultant",
        inputs=["process_definition", "query"],
        outputs=["explanation_report"],
        artifacts=["process_definition"],
        dependencies=["process"],
        tags=["query", "read_only", "explanation"],
    ),
    "process_simulation_query": AgentCard(
        name="process_simulation_query",
        description="Simulates business process cycle time, throughput, bottleneck risks, and resource utilization.",
        category="process",
        agent_type="simulator",
        inputs=["process_definition", "query"],
        outputs=["simulation_report"],
        artifacts=["process_definition", "simulation_report"],
        dependencies=["process"],
        tags=["simulation", "bottleneck_analysis", "sla_modeling"],
    ),
    "process_scenario_tester": AgentCard(
        name="process_scenario_tester",
        description="Performs what-if contingency and failure analysis on business process execution paths.",
        category="process",
        agent_type="simulator",
        inputs=["process_definition", "what_if_scenario"],
        outputs=["impact_assessment"],
        artifacts=["process_definition"],
        dependencies=["process"],
        tags=["what_if", "resilience", "contingency"],
    ),

    # -------------------------------------------------------------
    # Technical Architecture & Design Document Domain
    # -------------------------------------------------------------
    "design": AgentCard(
        name="design",
        description="Creates comprehensive High-Level Design (HLD) and Low-Level Design (LLD) documents with component and integration specs.",
        category="design",
        agent_type="generator",
        inputs=["system_brief", "requirements_summary"],
        outputs=["high_level_design", "low_level_design", "design_document_docx", "design_flow_diagram"],
        artifacts=["high_level_design", "low_level_design"],
        dependencies=[],
        tags=["hld", "lld", "software_architecture", "api_design", "database_design"],
    ),
    "design_update": AgentCard(
        name="design_update",
        description="Modifies existing architecture designs, updating component topologies, interfaces, and security controls.",
        category="design",
        agent_type="generator",
        inputs=["high_level_design", "low_level_design", "modification_request"],
        outputs=["high_level_design", "low_level_design", "design_document_docx"],
        artifacts=["high_level_design", "low_level_design"],
        dependencies=["design"],
        tags=["architecture_evolution", "refinement", "delta_update"],
    ),
    "design_consultant": AgentCard(
        name="design_consultant",
        description="Explains component architecture, integration contracts, technology choices, and architectural trade-offs.",
        category="design",
        agent_type="consultant",
        inputs=["high_level_design", "low_level_design", "query"],
        outputs=["explanation_report"],
        artifacts=["high_level_design", "low_level_design"],
        dependencies=["design"],
        tags=["architecture_review", "qa", "read_only"],
    ),
    "design_simulation_query": AgentCard(
        name="design_simulation_query",
        description="Simulates architecture resilience, SPOFs, latency budgets, scalability limits, and security boundaries.",
        category="design",
        agent_type="simulator",
        inputs=["high_level_design", "low_level_design", "query"],
        outputs=["simulation_report"],
        artifacts=["high_level_design", "low_level_design", "simulation_report"],
        dependencies=["design"],
        tags=["spof_detection", "latency_budget", "security_boundary", "simulation"],
    ),
    "design_scenario_tester": AgentCard(
        name="design_scenario_tester",
        description="Traces hypothetical component failure and regional outage scenarios against technical design graphs.",
        category="design",
        agent_type="simulator",
        inputs=["high_level_design", "low_level_design", "what_if_scenario"],
        outputs=["impact_assessment"],
        artifacts=["high_level_design", "low_level_design"],
        dependencies=["design"],
        tags=["fault_injection", "disaster_recovery", "what_if"],
    ),

    # -------------------------------------------------------------
    # Cloud Architecture & DrawIO Domain
    # -------------------------------------------------------------
    "cloudarch": AgentCard(
        name="cloudarch",
        description="Generates professional cloud architecture diagrams in structured DrawIO / mxGraph XML.",
        category="cloudarch",
        agent_type="generator",
        inputs=["architecture_brief", "high_level_design", "requirements_summary"],
        outputs=["cloud_architecture", "drawio_xml"],
        artifacts=["cloud_architecture", "drawio_xml"],
        dependencies=[],
        tags=["aws", "azure", "gcp", "drawio", "mxgraph", "cloud_diagram"],
    ),
    "cloudarch_consultant": AgentCard(
        name="cloudarch_consultant",
        description="Explains cloud resources, connectivity, network boundaries, and design patterns in generated cloud architectures.",
        category="cloudarch",
        agent_type="consultant",
        inputs=["drawio_xml", "query"],
        outputs=["explanation_report"],
        artifacts=["cloud_architecture", "drawio_xml"],
        dependencies=["cloudarch"],
        tags=["read_only", "diagram_qa"],
    ),
    "cloudarch_simulation_query": AgentCard(
        name="cloudarch_simulation_query",
        description="Simulates availability zones, multi-region failover, load balancing, and connectivity paths in cloud diagrams.",
        category="cloudarch",
        agent_type="simulator",
        inputs=["drawio_xml", "query"],
        outputs=["simulation_report"],
        artifacts=["cloud_architecture", "drawio_xml", "simulation_report"],
        dependencies=["cloudarch"],
        tags=["reliability", "ha", "network_path_analysis"],
    ),
    "cloudarch_attack_simulation_query": AgentCard(
        name="cloudarch_attack_simulation_query",
        description="Simulates adversarial threat modeling, STRIDE vectors, perimeter traversal, and attack graphs on cloud architectures.",
        category="cloudarch",
        agent_type="simulator",
        inputs=["drawio_xml", "threat_query"],
        outputs=["security_audit_report"],
        artifacts=["cloud_architecture", "drawio_xml", "simulation_report"],
        dependencies=["cloudarch"],
        tags=["stride", "threat_modeling", "security", "attack_tree"],
    ),
    "cloudarch_finops": AgentCard(
        name="cloudarch_finops",
        description="Estimates monthly cloud infrastructure costs, pricing breakdowns, and FinOps optimization recommendations.",
        category="cloudarch",
        agent_type="simulator",
        inputs=["drawio_xml", "high_level_design"],
        outputs=["finops_report"],
        artifacts=["cloud_architecture", "drawio_xml", "finops_report"],
        dependencies=["cloudarch"],
        tags=["cost_estimation", "finops", "aws_pricing", "tco"],
    ),
    "cloudarch_iac": AgentCard(
        name="cloudarch_iac",
        description="Generates production-grade Infrastructure-as-Code packages (Terraform, CloudFormation, Pulumi) from cloud diagrams.",
        category="cloudarch",
        agent_type="generator",
        inputs=["drawio_xml", "high_level_design"],
        outputs=["iac_package"],
        artifacts=["cloud_architecture", "drawio_xml", "iac_package"],
        dependencies=["cloudarch"],
        tags=["terraform", "cloudformation", "pulumi", "iac_zip"],
    ),

    # -------------------------------------------------------------
    # Test Specification Domain
    # -------------------------------------------------------------
    "test_specification": AgentCard(
        name="test_specification",
        description="Generates end-to-end test specifications, test cases, and verification matrices mapped to requirements and designs.",
        category="testing",
        agent_type="generator",
        inputs=["requirements_summary", "high_level_design", "drawio_xml"],
        outputs=["test_specification", "test_specification_docx"],
        artifacts=["test_specification"],
        dependencies=[],
        tags=["qa", "test_cases", "traceability", "verification"],
    ),
    "test_consultant": AgentCard(
        name="test_consultant",
        description="Explains test coverage, test case steps, preconditions, and requirements verification status.",
        category="testing",
        agent_type="consultant",
        inputs=["test_specification", "query"],
        outputs=["explanation_report"],
        artifacts=["test_specification"],
        dependencies=["test_specification"],
        tags=["test_qa", "read_only"],
    ),
    "test_reviewer": AgentCard(
        name="test_reviewer",
        description="Audits test specifications for completeness, edge case coverage, and assertions quality.",
        category="testing",
        agent_type="reviewer",
        inputs=["test_specification"],
        outputs=["review_feedback"],
        artifacts=["test_specification"],
        dependencies=["test_specification"],
        tags=["test_audit", "quality_review"],
    ),

    # -------------------------------------------------------------
    # Portfolio Backlog Domain
    # -------------------------------------------------------------
    "portfolio_backlog": AgentCard(
        name="portfolio_backlog",
        description="Decomposes architecture and requirements into Enterprise Agile Epics, Features, and Stories with WSJF scoring and Excel workbook generation.",
        category="portfolio",
        agent_type="generator",
        inputs=["requirements_summary", "high_level_design"],
        outputs=["portfolio_backlog", "portfolio_backlog_xlsx"],
        artifacts=["portfolio_backlog"],
        dependencies=[],
        tags=["agile", "safe", "wsjf", "epics_features_stories", "excel_generation"],
    ),
    "portfolio_backlog_consultant": AgentCard(
        name="portfolio_backlog_consultant",
        description="Answers questions about an existing Enterprise Agile Portfolio Backlog, or general agile/SAFe backlog-planning questions that need no saved backlog at all.",
        category="portfolio",
        agent_type="consultant",
        inputs=["portfolio_backlog", "query"],
        outputs=["explanation_report"],
        artifacts=["portfolio_backlog"],
        dependencies=["portfolio_backlog"],
        tags=["agile_qa", "wsjf", "read_only", "general_knowledge"],
    ),

    # -------------------------------------------------------------
    # Proposal Response (RFP / RtP) Domain
    # -------------------------------------------------------------
    "proposal_response_pipeline": AgentCard(
        name="proposal_response_pipeline",
        description="Drafts formal commercial and technical responses to RFPs / client solicitations with compliance matrices and pricing estimates.",
        category="proposal",
        agent_type="generator",
        inputs=["requirements_summary", "system_brief"],
        outputs=["proposal_response", "proposal_response_docx"],
        artifacts=["proposal_response"],
        dependencies=["requirements_summary"],
        tags=["rfp", "rtp", "bid_response", "compliance_matrix"],
    ),
    "proposal_response_consultant": AgentCard(
        name="proposal_response_consultant",
        description="Explains drafted proposal responses, compliance claims, solution approaches, and commercial terms.",
        category="proposal",
        agent_type="consultant",
        inputs=["proposal_response", "query"],
        outputs=["explanation_report"],
        artifacts=["proposal_response"],
        dependencies=["proposal_response_pipeline"],
        tags=["proposal_qa", "read_only"],
    ),
    "proposal_response_reviewer": AgentCard(
        name="proposal_response_reviewer",
        description="Audits proposal responses for honesty of compliance claims, substance, and defensibility.",
        category="proposal",
        agent_type="reviewer",
        inputs=["proposal_response"],
        outputs=["review_feedback"],
        artifacts=["proposal_response"],
        dependencies=["proposal_response_pipeline"],
        tags=["rfp_audit", "compliance_check"],
    ),

    # -------------------------------------------------------------
    # TOGAF Enterprise Architecture Domain
    # -------------------------------------------------------------
    "togaf": AgentCard(
        name="togaf",
        description="Generates TOGAF-compliant enterprise architecture deliverables: Architecture Vision Document and Architecture Definition Document.",
        category="governance",
        agent_type="generator",
        inputs=["high_level_design", "requirements_summary"],
        outputs=["togaf_artifacts", "architecture_vision_docx", "architecture_definition_docx"],
        artifacts=["togaf_artifacts"],
        dependencies=["design"],
        tags=["togaf", "adm", "architecture_vision", "architecture_definition", "traceability_matrix"],
    ),
    "togaf_scenario_tester": AgentCard(
        name="togaf_scenario_tester",
        description="Traces qualitative impacts of capability deprecation, vendor changes, and compliance risks across TOGAF matrices.",
        category="governance",
        agent_type="simulator",
        inputs=["togaf_artifacts", "what_if_scenario"],
        outputs=["impact_assessment"],
        artifacts=["togaf_artifacts"],
        dependencies=["togaf"],
        tags=["togaf_what_if", "capability_impact", "traceability_audit"],
    ),
    "togaf_consultant": AgentCard(
        name="togaf_consultant",
        description="Answers questions about an existing TOGAF architecture artifact set, or general TOGAF/enterprise-architecture questions that need no saved artifact set at all.",
        category="governance",
        agent_type="consultant",
        inputs=["togaf_artifacts", "query"],
        outputs=["explanation_report"],
        artifacts=["togaf_artifacts"],
        dependencies=["togaf"],
        tags=["togaf_qa", "adm", "read_only", "general_knowledge"],
    ),

    # -------------------------------------------------------------
    # ITSM (IT Service Management) Domain
    # -------------------------------------------------------------
    "itsm": AgentCard(
        name="itsm",
        description="Generates a best-of-breed ITSM process document authored fresh from a brief: incident/problem/change management, request fulfillment, service level management, a light CMDB, and RACI governance, audited by compliance and structural risk/coverage review.",
        category="itsm",
        agent_type="generator",
        inputs=["itsm_brief", "directory_context", "requirements_summary"],
        outputs=["itsm_artifacts", "itsm_document_docx"],
        artifacts=["itsm_artifacts"],
        dependencies=[],
        tags=["itil", "incident_management", "problem_management", "change_management", "service_catalog", "cmdb", "raci"],
    ),
    "itsm_update": AgentCard(
        name="itsm_update",
        description="Applies a natural-language change request to an existing ITSM process document while preserving unrelated content, audited by the same compliance and risk/coverage review.",
        category="itsm",
        agent_type="generator",
        inputs=["itsm_artifacts", "modification_request"],
        outputs=["itsm_artifacts", "itsm_document_docx"],
        artifacts=["itsm_artifacts"],
        dependencies=["itsm"],
        tags=["update", "delta_patch", "refinement"],
    ),
    "itsm_import": AgentCard(
        name="itsm_import",
        description="Imports an already-existing ITSM process document (runbooks, incident/change/problem procedures, SLAs, a CMDB export) directly into the structured ITSM schema.",
        category="itsm",
        agent_type="generator",
        inputs=["document_directory"],
        outputs=["itsm_artifacts"],
        artifacts=["itsm_artifacts"],
        dependencies=[],
        tags=["import", "ingestion", "runbooks"],
    ),
    "itsm_consultant": AgentCard(
        name="itsm_consultant",
        description="Explains an existing ITSM process document -- incident/problem/change procedures, SLAs, the CMDB, RACI assignments, tooling -- without mutating state.",
        category="itsm",
        agent_type="consultant",
        inputs=["itsm_artifacts", "query"],
        outputs=["explanation_report"],
        artifacts=["itsm_artifacts"],
        dependencies=["itsm"],
        tags=["query", "qa", "read_only"],
    ),
    "itsm_reviewer": AgentCard(
        name="itsm_reviewer",
        description="Audits the saved ITSM process document for quality -- vague RACI entries, missing SLA targets, unverifiable escalation paths, incomplete process steps; fixes only when explicitly asked.",
        category="itsm",
        agent_type="reviewer",
        inputs=["itsm_artifacts"],
        outputs=["review_feedback"],
        artifacts=["itsm_artifacts"],
        dependencies=["itsm"],
        tags=["audit", "quality_review"],
    ),
    "itsm_scenario_tester": AgentCard(
        name="itsm_scenario_tester",
        description="Traces what-if scenarios (a role unavailable, a configuration item failing) against an existing ITSM process document's real RACI/escalation/CI dependency links.",
        category="itsm",
        agent_type="simulator",
        inputs=["itsm_artifacts", "what_if_scenario"],
        outputs=["impact_assessment"],
        artifacts=["itsm_artifacts"],
        dependencies=["itsm"],
        tags=["what_if", "dependency_tracing", "raci"],
    ),
    "itsm_simulation_query": AgentCard(
        name="itsm_simulation_query",
        description="Runs a structural risk/coverage analysis over an existing ITSM process document -- role-concentration bottlenecks, missing escalation paths, missing SLA measurement fields, outsized CI blast radius, RACI coverage gaps. Not a timing/cost simulation.",
        category="itsm",
        agent_type="simulator",
        inputs=["itsm_artifacts", "query"],
        outputs=["simulation_report"],
        artifacts=["itsm_artifacts", "simulation_report"],
        dependencies=["itsm"],
        tags=["structural_analysis", "bottleneck_analysis", "coverage_gaps"],
    ),

    # -------------------------------------------------------------
    # Document Regeneration Utility
    # -------------------------------------------------------------
    "regenerate_document": AgentCard(
        name="regenerate_document",
        description="Standalone document renderer that compiles saved artifact data into formatted ISO Word documents and diagrams.",
        category="utility",
        agent_type="generator",
        inputs=["saved_json_artifact"],
        outputs=["rendered_docx", "rendered_png"],
        artifacts=["process_definition", "high_level_design", "requirements_summary", "proposal_response", "test_specification", "togaf_artifacts", "itsm_artifacts"],
        dependencies=[],
        tags=["docgen", "docx", "rendering"],
    ),
}


def get_all_agent_cards() -> List[Dict[str, Any]]:
    """Returns all Agent Cards in detailed dictionary format."""
    return [card.to_dict() for card in AGENT_CARDS.values()]


def get_agent_card(name: str) -> Optional[Dict[str, Any]]:
    """Look up an individual Agent Card by name (case-insensitive and alias-tolerant)."""
    if not name:
        return None
    # 1. Exact key match
    if name in AGENT_CARDS:
        return AGENT_CARDS[name].to_dict()

    # 2. Case-insensitive key or card.name match
    target = name.strip().lower()
    for key, card in AGENT_CARDS.items():
        if key.lower() == target or card.name.lower() == target:
            return card.to_dict()

    # 3. Normalized alias (e.g. Design_Agent -> design, Design_Pipeline -> design)
    normalized = target.replace("-", "_")
    if normalized.endswith("_agent"):
        trimmed = normalized[:-6]
    elif normalized.endswith("_pipeline"):
        trimmed = normalized[:-9]
    else:
        trimmed = normalized

    for key, card in AGENT_CARDS.items():
        if key.lower() == trimmed or card.name.lower() == trimmed:
            return card.to_dict()

    return None


def list_agent_summaries(category: Optional[str] = None, artifact: Optional[str] = None, agent_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """List agent summaries with optional category/artifact/agent_type filtering."""
    results = []
    for card in AGENT_CARDS.values():
        if category and card.category.lower() != category.lower():
            continue
        if agent_type and card.agent_type.lower() != agent_type.lower():
            continue
        if artifact and artifact.lower() not in [a.lower() for a in card.artifacts]:
            continue
        results.append(card.to_summary_dict())
    return results
