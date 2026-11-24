"""Generates 100% compliant ITSM Discovery & Options Assessment engagement artifacts
with a REALISTIC, PROFESSIONAL, MULTI-TIER WORK BREAKDOWN STRUCTURE (WBS):
- 9 Epics (all 9 required phases)
- 20 distinct Features (2-3 per Epic, covering functional workstreams)
- 41 concrete User Stories / Tasks with granular consulting activities
- Exact 12-week timescale (60 working days = 480 working hours, starting 2026-11-23, finishing 2027-02-12)
- Concurrent discovery streams with non-zero float on Phase 2
- Activity-based resource allocations from the mandated 4-role team
- All 9 required deliverables explicitly produced

Artifacts generated:
1. output/requirements_summary.json
2. output/portfolio_backlog.json (and portfolio_backlog.xlsx)
3. output/portfolio_backlog_project_plan.xml
4. output/portfolio_backlog_pert_cpm.png
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
            "effort_mix": 0.167,
            "daily_rate": 1300.0,
            "basis": "Market benchmark for senior IT programme delivery leadership and governance."
        },
        {
            "person": "TBD",
            "role": "Lead Business Analyst",
            "effort_mix": 0.333,
            "daily_rate": 1100.0,
            "basis": "Market benchmark for lead business analysis and process engineering."
        },
        {
            "person": "TBD",
            "role": "Business Analyst",
            "effort_mix": 0.333,
            "daily_rate": 1000.0,
            "basis": "Market benchmark for business analysis, requirements discovery, and cataloging."
        },
        {
            "person": "TBD",
            "role": "Solution Architect",
            "effort_mix": 0.167,
            "daily_rate": 1500.0,
            "basis": "Market benchmark for enterprise & ITSM solution architecture and integrations."
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
                "timing": "Week 1",
                "priority_components": {"user_business_value": 8, "time_criticality": 13, "risk_reduction": 8},
                "job_size": 5,
                "features": [
                    {
                        "id": "FEAT-001",
                        "title": "Engagement Onboarding & Delivery Governance",
                        "description": "Establish governance cadence, steering group terms of reference, and reporting frameworks.",
                        "strategic_theme": "Delivery Governance",
                        "traces_to": ["FR-001"],
                        "dependencies": [],
                        "priority_components": {"user_business_value": 8, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-001",
                                "title": "Stakeholder Identification & Engagement Governance Charter",
                                "description": "Identify primary and secondary stakeholder groups across service owners, establish steering committee cadence, and publish governance charter.",
                                "strategic_theme": "Delivery Governance",
                                "traces_to": ["CON-001", "FR-001"],
                                "dependencies": [],
                                "timing": "Week 1",
                                "duration_days": 2,
                                "priority_components": {"user_business_value": 8, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 2,
                                "acceptance_criteria": [
                                    "Steering group terms of reference and escalation mechanisms agreed with sponsor.",
                                    "Stakeholder engagement matrix published covering core IT and business units.",
                                    "Kickoff deck and project overview shared with executive leadership."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-002",
                                "title": "Discovery Tooling & Architecture Repository Access Provisioning",
                                "description": "Secure administrative and read access to current ITSM toolsets, configuration repositories, architecture diagrams, and financial ledgers.",
                                "strategic_theme": "Delivery Governance",
                                "traces_to": ["CON-002", "FR-001"],
                                "dependencies": ["STORY-001"],
                                "timing": "Week 1",
                                "duration_days": 2,
                                "priority_components": {"user_business_value": 5, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 2,
                                "acceptance_criteria": [
                                    "Read-only access provisioned for consulting team to existing service desk platforms.",
                                    "Architecture documentation repository established with baseline artifact templates.",
                                    "Data sharing and NDA compliance verified for external review."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 50},
                                    {"name": "Solution Architect", "allocation_percent": 50}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-002",
                        "title": "Discovery Planning & Workshop Logistics",
                        "description": "Formulate detailed workshop schedules, interview guides, and stakeholder engagement timetables.",
                        "strategic_theme": "Delivery Governance",
                        "traces_to": ["FR-001", "CON-003"],
                        "dependencies": [],
                        "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-003",
                                "title": "Discovery Interview Timetable & Stakeholder Workshop Scheduling",
                                "description": "Coordinate multi-department workshop calendar across incident, request, change, asset, and architecture leads.",
                                "strategic_theme": "Delivery Governance",
                                "traces_to": ["CON-003", "FR-001"],
                                "dependencies": ["STORY-001"],
                                "timing": "Week 1",
                                "duration_days": 2,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 2,
                                "acceptance_criteria": [
                                    "20+ discovery interview sessions booked with confirmed attendees.",
                                    "Standardized interview question templates aligned to ITIL v4 practices distributed.",
                                    "Workshop logistics and digital collaboration canvases configured."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-004",
                                "title": "Mobilisation Charter & Governance Kickoff Signoff",
                                "description": "Consolidate mobilisation outputs into formal Mobilisation Charter and obtain steering group signoff.",
                                "strategic_theme": "Delivery Governance",
                                "traces_to": ["FR-001"],
                                "dependencies": ["STORY-002", "STORY-003"],
                                "timing": "Week 1",
                                "duration_days": 1,
                                "priority_components": {"user_business_value": 8, "time_criticality": 13, "risk_reduction": 5},
                                "job_size": 1,
                                "acceptance_criteria": [
                                    "Formal project kickoff meeting conducted with CIO and steering committee.",
                                    "Mobilisation Charter signed off detailing 12-week roadmap and milestone gates.",
                                    "Deliverable: Mobilisation Charter & Governance Framework approved."
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
                "strategic_theme": "Current State Assessment",
                "traces_to": ["FR-002", "CON-001"],
                "dependencies": ["EPIC-001"],
                "timing": "Weeks 2-4",
                "duration_days": 15,
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                "job_size": 13,
                "features": [
                    {
                        "id": "FEAT-003",
                        "title": "ITSM Process Maturity & Workflow Assessment",
                        "description": "Evaluate maturity, bottlenecks, and manual overhead across core ITIL processes.",
                        "strategic_theme": "Current State Assessment",
                        "traces_to": ["FR-002"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-005",
                                "title": "Core Incident, Request & Service Desk Process Discovery",
                                "description": "Review ticket volume trends, escalation pathways, first-contact resolution rates, and user satisfaction across the service desk.",
                                "strategic_theme": "Current State Assessment",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-004"],
                                "timing": "Weeks 2-3",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Incident and service request lifecycle flowcharts documented.",
                                    "Pain point register compiling stakeholder feedback on ticket resolution bottlenecks.",
                                    "SLA performance baseline and breach root-cause analysis completed."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-006",
                                "title": "Change, Problem & Release Management Governance Review",
                                "description": "Evaluate CAB approval processes, emergency change frequency, problem root-cause investigation practices, and release coordination.",
                                "strategic_theme": "Current State Assessment",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-005"],
                                "timing": "Weeks 3-4",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Change approval lead times and emergency change ratio calculated.",
                                    "Problem management backlog and major incident post-mortem governance reviewed.",
                                    "Process maturity scored against ITIL v4 guidance for change and release enablement."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-004",
                        "title": "Tooling, Integrations & Infrastructure Baseline",
                        "description": "Audit current technical tooling footprint, custom code complexity, and integration interfaces.",
                        "strategic_theme": "Current State Assessment",
                        "traces_to": ["FR-002"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-007",
                                "title": "CMDB Coverage, Discovery Accuracy & Asset Audit",
                                "description": "Audit CMDB data accuracy, automated discovery tool coverage, relationship mapping, and hardware/software asset lifecycle tracking.",
                                "strategic_theme": "Current State Assessment",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-004"],
                                "timing": "Weeks 2-3",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "CMDB completeness score assessed across servers, cloud resources, and network gear.",
                                    "Asset discovery gap analysis completed against Active Directory and network subnets.",
                                    "Configuration item (CI) health and relationship mapping issues documented."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-008",
                                "title": "ITSM Platform Tooling & Custom Script Architecture Review",
                                "description": "Inventory existing tool versions, custom code modules, UI policies, business rules, and technical debt that obstruct upgrades.",
                                "strategic_theme": "Current State Assessment",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-007"],
                                "timing": "Weeks 3-4",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Catalog of custom scripts, UI actions, and third-party plugins compiled.",
                                    "Technical debt assessment identifying upgrade blockers and security vulnerabilities.",
                                    "Hosting infrastructure (cloud/on-prem) resilience and availability analyzed."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-005",
                        "title": "Integration Mapping & Current State Assessment Deliverable",
                        "description": "Map system interfaces, baseline operational costs, and publish the formal Current State Assessment.",
                        "strategic_theme": "Current State Assessment",
                        "traces_to": ["FR-002"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-009",
                                "title": "Integration Landscape & Data Flow Interface Mapping",
                                "description": "Map all active integration interfaces connecting ITSM to APM/monitoring, DevOps tools (Jira, GitHub), ERP/HR, and IAM systems.",
                                "strategic_theme": "Current State Assessment",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-004"],
                                "timing": "Weeks 2-3",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Current-state system context diagram illustrating data flows and protocols.",
                                    "Integration catalog listing endpoints, authentication methods, and failure points.",
                                    "Bi-directional data sync friction and manual swivel-chair activities documented."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-010",
                                "title": "Operational Spend, Licensing & Support Cost Ledger Analysis",
                                "description": "Extract historical operational expenditure, software license fees, cloud hosting, contractor support, and administration costs.",
                                "strategic_theme": "Current State Assessment",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-009"],
                                "timing": "Weeks 3-4",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 8, "time_criticality": 5, "risk_reduction": 5},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Baseline annual run-rate compiled across platform licensing, hosting, and tier-3 support.",
                                    "True cost per ticket and cost per fulfiller calculated.",
                                    "Contract renewal dates and notice period commitments itemized."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-011",
                                "title": "Current State Assessment Deliverable Synthesis & Signoff",
                                "description": "Synthesize all process maturity, technical architecture, and cost findings into the formal Current State Assessment deliverable.",
                                "strategic_theme": "Current State Assessment",
                                "traces_to": ["FR-002"],
                                "dependencies": ["STORY-006", "STORY-008", "STORY-010"],
                                "timing": "Week 4",
                                "duration_days": 3,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "Current State Assessment document authored covering processes, tooling, integrations, and costs.",
                                    "Executive summary highlighting key pain points and strategic risks presented to sponsor.",
                                    "Deliverable: Current State Assessment report formally signed off."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Programme Delivery Manager", "allocation_percent": 25}
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
                "traces_to": ["FR-003", "CON-001"],
                "dependencies": ["EPIC-001"],
                "timing": "Weeks 2-5",
                "duration_days": 20,
                "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                "job_size": 20,
                "features": [
                    {
                        "id": "FEAT-006",
                        "title": "Functional Requirements Elicitation",
                        "description": "Capture user stories and business requirements across self-service, operations, and ITOM.",
                        "strategic_theme": "Requirements Engineering",
                        "traces_to": ["FR-003"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 13,
                        "stories": [
                            {
                                "id": "STORY-012",
                                "title": "Service Portal, Catalog & Omnichannel Self-Service Requirements",
                                "description": "Capture requirements for modern self-service portal, service request catalog, automated fulfillment, and virtual agent/chat.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-004"],
                                "timing": "Weeks 2-3",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Portal user journey maps and catalog request taxonomy defined.",
                                    "Search experience, knowledge management, and AI deflection requirements detailed.",
                                    "Mobile responsiveness and accessibility (WCAG 2.1 AA) specifications agreed."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-013",
                                "title": "Service Operations, SLA & Workflow Automation Requirements",
                                "description": "Detail requirements for intelligent incident triage, dynamic SLA matrices, change approval workflows, and major incident handling.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-012"],
                                "timing": "Weeks 3-4",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Automated routing and skill-based assignment rules defined.",
                                    "Multi-tier SLA and OLA tracking requirements with automated escalations formulated.",
                                    "Standard, normal, and emergency change workflow automation specifications documented."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-007",
                        "title": "Non-Functional & Enterprise Platform Requirements",
                        "description": "Elicit non-functional requirements for security, compliance, analytics, and infrastructure.",
                        "strategic_theme": "Requirements Engineering",
                        "traces_to": ["FR-003"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-014",
                                "title": "ITOM, Event Management & Automated Discovery Requirements",
                                "description": "Formulate technical requirements for hybrid cloud discovery, automated CI relationship mapping, and AIOps event correlation.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-004"],
                                "timing": "Weeks 2-3",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Automated discovery requirements for on-prem VMs, AWS/Azure cloud resources, and network topology.",
                                    "Service mapping requirements connecting business applications to underlying CIs.",
                                    "Alert noise reduction, de-duplication, and monitoring tool integration specifications."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-015",
                                "title": "Security, UK Data Residency & Regulatory Compliance Requirements",
                                "description": "Define enterprise security requirements covering UK data sovereignty, role-based access control (RBAC), and encryption.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-014"],
                                "timing": "Weeks 3-4",
                                "duration_days": 6,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "UK data hosting and GDPR compliance constraints documented.",
                                    "SSO/MFA authentication standards (SAML 2.0 / OIDC) and granular RBAC specifications agreed.",
                                    "Audit logging, SIEM integration, and data retention rules defined."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-008",
                        "title": "Requirements Prioritization & Catalogue Publication",
                        "description": "Facilitate MoSCoW prioritization and publish the comprehensive Requirements Catalogue deliverable.",
                        "strategic_theme": "Requirements Engineering",
                        "traces_to": ["FR-003"],
                        "dependencies": ["EPIC-001"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-016",
                                "title": "Reporting, Performance Analytics & Executive KPI Requirements",
                                "description": "Elicit operational and strategic reporting needs, executive dashboards, CSAT feedback surveys, and performance analytics.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-012", "STORY-014"],
                                "timing": "Weeks 3-4",
                                "duration_days": 4,
                                "priority_components": {"user_business_value": 8, "time_criticality": 5, "risk_reduction": 5},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "Executive KPI dictionary defined (MTTR, First Contact Resolution, SLA achievement, CSAT).",
                                    "Operational dashboard mockups for service desk managers and team leads reviewed.",
                                    "Data export and automated scheduling requirements documented."
                                ],
                                "resources": [
                                    {"name": "Business Analyst", "allocation_percent": 100},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-017",
                                "title": "Stakeholder MoSCoW Prioritization & Consensus Workshops",
                                "description": "Facilitate consensus workshops with business unit leads and IT steering group to prioritize requirements via MoSCoW methodology.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-013", "STORY-015", "STORY-016"],
                                "timing": "Weeks 4-5",
                                "duration_days": 4,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "Over 100 requirements categorized into Must-Have, Should-Have, Could-Have, and Won't-Have.",
                                    "Cross-departmental prioritization conflicts resolved with signed stakeholder consensus.",
                                    "Prioritization audit log and rationale documented."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-018",
                                "title": "Requirements Catalogue Deliverable Authoring & Traceability Baseline",
                                "description": "Finalize and publish the formal Requirements Catalogue deliverable with complete traceability IDs and verification criteria.",
                                "strategic_theme": "Requirements Engineering",
                                "traces_to": ["FR-003"],
                                "dependencies": ["STORY-017"],
                                "timing": "Weeks 4-5",
                                "duration_days": 4,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "Structured Requirements Catalogue delivered covering functional, technical, and non-functional specifications.",
                                    "Traceability matrix linking all requirements to business objectives established.",
                                    "Deliverable: Requirements Catalogue signed off by business and technical leads."
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
                "description": "Define target ITSM architecture, integration topology, data governance principles, and Target Operating Model (TOM) alignment.",
                "strategic_theme": "Target Architecture",
                "traces_to": ["FR-004", "GOAL-001"],
                "dependencies": ["EPIC-002", "EPIC-003"],
                "timing": "Weeks 6-7",
                "duration_days": 10,
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-009",
                        "title": "Target Solution Architecture & Conceptual Topology",
                        "description": "Design target cloud platform architecture, security boundary, and data exchange topologies.",
                        "strategic_theme": "Target Architecture",
                        "traces_to": ["FR-004"],
                        "dependencies": ["EPIC-002", "EPIC-003"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-019",
                                "title": "Target Solution Architecture & Conceptual Topology Blueprints",
                                "description": "Draft target state architecture blueprints, cloud hosting topologies, high availability zones, and identity boundaries.",
                                "strategic_theme": "Target Architecture",
                                "traces_to": ["FR-004"],
                                "dependencies": ["STORY-011", "STORY-018"],
                                "timing": "Week 6",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 13},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Target architectural topology diagram produced with clear system boundaries.",
                                    "Multi-instance vs single-instance tenancy trade-offs documented.",
                                    "Disaster recovery, backup, and RPO/RTO targets specified."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-020",
                                "title": "Standard Integration Patterns & API Data Exchange Architecture",
                                "description": "Define enterprise integration patterns connecting target ITSM platform to CI/CD pipelines, ERP, observability, and HR systems.",
                                "strategic_theme": "Target Architecture",
                                "traces_to": ["FR-004"],
                                "dependencies": ["STORY-011", "STORY-018"],
                                "timing": "Week 6",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Standard integration design patterns formulated (REST APIs, webhooks, message queues).",
                                    "Data synchronization schemas and field mapping guidelines documented.",
                                    "Security and rate limiting architecture for public/private endpoints agreed."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-010",
                        "title": "Target Operating Model (TOM) & Service Governance",
                        "description": "Design future organizational support tiers, governance committees, and publish the Architecture Assessment.",
                        "strategic_theme": "Target Architecture",
                        "traces_to": ["FR-004"],
                        "dependencies": ["EPIC-002", "EPIC-003"],
                        "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-021",
                                "title": "Future Target Operating Model (TOM) & Service Governance Roles",
                                "description": "Formulate future operating model: tier-1 triage, tier-2 technical specialists, tier-3 vendor support, and continuous improvement governance.",
                                "strategic_theme": "Target Architecture",
                                "traces_to": ["FR-004"],
                                "dependencies": ["STORY-011", "STORY-018"],
                                "timing": "Week 6",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Target operating model organization chart and support tier interactions defined.",
                                    "RACI matrix created across service operations, incident management, and platform administration.",
                                    "Governance committee structure (Design Authority, CAB, Service Review) documented."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Programme Delivery Manager", "allocation_percent": 25}
                                ]
                            },
                            {
                                "id": "STORY-022",
                                "title": "Architecture Assessment Deliverable Synthesis & Validation",
                                "description": "Compile future-state blueprints, integration frameworks, and TOM into the formal Architecture Assessment deliverable.",
                                "strategic_theme": "Target Architecture",
                                "traces_to": ["FR-004"],
                                "dependencies": ["STORY-019", "STORY-020", "STORY-021"],
                                "timing": "Weeks 6-7",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Architecture Assessment document authored incorporating technical blueprints and TOM.",
                                    "Technical review conducted with enterprise architecture board.",
                                    "Deliverable: Architecture Assessment report signed off by Architecture Owner."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 100}
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
                "timing": "Weeks 6-7",
                "duration_days": 10,
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-011",
                        "title": "Vendor Capability & Ecosystem Evaluation",
                        "description": "Evaluate leading platforms on out-of-the-box functionality, roadmap, and implementation ecosystems.",
                        "strategic_theme": "Market Intelligence",
                        "traces_to": ["FR-005"],
                        "dependencies": ["EPIC-002", "EPIC-003"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-023",
                                "title": "Market Scan & Vendor Capability Matrix (ServiceNow, JSM, Freshservice, BMC)",
                                "description": "Conduct deep-dive vendor capability assessment evaluating ITIL process coverage, usability, AIOps, and mobile experiences.",
                                "strategic_theme": "Market Intelligence",
                                "traces_to": ["FR-005"],
                                "dependencies": ["STORY-011", "STORY-018"],
                                "timing": "Week 6",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Vendor profiles compiled covering ServiceNow, Jira Service Management, Freshservice, and BMC Helix.",
                                    "Capability benchmark matrix scoring core service management disciplines.",
                                    "Vendor product vision, release frequency, and innovation roadmaps evaluated."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-024",
                                "title": "Licensing Models, Commercial Structures & Partner Ecosystem Review",
                                "description": "Review vendor licensing models (per-user, per-asset, enterprise tiers), cloud hosting costs, and certified implementation partners in the UK.",
                                "strategic_theme": "Market Intelligence",
                                "traces_to": ["FR-005"],
                                "dependencies": ["STORY-023"],
                                "timing": "Weeks 6-7",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Licensing structures (fulfiller vs requester vs business user) compared across vendors.",
                                    "UK implementation partner landscape, day rates, and certified practitioner availability surveyed.",
                                    "Standard SLA, support tiers, and commercial lock-in terms analyzed."
                                ],
                                "resources": [
                                    {"name": "Business Analyst", "allocation_percent": 100},
                                    {"name": "Programme Delivery Manager", "allocation_percent": 25}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-012",
                        "title": "Requirements Coverage Scoring & Market Assessment Reporting",
                        "description": "Score platform coverage against the Requirements Catalogue and publish the Market Assessment deliverable.",
                        "strategic_theme": "Market Intelligence",
                        "traces_to": ["FR-005"],
                        "dependencies": ["EPIC-002", "EPIC-003"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-025",
                                "title": "Out-of-the-Box Requirements Fit Gap Scoring across Platforms",
                                "description": "Map the 100+ items from the Requirements Catalogue against each platform to determine out-of-the-box fit vs custom build requirements.",
                                "strategic_theme": "Market Intelligence",
                                "traces_to": ["FR-005"],
                                "dependencies": ["STORY-011", "STORY-018"],
                                "timing": "Week 6",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Fit gap scorecard completed for all 4 vendor platforms against Requirements Catalogue.",
                                    "Percentage of requirements met Out-of-the-Box, via Configuration, or via Customization calculated.",
                                    "Customization risk hotspots identified for each platform."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 100}
                                ]
                            },
                            {
                                "id": "STORY-026",
                                "title": "Market Assessment Deliverable Formulation & SWOT Reporting",
                                "description": "Author the Market Assessment deliverable synthesizing vendor capabilities, fit gap scoring, and comparative SWOT summaries.",
                                "strategic_theme": "Market Intelligence",
                                "traces_to": ["FR-005"],
                                "dependencies": ["STORY-023", "STORY-025"],
                                "timing": "Weeks 6-7",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Comprehensive Market Assessment document compiled with comparative analysis.",
                                    "SWOT analysis produced for ServiceNow, JSM, Freshservice, and BMC Helix.",
                                    "Deliverable: Market Assessment report delivered and reviewed with project sponsor."
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
                "strategic_theme": "Options Appraisal",
                "traces_to": ["FR-006", "GOAL-001"],
                "dependencies": ["EPIC-004", "EPIC-005"],
                "timing": "Weeks 8-9",
                "duration_days": 10,
                "priority_components": {"user_business_value": 20, "time_criticality": 8, "risk_reduction": 13},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-013",
                        "title": "Strategic Options Architecture & Scope Formulation",
                        "description": "Define candidate options spanning retain/optimize, cloud consolidation, and full enterprise re-platforming.",
                        "strategic_theme": "Options Appraisal",
                        "traces_to": ["FR-006"],
                        "dependencies": ["EPIC-004", "EPIC-005"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-027",
                                "title": "Candidate Option Architecture & Scope Formulation (4 Viable Options)",
                                "description": "Formulate 4 concrete strategic options: Option 1: Retain & Remediate Existing; Option 2: Consolidate on Atlassian JSM; Option 3: Enterprise ServiceNow; Option 4: Freshservice Cloud.",
                                "strategic_theme": "Options Appraisal",
                                "traces_to": ["FR-006"],
                                "dependencies": ["STORY-022", "STORY-026"],
                                "timing": "Week 8",
                                "duration_days": 3,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "Detailed architectural and operating scope defined for all 4 candidate options.",
                                    "Target deployment architecture and migration complexity characterized for each option.",
                                    "Initial viability gating verified with IT leadership."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 100}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-014",
                        "title": "Multi-Criteria Scoring & Trade-Off Analysis",
                        "description": "Execute weighted decision matrix scoring, risk sensitivity analysis, and publish the Options Appraisal deliverable.",
                        "strategic_theme": "Options Appraisal",
                        "traces_to": ["FR-006"],
                        "dependencies": ["EPIC-004", "EPIC-005"],
                        "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 13},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-028",
                                "title": "Weighted Multi-Criteria Decision Matrix Scoring Workshops",
                                "description": "Facilitate stakeholder scoring workshops across 4 weighted dimensions: Functional Fit (30%), Architecture/Security (25%), Delivery Risk (20%), Strategic Alignment (25%).",
                                "strategic_theme": "Options Appraisal",
                                "traces_to": ["FR-006"],
                                "dependencies": ["STORY-027"],
                                "timing": "Week 8",
                                "duration_days": 2,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 2,
                                "acceptance_criteria": [
                                    "Weighted scoring framework approved by steering committee.",
                                    "Consensus scores captured for each option across all criteria.",
                                    "Score audit trail with stakeholder commentary documented."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Programme Delivery Manager", "allocation_percent": 25}
                                ]
                            },
                            {
                                "id": "STORY-029",
                                "title": "Trade-Off, Sensitivity & Migration Risk Evaluation",
                                "description": "Perform sensitivity analysis on key scoring variables, evaluate lock-in risks, delivery disruption, and organizational feasibility.",
                                "strategic_theme": "Options Appraisal",
                                "traces_to": ["FR-006"],
                                "dependencies": ["STORY-028"],
                                "timing": "Weeks 8-9",
                                "duration_days": 2,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 2,
                                "acceptance_criteria": [
                                    "Sensitivity testing showing score stability under varying criteria weights.",
                                    "Risk profile highlighting key execution vulnerabilities for each option.",
                                    "Vendor lock-in and long-term exit viability assessed."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-030",
                                "title": "Options Appraisal Deliverable Consolidation & Executive Ranking",
                                "description": "Author the formal Options Appraisal deliverable consolidating multi-criteria scoring, trade-off analysis, and ranked option recommendations.",
                                "strategic_theme": "Options Appraisal",
                                "traces_to": ["FR-006"],
                                "dependencies": ["STORY-029"],
                                "timing": "Weeks 8-9",
                                "duration_days": 3,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "Options Appraisal document finalized with ranked strategic options.",
                                    "Executive summary articulating clear rationale for preferred and secondary options.",
                                    "Deliverable: Options Appraisal formally signed off by project sponsor."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Solution Architect", "allocation_percent": 50},
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
                "strategic_theme": "Business Case Support",
                "traces_to": ["FR-007", "CON-001"],
                "dependencies": ["EPIC-006"],
                "timing": "Weeks 10-11",
                "duration_days": 10,
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 13},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-015",
                        "title": "Financial Modeling & Total Cost of Ownership (TCO)",
                        "description": "Construct 5-year TCO financial models and quantify return on investment across options.",
                        "strategic_theme": "Business Case Support",
                        "traces_to": ["FR-007"],
                        "dependencies": ["EPIC-006"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-031",
                                "title": "5-Year Total Cost of Ownership (TCO) Comparative Financial Modeling",
                                "description": "Develop 5-year financial models comparing capital expenditure, subscription licensing, cloud hosting, implementation, and run costs across options.",
                                "strategic_theme": "Business Case Support",
                                "traces_to": ["FR-007"],
                                "dependencies": ["STORY-030"],
                                "timing": "Week 10",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "5-year detailed cost projection model completed in Excel across all candidate options.",
                                    "License cost, maintenance, infrastructure, and internal support overhead itemized.",
                                    "Year-on-year cash flow projections and NPV calculations completed."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-032",
                                "title": "Operational Efficiency, Deflection & License Consolidation ROI Analysis",
                                "description": "Quantify operational benefits: ticket deflection via self-service, reduction in MTTR, automated provisioning savings, and retired tool consolidation.",
                                "strategic_theme": "Business Case Support",
                                "traces_to": ["FR-007"],
                                "dependencies": ["STORY-031"],
                                "timing": "Weeks 10-11",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Deflection and automation efficiency savings quantified with financial finance models.",
                                    "Cost avoidance from retiring legacy tools and licenses calculated.",
                                    "Payback period and ROI projections agreed with finance team."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-016",
                        "title": "Implementation Sizing & Evidence Pack Documentation",
                        "description": "Size implementation services, establish risk contingency, and publish the Business Case Evidence Pack.",
                        "strategic_theme": "Business Case Support",
                        "traces_to": ["FR-007"],
                        "dependencies": ["EPIC-006"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-033",
                                "title": "Implementation Professional Services Sizing & Contingency Reserves",
                                "description": "Estimate systems integrator (SI) implementation fees, internal resource backfill, data migration costs, change management, and contingency.",
                                "strategic_theme": "Business Case Support",
                                "traces_to": ["FR-007"],
                                "dependencies": ["STORY-030"],
                                "timing": "Week 10",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Professional services effort and day-rate estimates modeled for migration.",
                                    "Internal project team backfill and operational transition budget sized.",
                                    "Risk contingency reserve (15-20%) calculated and justified."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Solution Architect", "allocation_percent": 25}
                                ]
                            },
                            {
                                "id": "STORY-034",
                                "title": "Business Case Evidence Pack Deliverable Compilation & Verification",
                                "description": "Author and finalize the Business Case Evidence Pack deliverable synthesizing financial models, ROI calculations, and commercial inputs.",
                                "strategic_theme": "Business Case Support",
                                "traces_to": ["FR-007"],
                                "dependencies": ["STORY-031", "STORY-033"],
                                "timing": "Weeks 10-11",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Comprehensive Business Case Evidence Pack document finalized.",
                                    "Executive financial summary prepared for CIO and CFO review.",
                                    "Deliverable: Business Case Evidence Pack signed off by finance stakeholders."
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
                "id": "EPIC-008",
                "title": "Phase 8: Implementation Readiness Assessment",
                "description": "Evaluation of organizational maturity, technical readiness, data migration prerequisites, skills gaps, and delivery risks.",
                "strategic_theme": "Implementation Readiness Assessment",
                "traces_to": ["FR-008", "CON-001"],
                "dependencies": ["EPIC-006"],
                "timing": "Weeks 10-11",
                "duration_days": 10,
                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 20},
                "job_size": 8,
                "features": [
                    {
                        "id": "FEAT-017",
                        "title": "Technical & Data Migration Readiness",
                        "description": "Assess CMDB data quality, Active Directory/IAM readiness, and migration prerequisites.",
                        "strategic_theme": "Implementation Readiness Assessment",
                        "traces_to": ["FR-008"],
                        "dependencies": ["EPIC-006"],
                        "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 13},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-035",
                                "title": "CMDB Data Cleanliness & Integration Prerequisite Audit",
                                "description": "Audit readiness of configuration item data for migration, identify duplicate records, orphan CIs, and integration API pre-flight requirements.",
                                "strategic_theme": "Implementation Readiness Assessment",
                                "traces_to": ["FR-008"],
                                "dependencies": ["STORY-030"],
                                "timing": "Week 10",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 13},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "CMDB data remediation backlog and cleanup requirements cataloged.",
                                    "Historical ticket archiving and migration scope boundaries defined.",
                                    "API gateway and firewall connectivity prerequisites mapped."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-036",
                                "title": "Security, Architecture Review Board & Identity Federation Prerequisites",
                                "description": "Review IAM/SSO prerequisite readiness, user provisioning mechanisms (SCIM), and architecture review board governance gates.",
                                "strategic_theme": "Implementation Readiness Assessment",
                                "traces_to": ["FR-008"],
                                "dependencies": ["STORY-035"],
                                "timing": "Weeks 10-11",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Security review gating requirements established with Information Security team.",
                                    "Enterprise identity federation and automated user provisioning readiness confirmed.",
                                    "Architecture Review Board submission requirements compiled."
                                ],
                                "resources": [
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-018",
                        "title": "Organizational Change Readiness & Governance Checkpoints",
                        "description": "Assess skills gaps, support staff training needs, and define implementation gating prerequisites.",
                        "strategic_theme": "Implementation Readiness Assessment",
                        "traces_to": ["FR-008"],
                        "dependencies": ["EPIC-006"],
                        "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 13},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-037",
                                "title": "IT Support Organization Skills Gap & Change Management Readiness",
                                "description": "Assess service desk and engineering team capabilities against target platform requirements, identifying training and change needs.",
                                "strategic_theme": "Implementation Readiness Assessment",
                                "traces_to": ["FR-008"],
                                "dependencies": ["STORY-030"],
                                "timing": "Week 10",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 8, "time_criticality": 8, "risk_reduction": 8},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Skills gap matrix across platform administration and developer skillsets completed.",
                                    "Change management impact assessment across service desk staff conducted.",
                                    "Training curriculum and certification roadmap outlined for target platform."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 50},
                                    {"name": "Business Analyst", "allocation_percent": 50}
                                ]
                            },
                            {
                                "id": "STORY-038",
                                "title": "Readiness Assessment Deliverable Consolidation & Gating Checkpoints",
                                "description": "Author the Readiness Assessment deliverable outlining overall transition feasibility, critical delivery risks, and go/no-go gates.",
                                "strategic_theme": "Implementation Readiness Assessment",
                                "traces_to": ["FR-008"],
                                "dependencies": ["STORY-035", "STORY-037"],
                                "timing": "Weeks 10-11",
                                "duration_days": 5,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 13},
                                "job_size": 5,
                                "acceptance_criteria": [
                                    "Readiness Assessment report completed covering technical, organizational, and data maturity.",
                                    "Implementation risk register with mitigation actions drafted.",
                                    "Deliverable: Readiness Assessment report signed off by steering committee."
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
                "id": "EPIC-009",
                "title": "Phase 9: Final Recommendation & Handover",
                "description": "Consolidation of strategic recommendations, delivery roadmap authoring, executive presentation, and formal engagement handover.",
                "strategic_theme": "Final Recommendation & Handover",
                "traces_to": ["FR-009", "GOAL-001"],
                "dependencies": ["EPIC-007", "EPIC-008"],
                "timing": "Week 12",
                "duration_days": 5,
                "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                "job_size": 5,
                "features": [
                    {
                        "id": "FEAT-019",
                        "title": "Implementation Roadmap Authoring",
                        "description": "Formulate phased implementation timeline, procurement guidance, and work packages.",
                        "strategic_theme": "Final Recommendation & Handover",
                        "traces_to": ["FR-009"],
                        "dependencies": ["EPIC-007", "EPIC-008"],
                        "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-039",
                                "title": "Multi-Phase Implementation Roadmap Formulation (12-18 Month Phasing)",
                                "description": "Develop actionable, phased implementation roadmap covering procurement, Foundation MVP, core ITIL rollout, integrations, and advanced AIOps.",
                                "strategic_theme": "Final Recommendation & Handover",
                                "traces_to": ["FR-009"],
                                "dependencies": ["STORY-034", "STORY-038"],
                                "timing": "Week 12",
                                "duration_days": 3,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "12-to-18 month phased roadmap with milestone gates, work packages, and dependency tracks published.",
                                    "Procurement timeline and RFP requirements package finalized.",
                                    "Deliverable: Implementation Roadmap approved by IT leadership."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Solution Architect", "allocation_percent": 25},
                                    {"name": "Lead Business Analyst", "allocation_percent": 50}
                                ]
                            }
                        ]
                    },
                    {
                        "id": "FEAT-020",
                        "title": "Executive Final Recommendation & Stakeholder Handover",
                        "description": "Deliver final strategic recommendation paper, executive presentation, and formal engagement deliverable handover.",
                        "strategic_theme": "Final Recommendation & Handover",
                        "traces_to": ["FR-009"],
                        "dependencies": ["EPIC-007", "EPIC-008"],
                        "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                        "job_size": 5,
                        "stories": [
                            {
                                "id": "STORY-040",
                                "title": "Final Strategic Recommendation Document Authoring & Executive Synthesis",
                                "description": "Synthesize all discovery findings, architectural assessments, market comparisons, and business case justification into the executive recommendation report.",
                                "strategic_theme": "Final Recommendation & Handover",
                                "traces_to": ["FR-009", "GOAL-001"],
                                "dependencies": ["STORY-034", "STORY-038"],
                                "timing": "Week 12",
                                "duration_days": 3,
                                "priority_components": {"user_business_value": 20, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "Executive recommendation paper completed detailing strategic justification for preferred option.",
                                    "Consolidated evidence references supporting all 9 engagement deliverables.",
                                    "Deliverable: Final Recommendation document formally delivered."
                                ],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Solution Architect", "allocation_percent": 25}
                                ]
                            },
                            {
                                "id": "STORY-041",
                                "title": "Governance Board Presentation & Formal Deliverable Handover",
                                "description": "Present strategic recommendations and roadmap to CIO, governance board, and complete formal deliverable handover signoff.",
                                "strategic_theme": "Final Recommendation & Handover",
                                "traces_to": ["FR-009"],
                                "dependencies": ["STORY-039", "STORY-040"],
                                "timing": "Week 12",
                                "duration_days": 2,
                                "priority_components": {"user_business_value": 13, "time_criticality": 13, "risk_reduction": 8},
                                "job_size": 2,
                                "acceptance_criteria": [
                                    "Executive presentation delivered to CIO, IT directors, and key business stakeholders.",
                                    "All 9 engagement deliverables formally accepted and signed off by project sponsor.",
                                    "Final engagement closure report and knowledge transfer completed."
                                ],
                                "resources": [
                                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                    {"name": "Lead Business Analyst", "allocation_percent": 100}
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
