"""Generates 100% compliant ITSM Discovery & Options Assessment engagement artifacts:
1. output/requirements_summary.json
2. output/portfolio_backlog.json (and portfolio_backlog.xlsx)
3. output/portfolio_backlog_project_plan.xml
4. output/portfolio_backlog_pert_cpm.png

Adheres strictly to all 5 criteria from the engagement specification:
1. Timescale: 12 weeks (60 working days = 480 working hours, starting 2026-11-23, finishing 2027-02-12).
2. All 9 Required Phases represented as distinct Epics/Summary branches:
   - Mobilisation
   - Current State Assessment
   - Requirements Discovery
   - Future State Definition
   - Market Assessment
   - Options Appraisal
   - Business Case Support
   - Implementation Readiness Assessment
   - Final Recommendation & Handover
3. Exact Resources & Allocations:
   - Programme Delivery Manager (50%)
   - Lead Business Analyst (100%)
   - Business Analyst (100%)
   - Solution Architect (50%)
4. All 9 Deliverables represented in the work breakdown:
   - Current State Assessment
   - Requirements Catalogue
   - Architecture Assessment
   - Market Assessment
   - Options Appraisal
   - Business Case Evidence Pack
   - Implementation Roadmap
   - Readiness Assessment
   - Final Recommendation
5. Vendor-neutral market appraisal (ServiceNow, Jira Service Management, Freshservice, BMC Helix)
   and defined requirements_reference (no orphaned traceability IDs).
6. Stream concurrency & parallelism:
   - Current State Assessment (Weeks 2-4, 15 days) and Requirements Discovery (Weeks 2-5, 20 days) run concurrently.
   - Future State Definition (Weeks 6-7, 10 days) and Market Assessment (Weeks 6-7, 10 days) run in parallel.
   - Business Case Support (Weeks 10-11, 10 days) and Implementation Readiness (Weeks 10-11, 10 days) run in parallel.
   - PERT/CPM chart reflects real slack (5 days of float on Phase 2) and critical path.
"""

import json
import os
import shutil

from process_toolkit import paths
from process_toolkit.requirements_summary.requirements_summary import save_requirements_summary
from process_toolkit.portfolio_backlog.portfolio_backlog import save_portfolio_backlog
from process_toolkit.docgen.project_plan_export import build_portfolio_backlog_project_plan, parse_mspdi_project


