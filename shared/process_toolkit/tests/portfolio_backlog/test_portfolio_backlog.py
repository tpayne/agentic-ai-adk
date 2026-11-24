import json
import os
import copy

from openpyxl import load_workbook

from process_toolkit import paths
from process_toolkit.portfolio_backlog.portfolio_backlog import (
    PORTFOLIO_BACKLOG_FILENAME,
    PORTFOLIO_BACKLOG_WORKBOOK_FILENAME,
    load_portfolio_backlog,
    save_portfolio_backlog,
)


def _sample_backlog():
    return {
        "name": "MetroLink Delivery Backlog",
        "summary": "Delivery backlog for the MetroLink vendor onboarding design.",
        "source_artifact": "design",
        "source_name": "MetroLink Vendor Onboarding",
        "epics": [
            {
                "id": "EPIC-001",
                "title": "Onboard vendors digitally",
                "description": "Deliver a secure digital vendor onboarding capability.",
                "strategic_theme": "Digital procurement",
                "traces_to": ["FR-001"],
                "priority_components": {
                    "user_business_value": 13,
                    "time_criticality": 8,
                    "risk_reduction": 5,
                },
                "job_size": 13,
                "features": [
                    {
                        "id": "FEAT-001",
                        "title": "Submit vendor applications",
                        "description": "Allow vendors to complete an onboarding application.",
                        "traces_to": ["FR-001"],
                        "priority_components": {
                            "user_business_value": 8,
                            "time_criticality": 5,
                            "risk_reduction": 3,
                        },
                        "job_size": 8,
                        "stories": [
                            {
                                "id": "STORY-001",
                                "title": "Save a draft application",
                                "description": "As a vendor, I can save an incomplete application.",
                                "traces_to": ["FR-001"],
                                "priority_components": {
                                    "user_business_value": 5,
                                    "time_criticality": 3,
                                    "risk_reduction": 2,
                                },
                                "job_size": 3,
                                "acceptance_criteria": [
                                    "A vendor can save and reopen an incomplete application.",
                                    "The saved draft is visible only to its vendor account.",
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_save_generates_template_based_workbook_with_hierarchy_formulas_and_assumptions():
    backlog = _sample_backlog()
    result = save_portfolio_backlog(backlog)

    assert result.startswith("SUCCESS:")
    assert "3 work items, 1 epics" in result
    with open(paths.output_path(PORTFOLIO_BACKLOG_FILENAME), encoding="utf-8") as file:
        assert json.load(file)["name"] == backlog["name"]

    workbook = load_workbook(paths.output_path(PORTFOLIO_BACKLOG_WORKBOOK_FILENAME), data_only=False)
    sheet = workbook["Enterprise Agile Backlog"]
    assert workbook.sheetnames == [
        "Enterprise Agile Backlog",
        "Portfolio Backlog Guide",
        "Assumptions",
        "Role Rates",
    ]
    assert sheet["A1"].value == "Enterprise Agile Portfolio Backlog"
    assert all(sheet[f"D{row}"].fill.fill_type is None for row in range(1, 4))
    assert sheet["A5"].value == "Work Item ID"
    assert sheet["L6"].value == "Epic"
    assert sheet["L7"].value == "Feature"
    assert sheet["M7"].value == "EPIC-001"
    assert sheet["L8"].value == "Story"
    assert sheet["M8"].value == "FEAT-001"
    assert sheet["N8"].value == "FR-001"
    assert sheet["P8"].value.startswith("- A vendor can save")
    assert sheet["S5"].value == "Costed Roles"
    assert "Role Rates" in sheet["S8"].value
    assert "'Role Rates'!$B$8" in sheet["S8"].value
    assert sheet["S6"].value == "Rolled up from child items; see story-level roles."
    assert sheet["H8"].value == (
        "=E8*'Assumptions'!$B$13+F8*'Assumptions'!$B$14"
        "+G8*'Assumptions'!$B$15"
    )
    assert sheet["J8"].value == "=IFERROR(H8/I8,0)"
    assert sheet["K8"].value.startswith("=1+COUNTIFS(")
    assert sheet["Q8"].value.startswith("=I8*'Assumptions'!$B$6*(1+'Assumptions'!$B$7)*(")
    assert "'Role Rates'!$D$8" in sheet["Q8"].value
    assert sheet["Q7"].value == "=SUMIF($M$6:$M$8,A7,$Q$6:$Q$8)"
    assert sheet["Q6"].value == "=SUMIF($M$6:$M$8,A6,$Q$6:$Q$8)"
    assert sheet["Q9"].value.startswith('=SUMIF($L$6:$L$8,"Epic"')
    assert {
        (sheet.cell(row, column).fill.fill_type, sheet.cell(row, column).fill.fgColor.rgb)
        for row in range(6, 9)
        for column in range(1, 20)
    } == {("solid", "00FFFFFF")}
    assert sheet["T2"].value == "=A6"
    assert sheet["U2"].value == "=J6"
    assert sheet.column_dimensions["T"].hidden
    assert sheet.column_dimensions["U"].hidden
    chart = sheet._charts[0]
    assert chart.anchor._from.row + 1 == 12
    assert chart.visible_cells_only is False
    assert chart.series[0].cat.strRef.f == "'Enterprise Agile Backlog'!$T$2:$T$2"
    assert chart.series[0].val.numRef.f == "'Enterprise Agile Backlog'!$U$2:$U$2"

    assumptions = workbook["Assumptions"]
    assert assumptions["B4"].value == "USD"
    assert assumptions["B5"].value == "=SUM('Role Rates'!E5:E10)"
    assert assumptions["B6"].value == 1.5
    assert assumptions["B7"].value == 0.2
    assert assumptions["B13"].value == 1.0
    assert assumptions["B14"].value == 1.0
    assert assumptions["B15"].value == 1.0
    assert assumptions["A16"].value == "Priority score scale"
    assert assumptions["A17"].value == "Priority score basis"
    assert assumptions["A19"].value == "Cost of Delay formula"
    assert assumptions["A20"].value == "WSJF formula"
    assert assumptions["A21"].value == "WSJF rank scope and ties"
    assert assumptions["A22"].value == "Default work item state"
    assert assumptions["A23"].value == "Default strategic theme"
    assert "not a quote" in assumptions["B10"].value
    assert assumptions["B24"].value == "See Role Rates worksheet"
    assert assumptions["C24"].value == (
        "Editable role names, effort mix, and illustrative USD daily rates are "
        "maintained only on the separate Role Rates worksheet."
    )
    assert all(assumptions.cell(row, column).value is None for row in range(28, 37) for column in range(1, 6))
    assert [assumptions.cell(row, 1).value for row in range(4, 13)] == [
        "Currency",
        "Blended fully-loaded delivery cost per person-day",
        "Effort per story point (person-days)",
        "Contingency uplift",
        "Story-level cost formula",
        "Estimate scope",
        "Estimate status",
        "Source artifact",
        "Source name",
    ]

    role_rates = workbook["Role Rates"]
    assert role_rates["A4"].value == "Person"
    assert role_rates["B4"].value == "Delivery Role"
    assert role_rates["C4"].value == "Effort Mix"
    assert role_rates["D4"].value == "Daily Rate (USD)"
    assert role_rates["E4"].value == "Weighted Rate Contribution (USD/day)"
    assert [role_rates.cell(row, 2).value for row in range(5, 11)] == [
        "Product Owner",
        "Business Analyst",
        "Solution Architect",
        "Software Engineer",
        "QA Engineer",
        "DevOps / Platform Engineer",
    ]
    assert all(role_rates.cell(row, 1).value == "TBD" for row in range(5, 11))
    assert role_rates["F4"].value == "Rate Basis"
    assert sum(role_rates.cell(row, 3).value for row in range(5, 11)) == 1.0
    assert sum(
        role_rates.cell(row, 3).value * role_rates.cell(row, 4).value
        for row in range(5, 11)
    ) == 1200
    assert role_rates["E5"].value == "=IFERROR(C5/SUM($C$5:$C$10)*D5,0)"
    assert all(
        role_rates.cell(row, 6).value.startswith("Illustrative default")
        for row in range(5, 11)
    )
    assert role_rates["C11"].value == "=SUM(C5:C10)"
    assert role_rates["E11"].value == "=SUM(E5:E10)"


def test_save_rejects_invalid_size_and_does_not_create_artifacts():
    backlog = _sample_backlog()
    backlog["epics"][0]["job_size"] = 4

    result = save_portfolio_backlog(backlog)

    assert result.startswith("ERROR:")
    assert "job_size" in result
    assert not os.path.exists(paths.output_path(PORTFOLIO_BACKLOG_FILENAME))
    assert not os.path.exists(paths.output_path(PORTFOLIO_BACKLOG_WORKBOOK_FILENAME))


def test_save_and_load_use_session_state_and_persist_json():
    state = {}
    backlog = _sample_backlog()

    result = save_portfolio_backlog(backlog, state)

    assert result.startswith("SUCCESS:")
    loaded = load_portfolio_backlog(state)
    assert loaded["status"] == "OK"
    assert loaded["name"] == backlog["name"]
    assert load_portfolio_backlog()["name"] == backlog["name"]


def test_load_without_a_saved_backlog_returns_not_found():
    assert load_portfolio_backlog() == {"status": "NOT_FOUND"}


def test_save_rejects_duplicate_ids():
    backlog = _sample_backlog()
    backlog["epics"][0]["features"][0]["stories"][0]["id"] = "EPIC-001"

    result = save_portfolio_backlog(backlog)

    assert result.startswith("ERROR:")
    assert "Duplicate work item id" in result


def test_workbook_expands_beyond_template_rows_without_losing_summary_formulas():
    backlog = _sample_backlog()
    base_epic = backlog["epics"][0]
    for index in range(2, 5):
        epic = copy.deepcopy(base_epic)
        epic["id"] = f"EPIC-00{index}"
        epic["features"][0]["id"] = f"FEAT-00{index}"
        epic["features"][0]["stories"][0]["id"] = f"STORY-00{index}"
        backlog["epics"].append(epic)

    result = save_portfolio_backlog(backlog)

    assert result.startswith("SUCCESS:")
    workbook = load_workbook(paths.output_path(PORTFOLIO_BACKLOG_WORKBOOK_FILENAME), data_only=False)
    sheet = workbook["Enterprise Agile Backlog"]
    assert sheet["A17"].value == "STORY-004"
    assert sheet["K17"].value.endswith("$J$17,\">\"&J17)")
    assert sheet["Q18"].value == '=SUMIF($L$6:$L$17,"Epic",$Q$6:$Q$17)'
    chart = sheet._charts[0]
    assert chart.anchor._from.row + 1 == 21
    assert chart.series[0].cat.strRef.f == "'Enterprise Agile Backlog'!$T$2:$T$5"
    assert chart.series[0].val.numRef.f == "'Enterprise Agile Backlog'!$U$2:$U$5"


def test_activity_based_resource_calculation():
    from process_toolkit.portfolio_backlog.portfolio_backlog import (
        calculate_story_resources,
        ROLE_DEVOPS_ENGINEER,
        ROLE_QA_ENGINEER,
        ROLE_SOLUTION_ARCHITECT,
        ROLE_BUSINESS_ANALYST,
        ROLE_SOFTWARE_ENGINEER,
    )

    devops_story = {
        "title": "Deploy Centralized Backup Policies",
        "description": "As a Platform Administrator, I want to deploy terraform backup policies across AWS accounts.",
        "acceptance_criteria": ["Terraform applies cleanly", "Backup plan is active"],
        "strategic_theme": "Cloud Infrastructure",
    }
    devops_res = calculate_story_resources(devops_story)
    assert devops_res[0]["name"] == ROLE_DEVOPS_ENGINEER
    assert devops_res[0]["allocation_percent"] == 60.0
    assert sum(r["allocation_percent"] for r in devops_res) == 100.0

    qa_story = {
        "title": "Automate E2E Regression Testing Suite",
        "description": "Verify and validate system behavior with automated test cases.",
        "acceptance_criteria": ["All smoke and regression tests pass"],
        "strategic_theme": "Quality & Compliance",
    }
    qa_res = calculate_story_resources(qa_story)
    assert qa_res[0]["name"] == ROLE_QA_ENGINEER
    assert qa_res[0]["allocation_percent"] == 60.0

    arch_story = {
        "title": "Architect Multi-Tenant Solution Design",
        "description": "Evaluate architectural tradeoffs and define high-level design standards.",
        "acceptance_criteria": ["HLD document approved"],
        "strategic_theme": "Architecture Governance",
    }
    arch_res = calculate_story_resources(arch_story)
    assert arch_res[0]["name"] == ROLE_SOLUTION_ARCHITECT
    assert arch_res[0]["allocation_percent"] == 60.0

    ba_story = {
        "title": "Capture Stakeholder Requirements for Onboarding",
        "description": "Interview business stakeholders and map business process workflow.",
        "acceptance_criteria": ["Requirements register signed off"],
        "strategic_theme": "Process Optimization",
    }
    ba_res = calculate_story_resources(ba_story)
    assert ba_res[0]["name"] == ROLE_BUSINESS_ANALYST
    assert ba_res[0]["allocation_percent"] == 60.0

    dev_story = {
        "title": "Implement User Profile API Endpoint",
        "description": "Develop CRUD REST API handler in backend service.",
        "acceptance_criteria": ["Endpoint returns 200 OK"],
        "strategic_theme": "Core Features",
    }
    dev_res = calculate_story_resources(dev_story)
    assert dev_res[0]["name"] == ROLE_SOFTWARE_ENGINEER
    assert dev_res[0]["allocation_percent"] == 60.0


def test_backlog_json_includes_resources_on_stories_and_top_level():
    backlog = _sample_backlog()
    save_portfolio_backlog(backlog)

    with open(paths.output_path(PORTFOLIO_BACKLOG_FILENAME), encoding="utf-8") as f:
        saved = json.load(f)

    assert "resources" in saved
    assert len(saved["resources"]) > 0
    story = saved["epics"][0]["features"][0]["stories"][0]
    assert "resources" in story
    assert len(story["resources"]) > 0
    assert sum(r["allocation_percent"] for r in story["resources"]) == 100.0


def test_explicit_story_resources_preserved():
    backlog = _sample_backlog()
    custom_res = [
        {"name": "DevOps / Platform Engineer", "allocation_percent": 80.0},
        {"name": "QA Engineer", "allocation_percent": 20.0},
    ]
    backlog["epics"][0]["features"][0]["stories"][0]["resources"] = custom_res
    save_portfolio_backlog(backlog)

    with open(paths.output_path(PORTFOLIO_BACKLOG_FILENAME), encoding="utf-8") as f:
        saved = json.load(f)

    story = saved["epics"][0]["features"][0]["stories"][0]
    assert story["resources"] == custom_res


def test_backlog_json_includes_projected_rate_card_by_default():
    backlog = _sample_backlog()
    save_portfolio_backlog(backlog)

    with open(paths.output_path(PORTFOLIO_BACKLOG_FILENAME), encoding="utf-8") as f:
        saved = json.load(f)

    assert "rate_card" in saved
    assert len(saved["rate_card"]) >= 6
    roles = {entry["role"]: entry for entry in saved["rate_card"]}
    assert "Solution Architect" in roles
    assert roles["Solution Architect"]["daily_rate"] == 1500.0
    assert "Software Engineer" in roles
    assert roles["Software Engineer"]["daily_rate"] == 1275.0
    assert sum(entry["effort_mix"] for entry in saved["rate_card"]) == 1.0


def test_explicit_rate_card_populates_role_rates_sheet_and_story_formulas():
    backlog = _sample_backlog()
    custom_rate_card = [
        {
            "person": "Lead Architect",
            "role": "Solution Architect",
            "effort_mix": 0.20,
            "daily_rate": 1600.0,
            "basis": "Custom enterprise architecture rate.",
        },
        {
            "person": "Lead Dev",
            "role": "Software Engineer",
            "effort_mix": 0.50,
            "daily_rate": 1350.0,
            "basis": "Senior developer rate.",
        },
        {
            "person": "Platform Lead",
            "role": "DevOps / Platform Engineer",
            "effort_mix": 0.30,
            "daily_rate": 1300.0,
            "basis": "Cloud infrastructure rate.",
        },
    ]
    backlog["rate_card"] = custom_rate_card
    backlog["epics"][0]["features"][0]["stories"][0]["resources"] = [
        {"name": "Solution Architect", "allocation_percent": 40.0},
        {"name": "Software Engineer", "allocation_percent": 60.0},
    ]
    save_portfolio_backlog(backlog)

    with open(paths.output_path(PORTFOLIO_BACKLOG_FILENAME), encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["rate_card"][0]["daily_rate"] == 1600.0

    workbook = load_workbook(paths.output_path(PORTFOLIO_BACKLOG_WORKBOOK_FILENAME), data_only=False)
    role_rates = workbook["Role Rates"]
    assert role_rates["A5"].value == "Lead Architect"
    assert role_rates["B5"].value == "Solution Architect"
    assert role_rates["D5"].value == 1600.0
    assert role_rates["F5"].value == "Custom enterprise architecture rate."

    assumptions = workbook["Assumptions"]
    assert assumptions["B5"].value == "=SUM('Role Rates'!E5:E7)"

    sheet = workbook["Enterprise Agile Backlog"]
    assert "'Role Rates'!$B$5" in sheet["S8"].value
    assert "'Role Rates'!$B$6" in sheet["S8"].value
    assert "'Role Rates'!$D$5" in sheet["Q8"].value
    assert "'Role Rates'!$D$6" in sheet["Q8"].value


def test_clean_effort_mix_removes_precision_skews():
    from process_toolkit.portfolio_backlog.portfolio_backlog import build_rate_card
    backlog = {
        "rate_card": [
            {"person": "TBD", "role": "Programme Delivery Manager", "effort_mix": 0.1663, "daily_rate": 1300.0},
            {"person": "TBD", "role": "Lead Business Analyst", "effort_mix": 0.3337, "daily_rate": 1100.0},
            {"person": "TBD", "role": "Business Analyst", "effort_mix": 0.3337, "daily_rate": 1000.0},
            {"person": "TBD", "role": "Solution Architect", "effort_mix": 0.1663, "daily_rate": 1500.0},
        ]
    }
    card = build_rate_card(backlog)
    mixes = [c["effort_mix"] for c in card]
    assert mixes == [0.1667, 0.3333, 0.3333, 0.1667]
    assert sum(mixes) == 1.0


def test_traceability_id_format_normalization(tmp_path, monkeypatch):
    from process_toolkit.portfolio_backlog.portfolio_backlog import save_portfolio_backlog, _normalize_id_format
    assert _normalize_id_format("FR_001A") == "FR-001A"
    assert _normalize_id_format("CON_001") == "CON-001"
    assert _normalize_id_format("INF_002") == "INF-002"
    assert _normalize_id_format("FR-001A") == "FR-001A"

    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    backlog = {
        "name": "Test Backlog",
        "summary": "Summary",
        "source_name": "Test Source",
        "source_artifact": "design",
        "requirements_reference": {
            "FR_001A": {"id": "FR_001A", "title": "Req 1"},
            "CON_001": {"id": "CON_001", "title": "Req 2"},
        },
        "epics": [
            {
                "id": "EPIC-1",
                "title": "Epic 1",
                "description": "Desc",
                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                "job_size": 3,
                "traces_to": ["FR_001A"],
                "features": [
                    {
                        "id": "FEAT-1",
                        "title": "Feat 1",
                        "description": "Desc",
                        "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                        "job_size": 3,
                        "traces_to": ["FR_001A"],
                        "stories": [
                            {
                                "id": "STORY-1",
                                "title": "Story 1",
                                "description": "Desc",
                                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                                "job_size": 3,
                                "traces_to": ["FR_001A", "CON_001"],
                                "acceptance_criteria": ["Criteria 1"],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    msg = save_portfolio_backlog(backlog)
    assert "SUCCESS" in msg
    assert "FR-001A" in backlog["requirements_reference"]
    assert "CON-001" in backlog["requirements_reference"]
    assert backlog["epics"][0]["traces_to"] == ["FR-001A"]
    assert backlog["epics"][0]["features"][0]["stories"][0]["traces_to"] == ["FR-001A", "CON-001"]


def test_dependency_cycle_detection_and_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    # Test circular dependency
    circular_backlog = {
        "name": "Circular Backlog",
        "summary": "Summary",
        "source_name": "Test Source",
        "source_artifact": "design",
        "epics": [
            {
                "id": "EPIC-1",
                "title": "Epic 1",
                "description": "Desc",
                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                "job_size": 3,
                "traces_to": ["REQ-1"],
                "features": [
                    {
                        "id": "FEAT-1",
                        "title": "Feat 1",
                        "description": "Desc",
                        "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                        "job_size": 3,
                        "traces_to": ["REQ-1"],
                        "stories": [
                            {
                                "id": "STORY-1",
                                "title": "Story 1",
                                "description": "Desc",
                                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                                "job_size": 3,
                                "traces_to": ["REQ-1"],
                                "acceptance_criteria": ["C1"],
                                "dependencies": ["STORY-2"],
                            },
                            {
                                "id": "STORY-2",
                                "title": "Story 2",
                                "description": "Desc",
                                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                                "job_size": 3,
                                "traces_to": ["REQ-1"],
                                "acceptance_criteria": ["C2"],
                                "dependencies": ["STORY-1"],
                            },
                        ]
                    }
                ]
            }
        ]
    }
    msg = save_portfolio_backlog(circular_backlog)
    assert "ERROR" in msg
    assert "Circular dependency detected" in msg

    # Test self-dependency
    self_dep_backlog = copy.deepcopy(circular_backlog)
    self_dep_backlog["epics"][0]["features"][0]["stories"][0]["dependencies"] = ["STORY-1"]
    msg_self = save_portfolio_backlog(self_dep_backlog)
    assert "ERROR" in msg_self
    assert "cannot depend on itself" in msg_self


def test_story_job_size_duration_rollups(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    backlog = {
        "name": "Rollup Backlog",
        "summary": "Summary",
        "source_name": "Test Source",
        "source_artifact": "design",
        "epics": [
            {
                "id": "EPIC-1",
                "title": "Epic 1",
                "description": "Desc",
                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                "job_size": 3,
                "traces_to": ["REQ-1"],
                "features": [
                    {
                        "id": "FEAT-1",
                        "title": "Feat 1",
                        "description": "Desc",
                        "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                        "job_size": 3,
                        "traces_to": ["REQ-1"],
                        "stories": [
                            {
                                "id": "STORY-1",
                                "title": "Story 1",
                                "description": "Desc",
                                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                                "job_size": 5,
                                "duration_days": 5,
                                "traces_to": ["REQ-1"],
                                "acceptance_criteria": ["C1"],
                            },
                            {
                                "id": "STORY-2",
                                "title": "Story 2",
                                "description": "Desc",
                                "priority_components": {"user_business_value": 3, "time_criticality": 3, "risk_reduction": 3},
                                "job_size": 8,
                                "traces_to": ["REQ-1"],
                                "acceptance_criteria": ["C2"],
                                "dependencies": ["UNKNOWN-ID-999"],  # Test stripping unknown dep
                            },
                        ]
                    }
                ]
            }
        ]
    }
    msg = save_portfolio_backlog(backlog)
    assert "SUCCESS" in msg
    assert backlog["epics"][0]["features"][0]["child_job_size_sum"] == 13
    assert backlog["epics"][0]["features"][0]["child_duration_days_sum"] == 13
    assert backlog["epics"][0]["child_job_size_sum"] == 13
    assert backlog["total_job_size"] == 13
    # Verify unresolvable ID was stripped safely without crashing
    assert backlog["epics"][0]["features"][0]["stories"][1]["dependencies"] == []


def test_calculate_story_resources_with_available_roles_consulting():
    from process_toolkit.portfolio_backlog.portfolio_backlog import calculate_story_resources
    consulting_roles = [
        "Programme Delivery Manager",
        "Lead Business Analyst",
        "Solution Architect",
        "Business Analyst",
    ]
    # Requirements story -> should pick Lead Business Analyst as primary
    ba_story = {
        "title": "Stakeholder Discovery and Requirements Elicitation",
        "description": "Conduct interviews and draft requirements catalogue.",
        "acceptance_criteria": ["Requirements signed off"],
    }
    res = calculate_story_resources(ba_story, available_roles=consulting_roles)
    allocated_names = [r["name"] for r in res]
    assert all(name in consulting_roles for name in allocated_names)
    assert res[0]["name"] == "Lead Business Analyst"
    assert sum(r["allocation_percent"] for r in res) == 100.0

    # Architecture story -> should pick Solution Architect as primary
    arch_story = {
        "title": "Current State Architecture Assessment & Target Topology",
        "description": "Evaluate high level design standards and topology.",
        "acceptance_criteria": ["HLD approved"],
    }
    res_arch = calculate_story_resources(arch_story, available_roles=consulting_roles)
    assert res_arch[0]["name"] == "Solution Architect"
    assert sum(r["allocation_percent"] for r in res_arch) == 100.0

    # Governance story -> should pick Programme Delivery Manager as primary
    gov_story = {
        "title": "Programme Mobilisation and Steering Cadence Setup",
        "description": "Establish governance reporting and risk logs.",
        "acceptance_criteria": ["Steering pack approved"],
    }
    res_gov = calculate_story_resources(gov_story, available_roles=consulting_roles)
    assert res_gov[0]["name"] == "Programme Delivery Manager"
    assert sum(r["allocation_percent"] for r in res_gov) == 100.0


def test_get_role_benchmark_domain_coverage():
    from process_toolkit.portfolio_backlog.portfolio_backlog import get_role_benchmark
    # Exact known roles
    rate, _ = get_role_benchmark("Software Engineer")
    assert rate == 1275.0
    rate, _ = get_role_benchmark("Solution Architect")
    assert rate == 1500.0
    rate, _ = get_role_benchmark("Programme Delivery Manager")
    assert rate == 1300.0

    # Inferred domain roles
    rate, basis = get_role_benchmark("Managing Director")
    assert rate >= 1500.0
    rate, basis = get_role_benchmark("Senior Management Consultant")
    assert rate >= 1100.0
    rate, basis = get_role_benchmark("Cloud Platform SRE")
    assert rate >= 1200.0
    rate, basis = get_role_benchmark("Cyber Security Specialist")
    assert rate >= 1350.0
    rate, basis = get_role_benchmark("Unknown Bespoke Title")
    assert rate == 1200.0


def test_custom_scenario_with_prompt_roles_and_rates(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    backlog = {
        "name": "Custom Consulting Engagement",
        "summary": "Engagement Summary",
        "source_name": "Consulting SOW",
        "source_artifact": "design",
        "roles": [
            {"name": "Engagement Lead", "allocation_percent": 25.0},
            {"name": "Senior Consultant", "allocation_percent": 50.0},
            {"name": "Financial Analyst", "allocation_percent": 25.0},
        ],
        "rate_card": [
            {"person": "Alice", "role": "Engagement Lead", "effort_mix": 0.25, "daily_rate": 1600.0, "basis": "Engagement partner rate."},
            {"person": "Bob", "role": "Senior Consultant", "effort_mix": 0.50, "daily_rate": 1200.0, "basis": "Advisory lead rate."},
            {"person": "Charlie", "role": "Financial Analyst", "effort_mix": 0.25, "daily_rate": 1100.0, "basis": "Financial modeling rate."},
        ],
        "epics": [
            {
                "id": "EPIC-001",
                "title": "Phase 1: Financial & Commercial Due Diligence",
                "description": "Analyze commercial options and build financial model.",
                "priority_components": {"user_business_value": 5, "time_criticality": 5, "risk_reduction": 3},
                "job_size": 5,
                "traces_to": ["REQ-1"],
                "features": [
                    {
                        "id": "FEAT-001",
                        "title": "Financial Modeling Stream",
                        "description": "Construct 5-year TCO and ROI projections.",
                        "priority_components": {"user_business_value": 5, "time_criticality": 5, "risk_reduction": 3},
                        "job_size": 5,
                        "traces_to": ["REQ-1"],
                        "stories": [
                            {
                                "id": "STORY-001",
                                "title": "Build Baseline Cost Model",
                                "description": "Gather current commercial spend and build Excel model.",
                                "priority_components": {"user_business_value": 5, "time_criticality": 5, "risk_reduction": 3},
                                "job_size": 3,
                                "duration_days": 3,
                                "traces_to": ["REQ-1"],
                                "acceptance_criteria": ["Model balances"],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    msg = save_portfolio_backlog(backlog)
    assert "SUCCESS" in msg
    # Verify story resources were drawn from the consulting team roles, not software engineer
    story = backlog["epics"][0]["features"][0]["stories"][0]
    assigned_roles = [r["name"] for r in story["resources"]]
    assert all(r in ["Engagement Lead", "Senior Consultant", "Financial Analyst"] for r in assigned_roles)
    assert "Software Engineer" not in assigned_roles
    # Verify rate_card preserved custom rates
    assert backlog["rate_card"][0]["daily_rate"] == 1600.0


def test_currency_and_capacity_reconciliation(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUTPUT_DIR", str(tmp_path))
    backlog = {
        "name": "ITSM Discovery Engagement",
        "summary": "12-week ITSM discovery and options assessment.",
        "source_name": "ITSM Discovery Assessment",
        "source_artifact": "requirements_summary",
        "timescale_weeks": 12,
        "holiday_calendar": "uk",
        "resources": [
            {"name": "Programme Delivery Manager", "allocation_percent": 50},
            {"name": "Lead Business Analyst", "allocation_percent": 100},
            {"name": "Business Analyst", "allocation_percent": 100},
            {"name": "Solution Architect", "allocation_percent": 50},
        ],
        "epics": [
            {
                "id": "EPIC-001",
                "title": "Mobilisation & Current State",
                "description": "Assess current ITSM capabilities and processes.",
                "priority_components": {"user_business_value": 13, "time_criticality": 8, "risk_reduction": 5},
                "job_size": 13,
                "traces_to": ["REQ-001"],
                "features": [
                    {
                        "id": "FEAT-001",
                        "title": "Current State Assessment",
                        "description": "Baseline tooling and process maturity.",
                        "priority_components": {"user_business_value": 8, "time_criticality": 5, "risk_reduction": 3},
                        "job_size": 8,
                        "traces_to": ["REQ-001"],
                        "stories": [
                            {
                                "id": "STORY-001",
                                "title": "Audit Tooling & Integrations",
                                "description": "Review ITSM tool ecosystem.",
                                "priority_components": {"user_business_value": 5, "time_criticality": 3, "risk_reduction": 2},
                                "job_size": 5,
                                "duration_days": 4,
                                "traces_to": ["REQ-001"],
                                "acceptance_criteria": ["Inventory complete"],
                                "resources": [
                                    {"name": "Lead Business Analyst", "allocation_percent": 100},
                                    {"name": "Solution Architect", "allocation_percent": 50},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    msg = save_portfolio_backlog(backlog)
    assert "SUCCESS" in msg
    assert backlog["currency"] == "GBP"
    assert backlog["currency_symbol"] == "£"

    story = backlog["epics"][0]["features"][0]["stories"][0]
    # 4 days duration * (1.0 + 0.5 FTE) = 6.0 person-days effort
    assert story["effort_person_days"] == 6.0
    assert story["effort_hours"] == 48.0

    # Backlog capacity metrics
    assert backlog["total_duration_days"] == 4
    assert backlog["total_effort_person_days"] == 6.0
    assert backlog["schedule_duration_working_days"] == 60  # 12 weeks * 5 days
    assert backlog["team_fte"] == 3.0  # 0.5 + 1.0 + 1.0 + 0.5
    assert backlog["total_capacity_person_days"] == 180.0  # 60 * 3.0
    assert backlog["capacity_utilization_percent"] == 3.3  # round(6.0 / 180.0 * 100, 1)
    assert "governance, cadence meetings, review cycles" in backlog["capacity_notes"]

    # Verify Excel workbook currency and headers
    wb_path = os.path.join(str(tmp_path), PORTFOLIO_BACKLOG_WORKBOOK_FILENAME)
    wb = load_workbook(wb_path, data_only=False)

    assumptions = wb["Assumptions"]
    assert assumptions["B4"].value == "GBP"
    assert "GBP" in assumptions["C4"].value

    role_rates = wb["Role Rates"]
    assert role_rates["D4"].value == "Daily Rate (GBP)"
    assert role_rates["E4"].value == "Weighted Rate Contribution (GBP/day)"

    backlog_sheet = wb["Enterprise Agile Backlog"]
    assert backlog_sheet["Q5"].value == "Cost Estimate (GBP)"


def test_save_accepts_inquiry_specification_source_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    backlog = _sample_backlog()
    backlog["source_artifact"] = "Inquiry Specification"
    res = save_portfolio_backlog(backlog)
    assert res.startswith("SUCCESS:")
    assert backlog["source_artifact"] == "Inquiry Specification"


def test_save_coerces_non_fibonacci_priority_components(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    backlog = _sample_backlog()
    # 4 is not in Fibonacci; should clamp to 3 or 5
    backlog["epics"][0]["priority_components"]["user_business_value"] = 4
    # float and string values should be coerced cleanly
    backlog["epics"][0]["priority_components"]["time_criticality"] = "5"
    backlog["epics"][0]["priority_components"]["risk_reduction"] = 8.0
    res = save_portfolio_backlog(backlog)
    assert res.startswith("SUCCESS:")
    assert backlog["epics"][0]["priority_components"]["user_business_value"] in (3, 5)
    assert backlog["epics"][0]["priority_components"]["time_criticality"] == 5
    assert backlog["epics"][0]["priority_components"]["risk_reduction"] == 8


def test_save_handles_missing_priority_components(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    backlog = _sample_backlog()
    del backlog["epics"][0]["priority_components"]
    res = save_portfolio_backlog(backlog)
    assert res.startswith("SUCCESS:")
    assert "priority_components" in backlog["epics"][0]
    assert backlog["epics"][0]["priority_components"]["user_business_value"] == 3


def test_save_handles_string_roles_and_string_resources(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "output_path", lambda name: str(tmp_path / name))
    backlog = _sample_backlog()
    backlog["timescale_weeks"] = 12
    backlog["roles"] = ["PDM", "Lead BA", "BA", "SA"]
    backlog["epics"][0]["features"][0]["stories"][0]["resources"] = ["Lead BA", "BA"]
    res = save_portfolio_backlog(backlog)
    assert res.startswith("SUCCESS:")
    assert backlog["team_fte"] == 4.0
    assert backlog["total_capacity_person_days"] == 240.0






