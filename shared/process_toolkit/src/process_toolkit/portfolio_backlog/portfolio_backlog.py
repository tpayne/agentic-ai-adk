"""Persist a traceable SAFe backlog and render it from the supplied workbook template."""

import copy
import json
import os
import tempfile
from typing import Any, Dict, MutableMapping, Optional

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from process_toolkit import paths

PORTFOLIO_BACKLOG_FILENAME = "portfolio_backlog.json"
PORTFOLIO_BACKLOG_WORKBOOK_FILENAME = "portfolio_backlog.xlsx"
STATE_KEY = "portfolio_backlog"
TEMPLATE_FILENAME = "SAFe_4.5_WSJF_Portfolio_Backlog.xlsx"
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", TEMPLATE_FILENAME)
FIBONACCI_SIZES = {1, 2, 3, 5, 8, 13, 20}
StateLike = MutableMapping[str, Any]

_DATA_START_ROW = 6
_HEADERS = [
    "Work Item ID",
    "Work Item Name",
    "Strategic Theme / Portfolio",
    "State",
    "User-Business Value",
    "Time Criticality",
    "Risk Reduction / Opportunity Enablement",
    "Cost of Delay (CoD)",
    "Job Size (Duration)",
    "WSJF Score",
    "WSJF Rank",
    "Work Item Type",
    "Parent ID",
    "Source Traceability",
    "Description",
    "Acceptance Criteria",
    "Cost Estimate (USD)",
    "Cost Basis / Notes",
]