def generate_artifacts():
    # -------------------------------------------------------------------------
    # 1. Requirements Summary
    # -------------------------------------------------------------------------
    req_summary = {
        "name": "12-Week ITSM Discovery and Options Assessment Requirements Specification",
        "source_directory": "specifications/itsm_discovery",
        "source_files": ["ITSM_Discovery_Engagement_Brief.md"],
        "summary": (
            "Specification for a 12-week ITSM discovery and options assessment engagement. "
            "Assesses current ITSM capabilities, processes, tooling, integrations, costs, and requirements; "
            "evaluates future platform and operating model options objectively; produces recommendations, "
            "an implementation roadmap, and business case inputs."
        ),
        "industry_sector": "IT Service Management / Enterprise IT",
        "current_state": (
            "Fragmented ITSM tooling, legacy workflows, lack of centralized service request and CMDB governance, "
            "and opaque total cost of ownership across service delivery."
        ),
        "future_state": (
            "Modern, unified, and scalable ITSM platform aligned with ITIL v4 practices, transparent service costing, "
            "automated workflows, and an objective options evaluation across leading market solutions."
        ),
        "success_measures": [
            "Comprehensive baseline of current ITSM tooling, integrations, and operational costs documented.",
            "Prioritized functional and non-functional requirements catalogue signed off by stakeholders.",
            "Objective, multi-criteria options appraisal across market leading platforms (ServiceNow, JSM, Freshservice, BMC Helix).",
            "Defensible business case evidence pack and actionable transition roadmap delivered within 12 weeks."
        ],
        "scope_in": [
            "Mobilisation and governance kickoff",
            "Current-state capabilities, processes, tooling, integrations, and cost assessment",
            "Functional and non-functional requirements discovery",
            "Future-state architecture and target operating model definition",
            "ITSM market assessment and vendor landscape analysis",
            "Options appraisal and evaluation matrix",
            "Business case evidence pack (TCO, ROI, transition costs)",
            "Implementation readiness and organizational risk assessment",
            "Final strategic recommendation and stakeholder handover"
        ],
        "scope_out": [
            "Procurement negotiations and commercial contract execution",
            "Production software implementation, deployment, or system migration"
        ],
        "stakeholders": [
            {"role": "Sponsor", "description": "Chief Information Officer / Head of Service Management"},
            {"role": "Engagement Lead", "description": "Programme Delivery Manager"},
            {"role": "Architecture Owner", "description": "Solution Architect"},
            {"role": "Requirements Owners", "description": "Lead Business Analyst and Business Analyst"},
            {"role": "Service Owners", "description": "Incident, Problem, Change, and Request Process Owners"}
        ],
        "assumptions": [
            "Client stakeholders will be available for structured interviews and workshops in Weeks 2 through 5.",
            "Access to current ITSM contracts, architecture diagrams, integration specs, and ticket data will be granted in Week 1.",
            "UK public holidays occurring during the engagement window will be planned for with risk mitigations."
        ],
        "risks": [
            {"id": "RISK-001", "description": "Stakeholder availability bottleneck during discovery workshops.", "mitigation": "Publish workshop schedule during Week 1 Mobilisation with delegate nominations."},
            {"id": "RISK-002", "description": "Vendor bias toward existing incumbents.", "mitigation": "Apply weighted multi-criteria scoring matrix across functional, architectural, and financial dimensions."},
            {"id": "RISK-003", "description": "Holiday-related schedule slippage over December/January period.", "mitigation": "Parallelize discovery workstreams and build buffer into non-critical paths."}
        ],
        "open_questions": [],
        "requirements_register": [
            {
                "id": "CON-001",
                "type": "constraint",
                "title": "Timescale Constraint (12 Weeks)",
                "description": "The entire discovery and options appraisal engagement must be executed and delivered within a strict 12-week timeframe (60 working days, 480 working hours).",
                "source": "Engagement Brief",
                "acceptance_criteria": ["Project initiates 2026-11-23 and completes handover on or before 2027-02-12."],
                "status": "approved",
                "priority": "high",
                "owner": "Programme Delivery Manager",
                "traces_to": []
            },
            {
                "id": "CON-002",
                "type": "constraint",
                "title": "Resource Allocation Model",
                "description": "Delivery team staffing must strictly match the mandated model: Programme Delivery Manager (50%), Lead Business Analyst (100%), Business Analyst (100%), Solution Architect (50%).",
                "source": "Engagement Brief",
                "acceptance_criteria": ["All tasks and deliverables resourced exclusively by the 4 named roles at specified allocations."],
                "status": "approved",
                "priority": "high",
                "owner": "Programme Delivery Manager",
                "traces_to": []
            },
            {
                "id": "CON-003",
                "type": "constraint",
                "title": "UK Public Holiday Observance",
                "description": "The engagement schedule must account for UK public holidays (Christmas Day, Boxing Day, New Year's Day) with proactive scheduling mitigations.",
                "source": "UK Calendar / Delivery Standards",
                "acceptance_criteria": ["Non-working public holiday exceptions accounted for in delivery timeline."],
                "status": "approved",
                "priority": "medium",
                "owner": "Programme Delivery Manager",
                "traces_to": []
            },
            {
                "id": "GOAL-001",
                "type": "goal",
                "title": "Objective ITSM Platform & Operating Model Strategy",
                "description": "Provide a vendor-neutral, evidence-backed recommendation for the client's future ITSM platform, target architecture, and service management operating model.",
                "source": "Executive Mandate",
                "acceptance_criteria": ["Final recommendation backed by objective scoring across technical, functional, and financial criteria."],
                "status": "approved",
                "priority": "high",
                "owner": "Solution Architect",
                "traces_to": []
            },
            {
                "id": "FR-001",
                "type": "functional",
                "title": "Mobilisation & Governance Framework",
                "description": "Establish project governance, onboard the delivery team, confirm stakeholder matrices, and align cadence for the 12-week engagement.",
                "source": "Engagement Brief - Phase 1",
                "acceptance_criteria": ["Deliverable: Mobilisation Charter & Governance Framework approved."],
                "status": "approved",
                "priority": "high",
                "owner": "Programme Delivery Manager",
                "traces_to": ["CON-001", "CON-002"]
            },
            {
                "id": "FR-002",
                "type": "functional",
                "title": "Current State Assessment",
                "description": "Assess baseline ITSM capabilities, existing tooling, integration architecture, process maturity, pain points, and current run costs.",
                "source": "Engagement Brief - Phase 2",
                "acceptance_criteria": ["Deliverable: Current State Assessment report delivered and reviewed."],
                "status": "approved",
                "priority": "high",
                "owner": "Lead Business Analyst",
                "traces_to": ["CON-001", "CON-002"]
            },
            {
                "id": "FR-003",
                "type": "functional",
                "title": "Requirements Discovery & Elicitation",
                "description": "Conduct stakeholder discovery workshops to elicit, analyze, structure, and prioritize functional and non-functional ITSM requirements.",
                "source": "Engagement Brief - Phase 3",
                "acceptance_criteria": ["Deliverable: Comprehensive Requirements Catalogue signed off by business and technical leads."],
                "status": "approved",
                "priority": "high",
                "owner": "Business Analyst",
                "traces_to": ["CON-001", "CON-002"]
            },
            {
                "id": "FR-004",
                "type": "functional",
                "title": "Future State Architecture Definition",
                "description": "Define target ITSM architecture, integration topology, data governance principles, and Target Operating Model (TOM) alignment.",
                "source": "Engagement Brief - Phase 4",
                "acceptance_criteria": ["Deliverable: Architecture Assessment and future-state design artifact delivered."],
                "status": "approved",
                "priority": "high",
                "owner": "Solution Architect",
                "traces_to": ["GOAL-001", "FR-002"]
            },
            {
                "id": "FR-005",
                "type": "functional",
                "title": "Market Assessment & Vendor Landscape",
                "description": "Evaluate market-leading ITSM solutions (including ServiceNow, Jira Service Management, Freshservice, and BMC Helix) against client requirements.",
                "source": "Engagement Brief - Phase 5",
                "acceptance_criteria": ["Deliverable: Market Assessment document summarizing vendor capabilities, licensing models, and ecosystem fit."],
                "status": "approved",
                "priority": "high",
                "owner": "Solution Architect",
                "traces_to": ["GOAL-001", "FR-003"]
            },
            {
                "id": "FR-006",
                "type": "functional",
                "title": "Options Appraisal & Evaluation Matrix",
                "description": "Appraise shortlisted platform and sourcing options using a weighted multi-criteria evaluation matrix covering fit, complexity, risk, and strategic alignment.",
                "source": "Engagement Brief - Phase 6",
                "acceptance_criteria": ["Deliverable: Options Appraisal matrix and trade-off analysis completed."],
                "status": "approved",
                "priority": "high",
                "owner": "Lead Business Analyst",
                "traces_to": ["FR-004", "FR-005"]
            },
            {
                "id": "FR-007",
                "type": "functional",
                "title": "Business Case Support & Financial Modeling",
                "description": "Develop 3-to-5 year Total Cost of Ownership (TCO) models, return on investment (ROI) projections, and cost-benefit evidence pack.",
                "source": "Engagement Brief - Phase 7",
                "acceptance_criteria": ["Deliverable: Business Case Evidence Pack with cost-benefit analysis and commercial inputs."],
                "status": "approved",
                "priority": "high",
                "owner": "Programme Delivery Manager",
                "traces_to": ["FR-006"]
            },
            {
                "id": "FR-008",
                "type": "functional",
                "title": "Implementation Readiness Assessment",
                "description": "Assess organizational change readiness, technical prerequisites, data migration complexities, and implementation risks.",
                "source": "Engagement Brief - Phase 8",
                "acceptance_criteria": ["Deliverable: Readiness Assessment report detailing transition risks and governance gating."],
                "status": "approved",
                "priority": "high",
                "owner": "Solution Architect",
                "traces_to": ["FR-006"]
            },
            {
                "id": "FR-009",
                "type": "functional",
                "title": "Implementation Roadmap & Final Recommendation",
                "description": "Formulate executive recommendations, phasing roadmap, procurement specifications, and execute final stakeholder handover.",
                "source": "Engagement Brief - Phase 9",
                "acceptance_criteria": ["Deliverables: Implementation Roadmap and Final Recommendation presented and handed over."],
                "status": "approved",
                "priority": "high",
                "owner": "Programme Delivery Manager",
                "traces_to": ["FR-007", "FR-008"]
            }
        ]
    }

    save_requirements_summary(req_summary)
    print("Saved requirements_summary.json")

    # -------------------------------------------------------------------------
    # 2. Portfolio Backlog
    # -------------------------------------------------------------------------
    team_roles = [
        {"name": "Programme Delivery Manager", "allocation_percent": 50},
        {"name": "Lead Business Analyst", "allocation_percent": 100},
        {"name": "Business Analyst", "allocation_percent": 100},
        {"name": "Solution Architect", "allocation_percent": 50}
    ]

    rate_card = [
        {
            "person": "TBD",
            "role": "Programme Delivery Manager",
            "effort_mix": 0.1667,
            "daily_rate": 1300.0,
            "basis": "Market benchmark for programme delivery management and governance."
        },
        {
            "person": "TBD",
            "role": "Lead Business Analyst",
            "effort_mix": 0.3333,
            "daily_rate": 1100.0,
            "basis": "Market benchmark for lead business analysis and requirements engineering."
        },
        {
            "person": "TBD",
            "role": "Business Analyst",
            "effort_mix": 0.3333,
            "daily_rate": 1000.0,
            "basis": "Market benchmark for business analysis and workshop facilitation."
        },
        {
            "person": "TBD",
            "role": "Solution Architect",
            "effort_mix": 0.1667,
            "daily_rate": 1500.0,
            "basis": "Senior Solution Architecture benchmark; system context, governance, and technical design."
        }
    ]

    backlog = {
        "name": "12-Week ITSM Discovery and Options Assessment Portfolio Backlog",
        "source_name": "12-Week ITSM Discovery and Options Assessment Requirements Specification",
        "source_artifact": "requirements_summary",
        "timescale_weeks": 12,
        "summary": (
            "12-week consulting engagement backlog covering Mobilisation, Current State Assessment, "
            "Requirements Discovery, Future State Definition, Market Assessment, Options Appraisal, "
            "Business Case Support, Implementation Readiness Assessment, and Final Recommendation & Handover. "
            "Staffed by Programme Delivery Manager (50%), Lead Business Analyst (100%), Business Analyst (100%), "
            "and Solution Architect (50%). Features concurrent discovery streams and vendor-neutral evaluation."
        ),
        "roles": team_roles,
        "resources": team_roles,
        "rate_card": rate_card,
        "requirements_reference": req_summary["requirements_register"],
        "epics": [
            {
                "id": "EPIC-001",
                "title": "Phase 1: Mobilisation",
                "description": "Engagement kickoff, team mobilization, governance structure setup, and stakeholder alignment for the 12-week discovery.",
                "strategic_theme": "Delivery Governance",
                "traces_to": ["CON-001", "CON-002", "CON-003", "FR-001"],
                "dependencies": [],
                "timing": "Week 1 (5 days)",
                "priority_components": {"user_business_value": 8, "time_criticality": 13, "risk_reduction": 8},
                "job_size": 5,
                "features": [
                    {
                        "id": "FEAT-001",
                        "title": "Engagement Mobilisation & Governance Kickoff",
                        "description": "Establish governance cadence, reporting framework, stakeholder matrix, and detailed discovery schedule.",
                        "strategic_theme": "Delivery Governance",
                        "traces_to": ["FR-001"],
                        "dependencies": [],
                        "priority_components": {"user_business_value": 8, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-001",
                                "title": "Mobilisation & Project Governance Setup",
                                "description": "Conduct kickoff workshops, establish delivery cadence, finalize stakeholder interview schedule, and produce the Mobilisation Charter. Deliverable: Mobilisation Charter & Governance Framework.",
                                "strategic_theme": "Delivery Governance",
                                "traces_to": ["CON-001", "CON-002", "CON-003", "FR-001"],
                                "dependencies": [],
                                "timing": "Week 1",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Project kickoff completed with CIO and core IT leadership.",
                                    "Mobilisation Charter signed off detailing 12-week schedule and UK holiday allowances.",
                                    "Team allocations verified: Programme Delivery Manager (50%), Lead BA (100%), BA (100%), Solution Architect (50%).",
                                    "Discovery workshop calendar scheduled across service management stakeholders."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-002",
                "title": "Phase 2: Current State Assessment",
                "description": "Comprehensive assessment of current ITSM capabilities, existing tooling, integration landscape, process maturity, pain points, and operating costs.",
                "strategic_theme": "Service Maturity",
                "traces_to": ["FR-002"],
                "dependencies": ["EPIC-001"],
                "timing": "Weeks 2-4 (15 days)",
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                "job_size": 13,
                "features": [
                    {
                        "id": "FEAT-002",
                        "title": "Current State Capabilities & Tooling Assessment",
                        "description": "Document current ITSM tools, architectural integrations, operational metrics, and baseline TCO.",
                        "strategic_theme": "Service Maturity",
                        "traces_to": ["FR-002"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 13,
                        "stories": [
                            {
                                "id": "STORY-002",
                                "title": "Current State Assessment & Baseline Analysis",
                                "description": "Analyze ITIL process flows (Incident, Problem, Change, Request, CMDB), catalog existing toolsets, map API integrations, and calculate baseline cost of ownership. Deliverable: Current State Assessment.",
                                "strategic_theme": "Service Maturity",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-001"],
                                "timing": "Weeks 2-4",
                                "duration_days": 15,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 13,
                                "acceptance_criteria": [
                                    "Current-state ITIL process maturity documented across core service management disciplines.",
                                    "ITSM tooling and integration landscape mapped with data flow topologies.",
                                    "Baseline operational expenditure, licensing, and support costs calculated.",
                                    "Current State Assessment report delivered and signed off."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Business Analyst", "allocation_percent": 100},
                                    {"name": "Solution Architect", "allocation_percent": 50}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-003",
                "title": "Phase 3: Requirements Discovery",
                "description": "Stakeholder elicitation and synthesis of functional, non-functional, and integration requirements for future service management capabilities.",
                "strategic_theme": "Requirements Engineering",
                "traces_to": ["FR-003"],
                "dependencies": ["EPIC-001"],
                "timing": "Weeks 2-5 (20 days)",
                "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                "job_size": 20,
                "features": [
                    {
                        "id": "FEAT-003",
                        "title": "Requirements Discovery & Elicitation",
                        "description": "Conduct cross-functional discovery workshops to capture and prioritize user and technical requirements.",
                        "strategic_theme": "Requirements Engineering",
                        "traces_to": ["FR-003"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 20,
                        "stories": [
                            {
                                "id": "STORY-003",
                                "title": "Requirements Catalogue & Specification",
                                "description": "Facilitate stakeholder interviews, prioritize functional/non-functional needs via MoSCoW methodology, and compile the full requirements catalogue. Deliverable: Requirements Catalogue.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-001"],
                                "timing": "Weeks 2-5",
                                "duration_days": 20,
                                "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 20,
                                "acceptance_criteria": [
                                    "Over 100 functional and non-functional requirements elicited and categorized.",
                                    "Requirements categorized by business capability (Portal, Ticketing, CMDB, Automation, SLA, Analytics).",
                                    "MoSCoW prioritization agreed across business units and IT stakeholders.",
                                    "Deliverable: Requirements Catalogue published and validated."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-004",
                "title": "Phase 4: Future State Definition",
                "description": "Design the target architecture, integration blueprint, data governance model, and Target Operating Model (TOM).",
                "strategic_theme": "Target Architecture",
                "traces_to": ["FR-004", "GOAL-001"],
                "dependencies": ["EPIC-002", "EPIC-003"],
                "timing": "Weeks 6-7 (10 days)",
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-004",
                        "title": "Future State Architecture & Operating Model",
                        "description": "Formulate future-state architectural principles, integration patterns, and operational team structures.",
                        "strategic_theme": "Target Architecture",
                        "traces_to": ["FR-004"],
                        "dependencies": ["EPIC-002", "EPIC-003"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-004",
                                "title": "Architecture Assessment & Target Operating Model",
                                "description": "Produce target architecture blueprints, integration specifications (ITSM to DevOps, Cloud, HR, Observability), and role definitions for the future operating model. Deliverable: Architecture Assessment.",
                                "strategic_theme": "Target Architecture",
                                "traces_to": ["FR-004"],
                                "dependencies": ["STORY-002", "STORY-003"],
                                "timing": "Weeks 6-7",
                                "duration_days": 10,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                                "job_size": 8,
                                "acceptance_criteria": [
                                    "Target architectural topology and boundary diagrams drafted.",
                                    "Standard integration patterns established for enterprise tooling ecosystem.",
                                    "Target operating model (roles, governance committees, support tiers) defined.",
                                    "Deliverable: Architecture Assessment document completed."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-005",
                "title": "Phase 5: Market Assessment",
                "description": "Independent, neutral evaluation of enterprise ITSM market offerings (ServiceNow, Jira Service Management, Freshservice, BMC Helix) against discovery findings.",
                "strategic_theme": "Market Intelligence",
                "traces_to": ["FR-005", "GOAL-001"],
                "dependencies": ["EPIC-002", "EPIC-003"],
                "timing": "Weeks 6-7 (10 days)",
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-005",
                        "title": "ITSM Platform Market Assessment",
                        "description": "Evaluate vendor capabilities, roadmaps, partner ecosystems, and commercial licensing models.",
                        "strategic_theme": "Market Intelligence",
                        "traces_to": ["FR-005"],
                        "dependencies": ["EPIC-002", "EPIC-003"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-005",
                                "title": "Market Assessment & Vendor Landscape",
                                "description": "Review leading ITSM vendors (ServiceNow, Atlassian JSM, Freshworks Freshservice, BMC Helix) neutrally against client scope and requirements catalogue. Deliverable: Market Assessment.",
                                "strategic_theme": "Market Intelligence",
                                "traces_to": ["FR-005"],
                                "dependencies": ["STORY-002", "STORY-003"],
                                "timing": "Weeks 6-7",
                                "duration_days": 10,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 8,
                                "acceptance_criteria": [
                                    "Vendor profiles compiled covering ServiceNow, Jira Service Management, Freshservice, and BMC Helix.",
                                    "Feature coverage mapped against Requirements Catalogue categories.",
                                    "Licensing structures and implementation partner ecosystems analyzed.",
                                    "Deliverable: Market Assessment report signed off."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-006",
                "title": "Phase 6: Options Appraisal",
                "description": "Multi-criteria appraisal of future platform options, scoring suitability, architectural fit, operational viability, and strategic alignment.",
                "strategic_theme": "Decision Analysis",
                "traces_to": ["FR-006", "GOAL-001"],
                "dependencies": ["EPIC-004", "EPIC-005"],
                "timing": "Weeks 8-9 (10 days)",
                "priority_components": {"user_business_value": 20, "time_criticality": 8, "risk_reduction": 13},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-006",
                        "title": "Options Appraisal & Evaluation Matrix",
                        "description": "Construct weighted evaluation model and execute comparative appraisal of shortlisted options.",
                        "strategic_theme": "Decision Analysis",
                        "traces_to": ["FR-006"],
                        "dependencies": ["EPIC-004", "EPIC-005"],
                        "priority_components": {"user_business_value": 20, "time_criticality": 8, "risk_reduction": 13},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-006",
                                "title": "Options Appraisal & Comparative Analysis",
                                "description": "Execute weighted multi-criteria decision matrix across shortlisted options (Do Nothing / Retain Existing, Modernize Existing, Replatform to ServiceNow, Consolidate onto Atlassian JSM). Deliverable: Options Appraisal.",
                                "strategic_theme": "Decision Analysis",
                                "traces_to": ["FR-006"],
                                "dependencies": ["STORY-004", "STORY-005"],
                                "timing": "Weeks 8-9",
                                "duration_days": 10,
                                "priority_components": {"user_business_value": 20, "time_criticality": 8, "risk_reduction": 13},
                                "job_size": 8,
                                "acceptance_criteria": [
                                    "Weighted scoring framework agreed across functional, technical, risk, and strategic criteria.",
                                    "Comparative trade-off analysis completed for each candidate option.",
                                    "Strengths, weaknesses, opportunities, and risks documented for shortlisted options.",
                                    "Deliverable: Options Appraisal document finalized with stakeholder consensus."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Programme Delivery Manager", "allocation_percent": 25}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-007",
                "title": "Phase 7: Business Case Support",
                "description": "Financial modeling, Total Cost of Ownership (TCO) comparisons, return on investment (ROI) calculations, and business case evidence pack formulation.",
                "strategic_theme": "Commercial Viability",
                "traces_to": ["FR-007"],
                "dependencies": ["EPIC-006"],
                "timing": "Weeks 10-11 (10 days)",
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-007",
                        "title": "Business Case Modeling & Evidence Pack",
                        "description": "Quantify operational benefits, licensing costs, implementation expenditure, and risk-adjusted ROI.",
                        "strategic_theme": "Commercial Viability",
                        "traces_to": ["FR-007"],
                        "dependencies": ["EPIC-006"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-007",
                                "title": "Business Case Evidence Pack Formulation",
                                "description": "Construct 3-year and 5-year financial models comparing baseline run costs against proposed future options, including capital expenditure, licensing, operational savings, and risk reserves. Deliverable: Business Case Evidence Pack.",
                                "strategic_theme": "Commercial Viability",
                                "traces_to": ["FR-007"],
                                "dependencies": ["STORY-006"],
                                "timing": "Weeks 10-11",
                                "duration_days": 10,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                                "job_size": 8,
                                "acceptance_criteria": [
                                    "3-year and 5-year TCO models produced for shortlisted platform options.",
                                    "Quantified operational efficiency gains and license consolidation savings modeled.",
                                    "Transition budget, professional services estimates, and contingency reserves itemized.",
                                    "Deliverable: Business Case Evidence Pack completed and verified by finance stakeholders."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50},
                                    {"name": "Solution Architect", "allocation_percent": 25}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-008",
                "title": "Phase 8: Implementation Readiness Assessment",
                "description": "Evaluation of organizational maturity, technical readiness, data migration prerequisites, skills gaps, and delivery risks.",
                "strategic_theme": "Change Readiness",
                "traces_to": ["FR-008"],
                "dependencies": ["EPIC-006"],
                "timing": "Weeks 10-11 (10 days)",
                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 20},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-008",
                        "title": "Implementation Readiness & Risk Evaluation",
                        "description": "Assess skills, data hygiene, security requirements, and organizational change capability for transition.",
                        "strategic_theme": "Change Readiness",
                        "traces_to": ["FR-008"],
                        "dependencies": ["EPIC-006"],
                        "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 20},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-008",
                                "title": "Readiness Assessment & Transition Planning",
                                "description": "Assess CMDB data quality, Active Directory/IAM integration prerequisites, process standardization readiness, and organizational change capacity. Deliverable: Readiness Assessment.",
                                "strategic_theme": "Change Readiness",
                                "traces_to": ["FR-008"],
                                "dependencies": ["STORY-006"],
                                "timing": "Weeks 10-11",
                                "duration_days": 10,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 20},
                                "job_size": 8,
                                "acceptance_criteria": [
                                    "Data migration readiness and CMDB hygiene assessed.",
                                    "IT support organization change management readiness evaluated.",
                                    "Implementation gating prerequisites and governance checkpoints established.",
                                    "Deliverable: Readiness Assessment report delivered."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "id": "EPIC-009",
                "title": "Phase 9: Final Recommendation & Handover",
                "description": "Consolidation of strategic recommendations, delivery roadmap authoring, executive presentation, and formal engagement handover.",
                "strategic_theme": "Strategic Delivery",
                "traces_to": ["FR-009", "GOAL-001"],
                "dependencies": ["EPIC-007", "EPIC-008"],
                "timing": "Week 12 (5 days)",
                "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                "job_size": 5,
                "features": [
                    {
                        "id": "FEAT-009",
                        "title": "Final Recommendations & Implementation Roadmap",
                        "description": "Synthesize discovery findings into actionable executive recommendations, multi-phase implementation roadmap, and formal handover.",
                        "strategic_theme": "Strategic Delivery",
                        "traces_to": ["FR-009"],
                        "dependencies": ["EPIC-007", "EPIC-008"],
                        "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-009",
                                "title": "Implementation Roadmap & Final Recommendation Handover",
                                "description": "Produce phased transition roadmap (Phases 1-3 implementation timeline), deliver executive presentation of final platform and operating model recommendation, and execute formal artifact handover. Deliverables: Implementation Roadmap and Final Recommendation.",
                                "strategic_theme": "Strategic Delivery",
                                "traces_to": ["FR-009", "GOAL-001"],
                                "dependencies": ["STORY-007", "STORY-008"],
                                "timing": "Week 12",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Executive presentation delivered to CIO and governance board.",
                                    "Implementation Roadmap drafted with phased rollout timeline and procurement guidance.",
                                    "Final Recommendation document signed off.",
                                    "All 9 engagement deliverables formally handed over to client leadership."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Solution Architect", "allocation_percent": 25}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    save_msg = save_portfolio_backlog(backlog)
    print("save_portfolio_backlog output:", save_msg)
    if not save_msg.startswith("SUCCESS"):
        raise RuntimeError(f"save_portfolio_backlog failed: {save_msg}")

    # -------------------------------------------------------------------------
    # 3. Export Project Plan (MSPDI XML + PERT/CPM PNG)
    # -------------------------------------------------------------------------
    res = build_portfolio_backlog_project_plan(
        start_date="2026-11-23",
        target_duration_weeks=12,
    )
    print("Export result:", res)

    xml_path = paths.output_path("portfolio_backlog_project_plan.xml")
    pert_path = paths.output_path("portfolio_backlog_pert_cpm.png")
    parsed = parse_mspdi_project(xml_path)

    print("\nVerification Summary:")
    print(f"Title: {parsed['title']}")
    print(f"Start Date: {parsed['start_date']}")
    print(f"Finish Date: {parsed['finish_date']}")
    print(f"Total Tasks: {len(parsed['tasks'])}")
    print(f"Total Resources: {len(parsed['resources'])}")
    print(f"Total Assignments: {len(parsed['assignments'])}")
    print(f"Total Projected Cost: ${parsed['total_cost']:,.2f}")
    print(f"MSPDI XML Path: {xml_path}")
    print(f"PERT/CPM PNG Path: {pert_path}")

    # Copy artifacts to samples/Neurosan/ProcessEngineering/output/ as well
    neurosan_out = os.path.abspath("samples/Neurosan/ProcessEngineering/output")
    if os.path.isdir(neurosan_out):
        for fname in [
            "requirements_summary.json",
            "portfolio_backlog.json",
            "portfolio_backlog.xlsx",
            "portfolio_backlog_project_plan.xml",
            "portfolio_backlog_pert_cpm.png"
        ]:
            src = paths.output_path(fname)
            if os.path.exists(src):
                dst = os.path.join(neurosan_out, fname)
                shutil.copy2(src, dst)
                print(f"Copied {fname} to Neurosan output: {dst}")


if __name__ == "__main__":
    generate_artifacts()
