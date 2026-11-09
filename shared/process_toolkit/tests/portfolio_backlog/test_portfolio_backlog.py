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
    sheet = workbook["Portfolio Backlog & WSJF"]
    assert workbook.sheetnames == [
        "Portfolio Backlog & WSJF",
        "SAFe 4.5 WSJF Guide",
        "Assumptions",
    ]
    assert sheet["A5"].value == "Work Item ID"
    assert sheet["L6"].value == "Epic"
    assert sheet["L7"].value == "Feature"
    assert sheet["M7"].value == "EPIC-001"
    assert sheet["L8"].value == "Story"
    assert sheet["M8"].value == "FEAT-001"
    assert sheet["N8"].value == "FR-001"
    assert sheet["P8"].value.startswith("- A vendor can save")
    assert sheet["H8"].value == "=SUM(E8:G8)"
    assert sheet["J8"].value == "=IFERROR(H8/I8,0)"
    assert sheet["K8"].value.startswith("=1+COUNTIFS(")
    assert sheet["Q8"].value == "=I8*'Assumptions'!$B$5*'Assumptions'!$B$6*(1+'Assumptions'!$B$7)"
    assert sheet["Q7"].value == "=SUMIF($M$6:$M$8,A7,$Q$6:$Q$8)"
    assert sheet["Q6"].value == "=SUMIF($M$6:$M$8,A6,$Q$6:$Q$8)"
    assert sheet["Q9"].value.startswith('=SUMIF($L$6:$L$8,"Epic"')

    assumptions = workbook["Assumptions"]
    assert assumptions["B4"].value == "USD"
    assert assumptions["B5"].value == 1200
    assert assumptions["B6"].value == 1.5
    assert assumptions["B7"].value == 0.2
    assert "not a quote" in assumptions["B10"].value


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
    sheet = workbook["Portfolio Backlog & WSJF"]
    assert sheet["A17"].value == "STORY-004"
    assert sheet["K17"].value.endswith("$J$17,\">\"&J17)")
    assert sheet["Q18"].value == '=SUMIF($L$6:$L$17,"Epic",$Q$6:$Q$17)'
