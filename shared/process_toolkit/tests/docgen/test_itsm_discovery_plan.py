"""Tests for the 12-Week ITSM Discovery and Options Assessment Engagement project plan.

Validates compliance against the 5 key criteria:
1. Timescale: 12 weeks (60 working days, 480 working hours).
2. 9 Required Phases present as distinct summary tasks/branches.
3. Resources and allocations: Programme Delivery Manager (50%), Lead Business Analyst (100%),
   Business Analyst (100%), Solution Architect (50%).
4. All 9 required deliverables represented in the work breakdown.
5. Structural / Schema compliance: Valid MSPDI XML with <Resources> and <Assignments>
   and parsed Project JSON.
"""

import datetime as _dt
import xml.etree.ElementTree as ET
from unittest.mock import patch
import pytest

from process_toolkit import paths
from process_toolkit.docgen.project_plan_export import (
    build_portfolio_backlog_project_plan,
    build_proposal_response_project_plan,
    parse_mspdi_project,
    _MSPDI_NS,
)


@pytest.fixture
def itsm_12_week_backlog():
    return {
        "name": "12-Week ITSM Discovery and Options Assessment Engagement",
        "summary": "Assess current ITSM capabilities, processes, tooling, integrations, costs and requirements; evaluate future options; produce recommendations, roadmap and business case inputs.",
        "status": "OK",
        "timescale_weeks": 12,
        "rate_card": [
            {"role": "Programme Delivery Manager", "daily_rate": 1300.0, "basis": "Market benchmark for programme delivery management."},
            {"role": "Lead Business Analyst", "daily_rate": 1100.0, "basis": "Market benchmark for lead business analysis and requirements."},
            {"role": "Business Analyst", "daily_rate": 1000.0, "basis": "Market benchmark for business analysis and workshop facilitation."},
            {"role": "Solution Architect", "daily_rate": 1500.0, "basis": "Market benchmark for enterprise & ITSM solution architecture."}
        ],
        "roles": [
            {"name": "Programme Delivery Manager", "allocation_percent": 50},
            {"name": "Lead Business Analyst", "allocation_percent": 100},
            {"name": "Business Analyst", "allocation_percent": 100},
            {"name": "Solution Architect", "allocation_percent": 50}
        ],
        "epics": [
            {
                "id": "EPIC-01",
                "title": "Phase 1: Mobilisation",
                "features": [{
                    "id": "FEAT-01",
                    "title": "Engagement Mobilisation & Governance Kickoff",
                    "stories": [{
                        "id": "STORY-01",
                        "title": "Mobilisation & Project Governance Setup",
                        "job_size": 5,
                        "description": "Deliverable: Mobilisation Charter & Governance Framework.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-02",
                "title": "Phase 2: Current State Assessment",
                "features": [{
                    "id": "FEAT-02",
                    "title": "Current State Capabilities & Tooling Assessment",
                    "stories": [{
                        "id": "STORY-02",
                        "title": "Current State Assessment & Baseline Analysis",
                        "job_size": 10,
                        "description": "Deliverable: Current State Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-03",
                "title": "Phase 3: Requirements Discovery",
                "features": [{
                    "id": "FEAT-03",
                    "title": "Requirements Discovery & Elicitation",
                    "stories": [{
                        "id": "STORY-03",
                        "title": "Requirements Catalogue & Specification",
                        "job_size": 10,
                        "description": "Deliverable: Requirements Catalogue.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-04",
                "title": "Phase 4: Future State Definition",
                "features": [{
                    "id": "FEAT-04",
                    "title": "Future State Architecture & Operating Model",
                    "stories": [{
                        "id": "STORY-04",
                        "title": "Architecture Assessment & Target Operating Model",
                        "job_size": 5,
                        "description": "Deliverable: Architecture Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-05",
                "title": "Phase 5: Market Assessment",
                "features": [{
                    "id": "FEAT-05",
                    "title": "ITSM Platform Market Assessment",
                    "stories": [{
                        "id": "STORY-05",
                        "title": "Market Assessment & Vendor Landscape",
                        "job_size": 5,
                        "description": "Deliverable: Market Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-06",
                "title": "Phase 6: Options Appraisal",
                "features": [{
                    "id": "FEAT-06",
                    "title": "Options Appraisal & Evaluation Matrix",
                    "stories": [{
                        "id": "STORY-06",
                        "title": "Options Appraisal & Comparative Analysis",
                        "job_size": 5,
                        "description": "Deliverable: Options Appraisal.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-07",
                "title": "Phase 7: Business Case Support",
                "features": [{
                    "id": "FEAT-07",
                    "title": "Business Case Modeling & Evidence Pack",
                    "stories": [{
                        "id": "STORY-07",
                        "title": "Business Case Evidence Pack Formulation",
                        "job_size": 5,
                        "description": "Deliverable: Business Case Evidence Pack.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-08",
                "title": "Phase 8: Implementation Readiness Assessment",
                "features": [{
                    "id": "FEAT-08",
                    "title": "Implementation Readiness & Risk Evaluation",
                    "stories": [{
                        "id": "STORY-08",
                        "title": "Readiness Assessment & Transition Planning",
                        "job_size": 5,
                        "description": "Deliverable: Readiness Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50}
                        ]
                    }]
                }]
            },
            {
                "id": "EPIC-09",
                "title": "Phase 9: Final Recommendation & Handover",
                "features": [{
                    "id": "FEAT-09",
                    "title": "Final Recommendations & Implementation Roadmap",
                    "stories": [
                        {
                            "id": "STORY-09A",
                            "title": "Implementation Roadmap & Delivery Strategy",
                            "job_size": 5,
                            "description": "Deliverable: Implementation Roadmap.",
                            "resources": [
                                {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                {"name": "Lead Business Analyst", "allocation_percent": 100},
                                {"name": "Business Analyst", "allocation_percent": 100},
                                {"name": "Solution Architect", "allocation_percent": 50}
                            ]
                        },
                        {
                            "id": "STORY-09B",
                            "title": "Final Recommendation & Stakeholder Handover",
                            "job_size": 5,
                            "description": "Deliverable: Final Recommendation.",
                            "resources": [
                                {"name": "Programme Delivery Manager", "allocation_percent": 50},
                                {"name": "Lead Business Analyst", "allocation_percent": 100},
                                {"name": "Business Analyst", "allocation_percent": 100},
                                {"name": "Solution Architect", "allocation_percent": 50}
                            ]
                        }
                    ]
                }]
            }
        ]
    }


def test_itsm_12_week_project_plan_compliance(itsm_12_week_backlog):
    """Verifies that the generated project plan complies with all 5 audit criteria."""
    with patch("process_toolkit.docgen.project_plan_export.load_portfolio_backlog", return_value=itsm_12_week_backlog):
        result_msg = build_portfolio_backlog_project_plan(
            start_date="2026-11-23",
            target_duration_weeks=12,
        )
    assert "successfully exported" in result_msg
    assert "WARNING: Schedule Overrun" not in result_msg

    xml_path = paths.output_path("portfolio_backlog_project_plan.xml")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {"m": _MSPDI_NS}

    # 1. Timescale: 12 weeks = 60 working days = 480 working hours
    tasks = root.findall("m:Tasks/m:Task", ns)
    root_task = tasks[0]
    assert root_task.find("m:Duration", ns).text == "PT480H0M0S"
    assert root_task.find("m:Start", ns).text == "2026-11-23T08:00:00"
    assert root_task.find("m:Finish", ns).text == "2027-02-12T16:00:00"

    # 2. 9 Required Phases present as distinct summary branches (OutlineLevel 2)
    summary_phases = [
        t.find("m:Name", ns).text
        for t in tasks
        if t.find("m:Summary", ns) is not None
        and t.find("m:Summary", ns).text == "1"
        and t.find("m:OutlineLevel", ns).text == "2"
    ]
    expected_phases = [
        "Mobilisation",
        "Current State Assessment",
        "Requirements Discovery",
        "Future State Definition",
        "Market Assessment",
        "Options Appraisal",
        "Business Case Support",
        "Implementation Readiness Assessment",
        "Final Recommendation & Handover",
    ]
    assert len(summary_phases) == 9
    for exp_phase in expected_phases:
        assert any(exp_phase.lower() in p.lower() for p in summary_phases), f"Missing phase: {exp_phase}"

    # 3. Resources & Allocations: 4 roles with correct percentages
    resources = root.findall("m:Resources/m:Resource", ns)
    assert len(resources) == 4
    res_map = {
        r.find("m:Name", ns).text: float(r.find("m:MaxUnits", ns).text)
        for r in resources
    }
    assert res_map["Programme Delivery Manager"] == 0.5
    assert res_map["Lead Business Analyst"] == 1.0
    assert res_map["Business Analyst"] == 1.0
    assert res_map["Solution Architect"] == 0.5

    # 4. Deliverables: all 9 deliverables represented across stories/tasks
    all_task_names_and_notes = " ".join(
        (t.find("m:Name", ns).text or "") + " " + (t.find("m:Notes", ns).text if t.find("m:Notes", ns) is not None else "")
        for t in tasks
    )
    expected_deliverables = [
        "Current State Assessment",
        "Requirements Catalogue",
        "Architecture Assessment",
        "Market Assessment",
        "Options Appraisal",
        "Business Case Evidence Pack",
        "Implementation Roadmap",
        "Readiness Assessment",
        "Final Recommendation",
    ]
    for d in expected_deliverables:
        assert d.lower() in all_task_names_and_notes.lower(), f"Missing deliverable: {d}"

    # 5. Schema & Structural Compliance: <Assignments> present and parsed Project JSON
    assignments = root.findall("m:Assignments/m:Assignment", ns)
    assert len(assignments) == 40  # 10 leaf stories * 4 resources

    from process_toolkit.docgen.project_plan_export import validate_mspdi_xml
    assert validate_mspdi_xml(xml_path) == []

    parsed = parse_mspdi_project(xml_path)
    assert parsed["title"] == "12-Week ITSM Discovery and Options Assessment Engagement"
    assert parsed["start_date"] == "2026-11-23T08:00:00"
    assert parsed["finish_date"] == "2027-02-12T16:00:00"
    assert len(parsed["resources"]) == 4
    assert len(parsed["assignments"]) == 40
    # Total cost = 60 days * (0.5*1300 + 1.0*1100 + 1.0*1000 + 0.5*1500) = 60 * 3500 = £210,000
    assert parsed["total_cost"] == 210000.0


def test_itsm_12_week_proposal_response_project_plan_compliance():
    """Verifies that an implementation_plan in proposal_response also exports a 100% compliant plan."""
    itsm_proposal = {
        "name": "12-Week ITSM Discovery and Options Assessment Engagement",
        "status": "OK",
        "rate_card": [
            {"role": "Programme Delivery Manager", "daily_rate": 1300.0},
            {"role": "Lead Business Analyst", "daily_rate": 1100.0},
            {"role": "Business Analyst", "daily_rate": 1000.0},
            {"role": "Solution Architect", "daily_rate": 1500.0},
        ],
        "implementation_plan": [
            {
                "phase": "Phase 1: Mobilisation",
                "timing": "Week 1 (5 days)",
                "deliverable": "Mobilisation Charter & Governance Framework",
                "acceptance_criteria": "Project governance established, stakeholder matrix agreed.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 2: Current State Assessment",
                "timing": "Weeks 2-3 (10 days)",
                "deliverable": "Current State Assessment",
                "acceptance_criteria": "Baseline ITSM capabilities, tooling, integrations, and operational costs documented.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 3: Requirements Discovery",
                "timing": "Weeks 4-5 (10 days)",
                "deliverable": "Requirements Catalogue",
                "acceptance_criteria": "Comprehensive functional and non-functional requirements catalogue signed off.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 4: Future State Definition",
                "timing": "Week 6 (5 days)",
                "deliverable": "Architecture Assessment & Target Operating Model",
                "acceptance_criteria": "Target Operating Model and future-state architecture definition completed.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 5: Market Assessment",
                "timing": "Week 7 (5 days)",
                "deliverable": "Market Assessment",
                "acceptance_criteria": "ITSM tooling market evaluation and vendor capability assessment completed.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 6: Options Appraisal",
                "timing": "Week 8 (5 days)",
                "deliverable": "Options Appraisal",
                "acceptance_criteria": "Multi-criteria evaluation matrix and shortlisted options appraisal documented.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 7: Business Case Support",
                "timing": "Week 9 (5 days)",
                "deliverable": "Business Case Evidence Pack",
                "acceptance_criteria": "TCO, ROI modeling, and business case evidence pack finalized.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 8: Implementation Readiness Assessment",
                "timing": "Week 10 (5 days)",
                "deliverable": "Readiness Assessment",
                "acceptance_criteria": "Organizational readiness, skills, governance, and risk assessments documented.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
            {
                "phase": "Phase 9: Final Recommendation & Handover",
                "timing": "Weeks 11-12 (10 days)",
                "deliverable": "Implementation Roadmap & Final Recommendation",
                "acceptance_criteria": "Strategic recommendations, delivery roadmap, and handover sign-off completed.",
                "resources": [
                    {"name": "Programme Delivery Manager", "allocation_percent": 50},
                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                    {"name": "Business Analyst", "allocation_percent": 100},
                    {"name": "Solution Architect", "allocation_percent": 50},
                ],
            },
        ],
    }

    with patch("process_toolkit.docgen.project_plan_export.load_proposal_response", return_value=itsm_proposal):
        result_msg = build_proposal_response_project_plan(
            start_date="2026-11-23",
            target_duration_weeks=12,
        )
    assert "successfully exported" in result_msg
    assert "WARNING: Schedule Overrun" not in result_msg

    xml_path = paths.output_path("proposal_response_project_plan.xml")
    from process_toolkit.docgen.project_plan_export import validate_mspdi_xml
    assert validate_mspdi_xml(xml_path) == []
    parsed = parse_mspdi_project(xml_path)
    assert parsed["title"] == "12-Week ITSM Discovery and Options Assessment Engagement"
    assert parsed["start_date"] == "2026-11-23T08:00:00"
    assert parsed["finish_date"] == "2027-02-12T16:00:00"
    assert len(parsed["resources"]) == 4
    assert len(parsed["tasks"]) == 10  # 1 root + 9 phases
    assert parsed["total_cost"] == 210000.0


def test_itsm_12_week_parallel_streams_and_slack():
    """Verifies that when backlog or proposal specifies concurrent discovery streams,
    tasks run in parallel, dependencies link correctly, and slack/float is accurately computed."""
    parallel_backlog = {
        "name": "12-Week ITSM Discovery and Options Assessment Engagement",
        "summary": "Assess current ITSM capabilities, processes, tooling, integrations, costs and requirements; evaluate future options; produce recommendations, roadmap and business case inputs.",
        "status": "OK",
        "timescale_weeks": 12,
        "rate_card": [
            {"role": "Programme Delivery Manager", "daily_rate": 1300.0},
            {"role": "Lead Business Analyst", "daily_rate": 1100.0},
            {"role": "Business Analyst", "daily_rate": 1000.0},
            {"role": "Solution Architect", "daily_rate": 1500.0},
        ],
        "roles": [
            {"name": "Programme Delivery Manager", "allocation_percent": 50},
            {"name": "Lead Business Analyst", "allocation_percent": 100},
            {"name": "Business Analyst", "allocation_percent": 100},
            {"name": "Solution Architect", "allocation_percent": 50},
        ],
        "epics": [
            {
                "id": "EPIC-01",
                "title": "Phase 1: Mobilisation",
                "dependencies": [],
                "features": [{
                    "id": "FEAT-01",
                    "title": "Engagement Mobilisation & Governance Kickoff",
                    "stories": [{
                        "id": "STORY-01",
                        "title": "Mobilisation & Project Governance Setup",
                        "duration_days": 5,
                        "description": "Deliverable: Mobilisation Charter & Governance Framework.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-02",
                "title": "Phase 2: Current State Assessment",
                "dependencies": ["EPIC-01"],
                "features": [{
                    "id": "FEAT-02",
                    "title": "Current State Capabilities & Tooling Assessment",
                    "stories": [{
                        "id": "STORY-02",
                        "title": "Current State Assessment & Baseline Analysis",
                        "duration_days": 15,  # Weeks 2-4 (3 weeks)
                        "description": "Deliverable: Current State Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-03",
                "title": "Phase 3: Requirements Discovery",
                "dependencies": ["EPIC-01"],
                "features": [{
                    "id": "FEAT-03",
                    "title": "Requirements Discovery & Elicitation",
                    "stories": [{
                        "id": "STORY-03",
                        "title": "Requirements Catalogue & Specification",
                        "duration_days": 20,  # Weeks 2-5 (4 weeks) -> runs parallel with Phase 2
                        "description": "Deliverable: Requirements Catalogue.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-04",
                "title": "Phase 4: Future State Definition",
                "dependencies": ["EPIC-02", "EPIC-03"],
                "features": [{
                    "id": "FEAT-04",
                    "title": "Future State Architecture & Operating Model",
                    "stories": [{
                        "id": "STORY-04",
                        "title": "Architecture Assessment & Target Operating Model",
                        "duration_days": 10,  # Weeks 6-7 (2 weeks)
                        "description": "Deliverable: Architecture Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-05",
                "title": "Phase 5: Market Assessment",
                "dependencies": ["EPIC-02", "EPIC-03"],
                "features": [{
                    "id": "FEAT-05",
                    "title": "ITSM Platform Market Assessment",
                    "stories": [{
                        "id": "STORY-05",
                        "title": "Market Assessment & Vendor Landscape",
                        "duration_days": 10,  # Weeks 6-7 (2 weeks) -> runs parallel with Phase 4
                        "description": "Deliverable: Market Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-06",
                "title": "Phase 6: Options Appraisal",
                "dependencies": ["EPIC-04", "EPIC-05"],
                "features": [{
                    "id": "FEAT-06",
                    "title": "Options Appraisal & Evaluation Matrix",
                    "stories": [{
                        "id": "STORY-06",
                        "title": "Options Appraisal & Comparative Analysis",
                        "duration_days": 10,  # Weeks 8-9 (2 weeks)
                        "description": "Deliverable: Options Appraisal.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-07",
                "title": "Phase 7: Business Case Support",
                "dependencies": ["EPIC-06"],
                "features": [{
                    "id": "FEAT-07",
                    "title": "Business Case Modeling & Evidence Pack",
                    "stories": [{
                        "id": "STORY-07",
                        "title": "Business Case Evidence Pack Formulation",
                        "duration_days": 10,  # Weeks 10-11 (2 weeks)
                        "description": "Deliverable: Business Case Evidence Pack.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-08",
                "title": "Phase 8: Implementation Readiness Assessment",
                "dependencies": ["EPIC-06"],
                "features": [{
                    "id": "FEAT-08",
                    "title": "Implementation Readiness & Risk Evaluation",
                    "stories": [{
                        "id": "STORY-08",
                        "title": "Readiness Assessment & Transition Planning",
                        "duration_days": 10,  # Weeks 10-11 (2 weeks) -> runs parallel with Phase 7
                        "description": "Deliverable: Readiness Assessment.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
            {
                "id": "EPIC-09",
                "title": "Phase 9: Final Recommendation & Handover",
                "dependencies": ["EPIC-07", "EPIC-08"],
                "features": [{
                    "id": "FEAT-09",
                    "title": "Final Recommendations & Implementation Roadmap",
                    "stories": [{
                        "id": "STORY-09",
                        "title": "Final Recommendation, Roadmap & Handover",
                        "duration_days": 5,  # Week 12 (1 week)
                        "description": "Deliverable: Implementation Roadmap and Final Recommendation.",
                        "resources": [
                            {"name": "Programme Delivery Manager", "allocation_percent": 50},
                            {"name": "Lead Business Analyst", "allocation_percent": 100},
                            {"name": "Business Analyst", "allocation_percent": 100},
                            {"name": "Solution Architect", "allocation_percent": 50},
                        ],
                    }],
                }],
            },
        ],
    }

    with patch("process_toolkit.docgen.project_plan_export.load_portfolio_backlog", return_value=parallel_backlog):
        result_msg = build_portfolio_backlog_project_plan(
            start_date="2026-11-23",
            target_duration_weeks=12,
        )

    assert "successfully exported" in result_msg
    xml_path = paths.output_path("portfolio_backlog_project_plan.xml")
    from process_toolkit.docgen.project_plan_export import validate_mspdi_xml
    assert validate_mspdi_xml(xml_path) == []
    parsed = parse_mspdi_project(xml_path)

    # 1. Total span is exactly 12 weeks (Nov 23, 2026 to Feb 12, 2027)
    assert parsed["start_date"] == "2026-11-23T08:00:00"
    assert parsed["finish_date"] == "2027-02-12T16:00:00"

    tasks_by_name = {t["name"]: t for t in parsed["tasks"]}

    # 2. Concurrency: Phase 2 and Phase 3 both start on 2026-11-30 (immediately after Phase 1)
    p2 = tasks_by_name["Phase 2: Current State Assessment"]
    p3 = tasks_by_name["Phase 3: Requirements Discovery"]
    assert p2["start"] == "2026-11-30T08:00:00"
    assert p3["start"] == "2026-11-30T08:00:00"

    # Phase 2 is 15 working days (finishes Dec 18) while Phase 3 is 20 working days (finishes Dec 25)
    assert p2["finish"] == "2026-12-18T16:00:00"
    assert p3["finish"] == "2026-12-25T16:00:00"

    # 3. Phase 4 starts on Dec 28 (after both Phase 2 and Phase 3 finish)
    p4 = tasks_by_name["Phase 4: Future State Definition"]
    p5 = tasks_by_name["Phase 5: Market Assessment"]
    assert p4["start"] == "2026-12-28T08:00:00"
    assert p5["start"] == "2026-12-28T08:00:00"

    # 4. Multi-predecessor verification in XML
    story4 = tasks_by_name["Architecture Assessment & Target Operating Model"]
    story2 = tasks_by_name["Current State Assessment & Baseline Analysis"]
    story3 = tasks_by_name["Requirements Catalogue & Specification"]
    assert str(story2["uid"]) in story4["predecessor_uids"]
    assert str(story3["uid"]) in story4["predecessor_uids"]

    # 5. PERT/CPM: Phase 2 finished early, so its leaf story has 5 working days of float
    from process_toolkit.docgen.pert_cpm_export import _compute_cpm
    leaves = [t for t in parsed["tasks"] if not t["is_summary"]]
    cpm_input = [
        {
            "uid": int(t["uid"]),
            "name": t["name"],
            "start": _dt.date.fromisoformat(t["start"].split("T")[0]),
            "finish": _dt.date.fromisoformat(t["finish"].split("T")[0]),
            "duration_days": int(t["duration_hours"] / 8),
            "predecessor_uids": [int(u) for u in t.get("predecessor_uids", []) if u.isdigit()],
        }
        for t in leaves
    ]
    cpm_scored = _compute_cpm(cpm_input)
    cpm_by_name = {c["name"]: c for c in cpm_scored}

    # Phase 2 story has 5 days of float and is not critical
    assert cpm_by_name["Current State Assessment & Baseline Analysis"]["float_days"] == 5
    assert cpm_by_name["Current State Assessment & Baseline Analysis"]["critical"] is False

    # Phase 3 story is on the critical path (0 float)
    assert cpm_by_name["Requirements Catalogue & Specification"]["float_days"] == 0
    assert cpm_by_name["Requirements Catalogue & Specification"]["critical"] is True