def _validate_work_item(item: Any, item_type: str, seen_ids: set[str], location: str) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"{location} must be a JSON object.")

    for field in ("id", "title", "description"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError(f"{location}.{field} must be a non-empty string.")

    if item["id"] in seen_ids:
        raise ValueError(f"Duplicate work item id: {item['id']}.")
    seen_ids.add(item["id"])

    traces_to = item.get("traces_to")
    if not isinstance(traces_to, list) or not traces_to or not all(
        isinstance(trace, str) and trace.strip() for trace in traces_to
    ):
        raise ValueError(f"{location}.traces_to must contain at least one source reference.")

    components = item.get("priority_components")
    if not isinstance(components, dict):
        raise ValueError(f"{location}.priority_components must be a JSON object.")
    for field in ("user_business_value", "time_criticality", "risk_reduction"):
        if type(components.get(field)) is not int or components[field] not in FIBONACCI_SIZES:
            raise ValueError(
                f"{location}.priority_components.{field} must be one of "
                f"{sorted(FIBONACCI_SIZES)}."
            )

    if type(item.get("job_size")) is not int or item["job_size"] not in FIBONACCI_SIZES:
        raise ValueError(f"{location}.job_size must be one of {sorted(FIBONACCI_SIZES)}.")

    if item_type == "Story":
        criteria = item.get("acceptance_criteria")
        if not isinstance(criteria, list) or not criteria or not all(
            isinstance(criterion, str) and criterion.strip() for criterion in criteria
        ):
            raise ValueError(f"{location}.acceptance_criteria must contain non-empty criteria.")


def _flatten_backlog(backlog: Dict[str, Any]) -> list[dict[str, Any]]:
    epics = backlog.get("epics")
    if not isinstance(epics, list) or not epics:
        raise ValueError("epics must be a non-empty list.")

    seen_ids: set[str] = set()
    rows = []
    for epic_index, epic in enumerate(epics, start=1):
        epic_location = f"epics[{epic_index - 1}]"
        _validate_work_item(epic, "Epic", seen_ids, epic_location)
        epic.setdefault("state", "In Analysis")
        rows.append((epic, "Epic", ""))

        features = epic.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError(f"{epic_location}.features must contain at least one feature.")
        for feature_index, feature in enumerate(features, start=1):
            feature_location = f"{epic_location}.features[{feature_index - 1}]"
            _validate_work_item(feature, "Feature", seen_ids, feature_location)
            feature.setdefault("state", "In Analysis")
            rows.append((feature, "Feature", epic["id"]))

            stories = feature.get("stories")
            if not isinstance(stories, list) or not stories:
                raise ValueError(f"{feature_location}.stories must contain at least one story.")
            for story_index, story in enumerate(stories, start=1):
                story_location = f"{feature_location}.stories[{story_index - 1}]"
                _validate_work_item(story, "Story", seen_ids, story_location)
                story.setdefault("state", "In Analysis")
                rows.append((story, "Story", feature["id"]))
    return rows


def _copy_row_style(sheet, source_row: int, target_row: int, max_column: int) -> None:
    for column in range(1, max_column + 1):
        source = sheet.cell(source_row, column)
        target = sheet.cell(target_row, column)
        if source.has_style:
            target._style = copy.copy(source._style)
        if source.number_format:
            target.number_format = source.number_format
    if source_row in sheet.row_dimensions:
        sheet.row_dimensions[target_row].height = sheet.row_dimensions[source_row].height


def _write_assumptions_sheet(workbook, backlog: Dict[str, Any]) -> None:
    if "Assumptions" in workbook.sheetnames:
        del workbook["Assumptions"]
    sheet = workbook.create_sheet("Assumptions")
    sheet.merge_cells("A1:C1")
    sheet["A1"] = "Costing Assumptions & Estimate Method"
    sheet["A1"].font = Font(bold=True, size=16, color="FFFFFF")
    sheet["A1"].fill = PatternFill("solid", fgColor="17365D")
    sheet["A1"].alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 30

    sheet.append([])
    sheet.append(["Assumption", "Editable Value", "Explanation"])
    assumptions = [
        ("Currency", "USD", "All cost estimates are illustrative planning estimates in US dollars."),
        (
            "Blended fully-loaded delivery cost per person-day",
            1200,
            "Editable default covering delivery labor; replace with the team's loaded rate.",
        ),
        (
            "Effort per story point (person-days)",
            1.5,
            "Editable conversion used only for indicative cost sizing; story points remain relative.",
        ),
        (
            "Contingency uplift",
            0.20,
            "Editable allowance applied to story-level labor estimates.",
        ),
        (
            "Story-level cost formula",
            "Job Size x effort per point x blended daily rate x (1 + contingency)",
            "Features and epics roll up child costs; their costs are not estimated a second time.",
        ),
        (
            "Estimate scope",
            "Delivery labor only",
            "Licenses, cloud consumption, taxes, travel, and other non-labor costs are excluded unless explicitly priced in the source.",
        ),
        (
            "Estimate status",
            "Illustrative, not a quote or approved budget",
            "Confirm rates, velocity, scope, and delivery constraints before using for funding decisions.",
        ),
        ("Source artifact", backlog.get("source_artifact", ""), "Exactly one saved requirements summary or design document."),
        ("Source name", backlog.get("source_name", ""), "Artifact used to ground the generated backlog."),
    ]
    for assumption in assumptions:
        sheet.append(list(assumption))

    sheet["B5"].number_format = '"$"#,##0.00'
    sheet["B6"].number_format = "0.00"
    sheet["B7"].number_format = "0%"
    for cell in sheet[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4472C4")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for row in sheet.iter_rows(min_row=4, max_row=sheet.max_row, min_col=1, max_col=3):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.column_dimensions["A"].width = 45
    sheet.column_dimensions["B"].width = 55
    sheet.column_dimensions["C"].width = 90
    sheet.freeze_panes = "A4"


def _render_workbook(backlog: Dict[str, Any], rows: list[tuple[dict[str, Any], str, str]], path: str) -> None:
    if not os.path.isfile(TEMPLATE_PATH):
        raise FileNotFoundError(f"SAFe backlog workbook template is missing: {TEMPLATE_PATH}")

    workbook = load_workbook(TEMPLATE_PATH)
    sheet = workbook["Portfolio Backlog & WSJF"]
    summary_styles = [
        copy.copy(sheet.cell(16, column)._style) for column in range(1, 12)
    ]
    if "A16:D16" in {str(merged) for merged in sheet.merged_cells.ranges}:
        sheet.unmerge_cells("A16:D16")

    for row_index in range(_DATA_START_ROW, max(sheet.max_row, _DATA_START_ROW + 10) + 1):
        for column in range(1, max(sheet.max_column, len(_HEADERS)) + 1):
            sheet.cell(row_index, column).value = None

    sheet["A4"] = "Backlog Item"
    sheet["E4"] = "Cost of Delay (CoD) Components (Fibonacci: 1, 2, 3, 5, 8, 13, 20)"
    sheet["I4"] = "Job Size"
    sheet["J4"] = "WSJF Output"
    sheet.merge_cells("L4:M4")
    sheet["L4"] = "Hierarchy"
    sheet.merge_cells("N4:P4")
    sheet["N4"] = "Traceability & Delivery"
    sheet.merge_cells("Q4:R4")
    sheet["Q4"] = "Planning Cost"
    for column in (12, 14, 17):
        sheet.cell(4, column)._style = copy.copy(sheet["J4"]._style)
    for column, header in enumerate(_HEADERS, start=1):
        sheet.cell(5, column).value = header
        if column > 11:
            sheet.cell(5, column)._style = copy.copy(sheet.cell(5, 11)._style)

    last_data_row = _DATA_START_ROW + len(rows) - 1
    for offset, (item, item_type, parent_id) in enumerate(rows):
        row_number = _DATA_START_ROW + offset
        if row_number > 15:
            _copy_row_style(sheet, _DATA_START_ROW, row_number, len(_HEADERS))

        components = item["priority_components"]
        criteria = item.get("acceptance_criteria", [])
        values = [
            item["id"],
            item["title"],
            item.get("strategic_theme", "Unspecified"),
            item.get("state", "In Analysis"),
            components["user_business_value"],
            components["time_criticality"],
            components["risk_reduction"],
            f"=SUM(E{row_number}:G{row_number})",
            item["job_size"],
            f"=IFERROR(H{row_number}/I{row_number},0)",
            f'=1+COUNTIFS($L${_DATA_START_ROW}:$L${last_data_row},L{row_number},$J${_DATA_START_ROW}:$J${last_data_row},">"&J{row_number})',
            item_type,
            parent_id,
            "; ".join(item["traces_to"]),
            item["description"],
            "\n".join(f"- {criterion}" for criterion in criteria),
            None,
            item.get("cost_notes", "Planning estimate; see editable assumptions."),
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(row_number, column).value = value
            if column >= 14:
                sheet.cell(row_number, column).alignment = Alignment(wrap_text=True, vertical="top")

        if item_type == "Story":
            sheet.cell(
                row_number,
                17,
                f"=I{row_number}*'Assumptions'!$B$5*'Assumptions'!$B$6*(1+'Assumptions'!$B$7)",
            )
        else:
            sheet.cell(
                row_number,
                17,
                f"=SUMIF($M${_DATA_START_ROW}:$M${last_data_row},A{row_number},$Q${_DATA_START_ROW}:$Q${last_data_row})",
            )
            sheet.cell(row_number, 18).value = "Roll-up of child items; no separate cost added."
        sheet.cell(row_number, 17).number_format = '"$"#,##0.00'

    summary_row = last_data_row + 1
    for column, style in enumerate(summary_styles, start=1):
        sheet.cell(summary_row, column)._style = copy.copy(style)
    sheet.merge_cells(start_row=summary_row, start_column=1, end_row=summary_row, end_column=4)
    sheet.cell(summary_row, 1).value = "Portfolio Summary / Average"
    for column in range(5, 11):
        letter = sheet.cell(5, column).column_letter
        sheet.cell(summary_row, column).value = (
            f"=AVERAGE({letter}{_DATA_START_ROW}:{letter}{last_data_row})"
        )
    sheet.cell(summary_row, 17).value = (
        f'=SUMIF($L${_DATA_START_ROW}:$L${last_data_row},"Epic",$Q${_DATA_START_ROW}:$Q${last_data_row})'
    )
    sheet.cell(summary_row, 17).number_format = '"$"#,##0.00'
    sheet.cell(summary_row, 18).value = "Portfolio total sums epics only to avoid double-counting features and stories."

    sheet.auto_filter.ref = f"A5:R{last_data_row}"
    sheet.freeze_panes = "A6"
    sheet.column_dimensions["A"].width = 16
    sheet.column_dimensions["B"].width = 34
    sheet.column_dimensions["C"].width = 27
    sheet.column_dimensions["L"].width = 15
    sheet.column_dimensions["M"].width = 16
    sheet.column_dimensions["N"].width = 32
    sheet.column_dimensions["O"].width = 55
    sheet.column_dimensions["P"].width = 55
    sheet.column_dimensions["Q"].width = 22
    sheet.column_dimensions["R"].width = 38
    for row_number in range(_DATA_START_ROW, last_data_row + 1):
        sheet.row_dimensions[row_number].height = 48

    _write_assumptions_sheet(workbook, backlog)
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    output_dir = os.path.dirname(path) or "."
    os.makedirs(output_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".portfolio_backlog_", suffix=".xlsx", dir=output_dir)
    os.close(fd)
    try:
        workbook.save(temp_path)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def save_portfolio_backlog(
    backlog: Dict[str, Any], state: Optional[StateLike] = None
) -> str:
    if not isinstance(backlog, dict):
        return "ERROR: backlog must be a JSON object."

    try:
        for field in ("name", "summary", "source_name"):
            if not isinstance(backlog.get(field), str) or not backlog[field].strip():
                raise ValueError(f"{field} must be a non-empty string.")
        if backlog.get("source_artifact") not in {"requirements_summary", "design"}:
            raise ValueError("source_artifact must be 'requirements_summary' or 'design'.")

        work_items = _flatten_backlog(backlog)
        json_path = paths.output_path(PORTFOLIO_BACKLOG_FILENAME)
        workbook_path = paths.output_path(PORTFOLIO_BACKLOG_WORKBOOK_FILENAME)
        _render_workbook(backlog, work_items, workbook_path)
        fd, temp_json_path = tempfile.mkstemp(
            prefix=".portfolio_backlog_", suffix=".json", dir=os.path.dirname(json_path) or "."
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(backlog, file, indent=2, ensure_ascii=False)
            os.replace(temp_json_path, json_path)
        finally:
            if os.path.exists(temp_json_path):
                os.remove(temp_json_path)
        if state is not None:
            state[STATE_KEY] = backlog
        return (
            f"SUCCESS: Portfolio backlog saved to {json_path}; "
            f"SAFe workbook generated at {workbook_path} "
            f"({len(work_items)} work items, {len(backlog['epics'])} epics)."
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"ERROR: Could not save portfolio backlog: {error}"


def load_portfolio_backlog(state: Optional[StateLike] = None) -> Dict[str, Any]:
    if state is not None:
        session_backlog = state.get(STATE_KEY)
        if isinstance(session_backlog, dict):
            result = dict(session_backlog)
            result.setdefault("status", "OK")
            return result

    path = paths.output_path(PORTFOLIO_BACKLOG_FILENAME)
    if not os.path.exists(path):
        return {"status": "NOT_FOUND"}
    try:
        with open(path, "r", encoding="utf-8") as file:
            backlog = json.load(file)
        if isinstance(backlog, dict):
            backlog.setdefault("status", "OK")
        return backlog
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "ERROR", "error": str(error)}
