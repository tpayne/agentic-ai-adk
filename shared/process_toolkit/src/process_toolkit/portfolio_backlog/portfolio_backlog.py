"""Persist an Enterprise Agile Portfolio Backlog and render its workbook."""

import copy
import json
import os
import tempfile
from typing import Any, Dict, MutableMapping, Optional

from openpyxl import load_workbook
from openpyxl.chart.data_source import StrRef
from openpyxl.styles import Alignment, Font, PatternFill

from process_toolkit import paths

PORTFOLIO_BACKLOG_FILENAME = "portfolio_backlog.json"
PORTFOLIO_BACKLOG_WORKBOOK_FILENAME = "portfolio_backlog.xlsx"
STATE_KEY = "portfolio_backlog"
TEMPLATE_FILENAME = "Enterprise_Agile_Portfolio_Backlog.xlsx"
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", TEMPLATE_FILENAME)
FIBONACCI_SIZES = {1, 2, 3, 5, 8, 13, 20}
StateLike = MutableMapping[str, Any]

_DATA_START_ROW = 6
_CHART_DATA_START_ROW = 2
_CHART_CATEGORY_COLUMN = 20
_CHART_VALUE_COLUMN = 21
_DATA_ROW_FILL = PatternFill("solid", fgColor="FFFFFF")
ROLE_PRODUCT_OWNER = "Product Owner"
ROLE_BUSINESS_ANALYST = "Business Analyst"
ROLE_SOLUTION_ARCHITECT = "Solution Architect"
ROLE_SOFTWARE_ENGINEER = "Software Engineer"
ROLE_QA_ENGINEER = "QA Engineer"
ROLE_DEVOPS_ENGINEER = "DevOps / Platform Engineer"

_ROLE_ROW_INDEX = {
    ROLE_PRODUCT_OWNER: 5,
    ROLE_BUSINESS_ANALYST: 6,
    ROLE_SOLUTION_ARCHITECT: 7,
    ROLE_SOFTWARE_ENGINEER: 8,
    ROLE_QA_ENGINEER: 9,
    ROLE_DEVOPS_ENGINEER: 10,
}

ROLE_BENCHMARK_RATES: dict[str, tuple[float, str]] = {
    ROLE_PRODUCT_OWNER: (1200.0, "Product ownership benchmark; backlog prioritization, stakeholder alignment, and acceptance."),
    ROLE_BUSINESS_ANALYST: (1000.0, "Business analysis & requirements engineering benchmark; user stories and workflow specs."),
    ROLE_SOLUTION_ARCHITECT: (1500.0, "Senior Solution Architecture benchmark; system context, governance, and technical design."),
    ROLE_SOFTWARE_ENGINEER: (1275.0, "Full-stack software engineering benchmark; feature delivery and implementation."),
    ROLE_QA_ENGINEER: (1000.0, "Quality assurance & test automation benchmark; verification, regression, and E2E."),
    ROLE_DEVOPS_ENGINEER: (1200.0, "Cloud platform & DevOps engineering benchmark; CI/CD, IaC, and observability."),
    "Programme Delivery Manager": (1300.0, "Programme delivery management and governance benchmark; delivery oversight, cadence, and reporting."),
    "Project Manager": (1200.0, "Project management and delivery coordination benchmark; tracking, risks, and issue mitigation."),
    "Lead Business Analyst": (1100.0, "Lead business analysis and requirements engineering benchmark; discovery facilitation, catalogue ownership."),
    "Enterprise Architect": (1600.0, "Enterprise architecture and strategy benchmark; target operating models and strategic alignment."),
    "Data Engineer": (1350.0, "Data engineering benchmark; ETL pipelines, data warehousing, and analytics infrastructure."),
    "Security Engineer": (1400.0, "Security & compliance engineering benchmark; threat modeling, IAM, and hardening."),
    "Scrum Master / Agile Coach": (1150.0, "Agile delivery coaching and facilitation benchmark."),
    "UI/UX Designer": (1100.0, "UI/UX design benchmark; wireframes, user journeys, and design systems."),
}

_ROLE_COSTING_DEFAULTS = [
    ("TBD", ROLE_PRODUCT_OWNER, 0.10, 1200, "Illustrative default; replace with the approved rate card."),
    ("TBD", ROLE_BUSINESS_ANALYST, 0.15, 1000, "Illustrative default; replace with the approved rate card."),
    ("TBD", ROLE_SOLUTION_ARCHITECT, 0.10, 1500, "Illustrative default; replace with the approved rate card."),
    ("TBD", ROLE_SOFTWARE_ENGINEER, 0.40, 1275, "Illustrative default; replace with the approved rate card."),
    ("TBD", ROLE_QA_ENGINEER, 0.15, 1000, "Illustrative default; replace with the approved rate card."),
    (
        "TBD",
        ROLE_DEVOPS_ENGINEER,
        0.10,
        1200,
        "Illustrative default; replace with the approved rate card.",
    ),
]


def build_rate_card(
    backlog: Dict[str, Any],
    work_items: Optional[list[tuple[dict[str, Any], str, str]]] = None,
) -> list[dict[str, Any]]:
    """Builds, projects, or normalizes an illustrative rate card with sensible market-grounded
    estimations for resource daily rates and bases.
    If backlog contains an explicit `rate_card` or `roles`, its rates, roles, and bases are respected
    and normalized. Missing roles used in stories are appended with sensible estimations.
    If no rate card is provided, a sensible rate card is projected based on default benchmarks
    and any specialized roles present in the backlog stories.
    """
    explicit = backlog.get("rate_card") or backlog.get("roles")
    if isinstance(explicit, list) and explicit:
        normalized = []
        seen_roles = set()
        for entry in explicit:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or entry.get("name") or "").strip()
            if not role or role in seen_roles:
                continue
            seen_roles.add(role)
            person = str(entry.get("person") or "TBD").strip()
            daily_rate = entry.get("daily_rate") or entry.get("rate")
            try:
                daily_rate = float(daily_rate)
            except (TypeError, ValueError):
                daily_rate = None
            if daily_rate is None or daily_rate <= 0:
                daily_rate = ROLE_BENCHMARK_RATES.get(role, (1200.0, ""))[0]

            basis = str(entry.get("basis") or "").strip()
            if not basis:
                basis = ROLE_BENCHMARK_RATES.get(
                    role,
                    (1200.0, f"Sensible market benchmark rate for {role}; standard 8hr daily basis.")
                )[1]

            mix = entry.get("effort_mix") or entry.get("mix") or entry.get("allocation_percent")
            try:
                mix = float(mix)
                if mix > 1.0:
                    mix = mix / 100.0
            except (TypeError, ValueError):
                mix = None
            if mix is None or mix < 0:
                mix = 0.10

            normalized.append({
                "person": person,
                "role": role,
                "effort_mix": mix,
                "daily_rate": daily_rate,
                "basis": basis,
            })

        # Check for roles in work_items/stories not covered in rate_card
        story_roles = set()
        if work_items:
            for item, item_type, _ in work_items:
                if item_type == "Story":
                    for res in item.get("resources") or []:
                        r_name = str(res.get("name") or "").strip()
                        if r_name:
                            story_roles.add(r_name)
        for r_name in sorted(story_roles):
            if r_name not in seen_roles:
                seen_roles.add(r_name)
                bench = ROLE_BENCHMARK_RATES.get(
                    r_name, (1200.0, f"Sensible market benchmark rate for {r_name}; standard 8hr daily basis.")
                )
                normalized.append({
                    "person": "TBD",
                    "role": r_name,
                    "effort_mix": 0.05,
                    "daily_rate": bench[0],
                    "basis": bench[1],
                })

        # Normalize effort_mix so total is 1.0
        tot = sum(e["effort_mix"] for e in normalized)
        if tot > 0 and abs(tot - 1.0) > 1e-4:
            for e in normalized:
                e["effort_mix"] = round(e["effort_mix"] / tot, 4)
        return normalized

    # Default market benchmark rate card
    card = [
        {
            "person": person,
            "role": role,
            "effort_mix": mix,
            "daily_rate": rate,
            "basis": basis,
        }
        for person, role, mix, rate, basis in _ROLE_COSTING_DEFAULTS
    ]
    seen_roles = {c["role"] for c in card}
    if work_items:
        for item, item_type, _ in work_items:
            if item_type == "Story":
                for res in item.get("resources") or []:
                    r_name = str(res.get("name") or "").strip()
                    if r_name and r_name not in seen_roles:
                        seen_roles.add(r_name)
                        bench = ROLE_BENCHMARK_RATES.get(
                            r_name, (1200.0, f"Sensible market benchmark rate for {r_name}; standard 8hr daily basis.")
                        )
                        card.append({
                            "person": "TBD",
                            "role": r_name,
                            "effort_mix": 0.05,
                            "daily_rate": bench[0],
                            "basis": bench[1],
                        })
        if len(card) > len(_ROLE_COSTING_DEFAULTS):
            tot = sum(c["effort_mix"] for c in card)
            if tot > 0:
                for c in card:
                    c["effort_mix"] = round(c["effort_mix"] / tot, 4)
    return card


def calculate_story_resources(story: Dict[str, Any]) -> list[dict[str, Any]]:
    """Calculates realistic role and resource allocations (percentages summing to 100%)
    based on the activity being performed in the story (analyzing title, description,
    acceptance criteria, and strategic theme), rather than assigning fixed values.
    """
    existing = story.get("resources") or story.get("roles")
    if isinstance(existing, list) and existing:
        normalized = []
        for r in existing:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or r.get("role") or "").strip()
            if not name:
                continue
            try:
                pct = float(r.get("allocation_percent", 0))
            except (TypeError, ValueError):
                continue
            if pct > 0:
                normalized.append({"name": name, "allocation_percent": pct})
        if normalized:
            total = sum(x["allocation_percent"] for x in normalized)
            if total > 0 and abs(total - 100.0) > 1e-3:
                for x in normalized:
                    x["allocation_percent"] = round((x["allocation_percent"] / total) * 100.0, 1)
            return normalized

    text_parts = [
        story.get("title", ""),
        story.get("description", ""),
        " ".join(story.get("acceptance_criteria", []) if isinstance(story.get("acceptance_criteria"), list) else []),
        story.get("strategic_theme", ""),
    ]
    text = " ".join(part for part in text_parts if isinstance(part, str)).lower()

    devops_keywords = [
        "devops", "platform", "infrastructure", "iac", "terraform", "cloudformation",
        "bicep", "ansible", "kubernetes", "k8s", "docker", "container", "helm",
        "cluster", "backup", "backups", "lockdown", "vpc", "subnet", "iam", "kms",
        "secrets", "provision", "deploy", "deployment", "pipeline", "ci/cd",
        "telemetry", "cloudwatch", "datadog", "prometheus", "grafana", "alerting",
        "sre", "firewall", "network", "ingress", "egress", "route53", "dns", "gateway",
    ]
    qa_keywords = [
        "test", "tests", "testing", "qa", "verify", "verification", "validate",
        "validation", "validator", "e2e", "cypress", "selenium", "playwright",
        "smoke", "regression", "penetration", "pentest", "performance test",
        "load test", "stress test", "audit", "compliance verification", "benchmark",
    ]
    arch_keywords = [
        "architect", "architecture", "solution design", "high-level design", "hld",
        "low-level design", "lld", "framework", "governance", "topology",
        "system context", "tradeoff", "trade-off", "standards", "evaluation",
        "evaluate", "feasibility", "conceptual", "reference architecture",
    ]
    ba_keywords = [
        "requirement", "requirements", "business analyst", "analyst", "user research",
        "interview", "stakeholder", "business process", "workflow", "gap analysis",
        "specification", "business rule", "onboarding flow", "user journey",
    ]
    po_keywords = [
        "product owner", "roadmap", "backlog refinement", "prioritization",
        "user persona", "market analysis", "vision document", "scope definition",
        "release planning", "feature prioritization",
    ]

    devops_score = sum(text.count(kw) for kw in devops_keywords)
    qa_score = sum(text.count(kw) for kw in qa_keywords)
    arch_score = sum(text.count(kw) for kw in arch_keywords)
    ba_score = sum(text.count(kw) for kw in ba_keywords)
    po_score = sum(text.count(kw) for kw in po_keywords)

    scores = [
        ("devops", devops_score),
        ("qa", qa_score),
        ("arch", arch_score),
        ("ba", ba_score),
        ("po", po_score),
    ]
    scores.sort(key=lambda s: s[1], reverse=True)
    top_cat, top_score = scores[0]

    if top_score > 0:
        if top_cat == "devops":
            return [
                {"name": ROLE_DEVOPS_ENGINEER, "allocation_percent": 60.0},
                {"name": ROLE_SOFTWARE_ENGINEER, "allocation_percent": 25.0},
                {"name": ROLE_QA_ENGINEER, "allocation_percent": 15.0},
            ]
        elif top_cat == "qa":
            return [
                {"name": ROLE_QA_ENGINEER, "allocation_percent": 60.0},
                {"name": ROLE_SOFTWARE_ENGINEER, "allocation_percent": 25.0},
                {"name": ROLE_DEVOPS_ENGINEER, "allocation_percent": 15.0},
            ]
        elif top_cat == "arch":
            return [
                {"name": ROLE_SOLUTION_ARCHITECT, "allocation_percent": 60.0},
                {"name": ROLE_SOFTWARE_ENGINEER, "allocation_percent": 20.0},
                {"name": ROLE_BUSINESS_ANALYST, "allocation_percent": 20.0},
            ]
        elif top_cat == "ba":
            return [
                {"name": ROLE_BUSINESS_ANALYST, "allocation_percent": 60.0},
                {"name": ROLE_PRODUCT_OWNER, "allocation_percent": 25.0},
                {"name": ROLE_SOLUTION_ARCHITECT, "allocation_percent": 15.0},
            ]
        elif top_cat == "po":
            return [
                {"name": ROLE_PRODUCT_OWNER, "allocation_percent": 60.0},
                {"name": ROLE_BUSINESS_ANALYST, "allocation_percent": 25.0},
                {"name": ROLE_SOLUTION_ARCHITECT, "allocation_percent": 15.0},
            ]

    return [
        {"name": ROLE_SOFTWARE_ENGINEER, "allocation_percent": 60.0},
        {"name": ROLE_QA_ENGINEER, "allocation_percent": 20.0},
        {"name": ROLE_SOLUTION_ARCHITECT, "allocation_percent": 10.0},
        {"name": ROLE_DEVOPS_ENGINEER, "allocation_percent": 10.0},
    ]
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
    "Costed Roles",
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
                story["resources"] = calculate_story_resources(story)
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


def _write_epic_chart_data(sheet, rows: list[tuple[dict[str, Any], str, str]]) -> tuple[str, str]:
    chart_row = _CHART_DATA_START_ROW
    for data_offset, (item, item_type, _) in enumerate(rows):
        if item_type != "Epic":
            continue
        data_row = _DATA_START_ROW + data_offset
        sheet.cell(chart_row, _CHART_CATEGORY_COLUMN, f"=A{data_row}")
        sheet.cell(chart_row, _CHART_VALUE_COLUMN, f"=J{data_row}")
        chart_row += 1

    sheet.column_dimensions[sheet.cell(1, _CHART_CATEGORY_COLUMN).column_letter].hidden = True
    sheet.column_dimensions[sheet.cell(1, _CHART_VALUE_COLUMN).column_letter].hidden = True
    last_chart_row = chart_row - 1
    category_range = (
        f"'{sheet.title}'!${sheet.cell(1, _CHART_CATEGORY_COLUMN).column_letter}"
        f"${_CHART_DATA_START_ROW}:${sheet.cell(1, _CHART_CATEGORY_COLUMN).column_letter}${last_chart_row}"
    )
    value_range = (
        f"'{sheet.title}'!${sheet.cell(1, _CHART_VALUE_COLUMN).column_letter}"
        f"${_CHART_DATA_START_ROW}:${sheet.cell(1, _CHART_VALUE_COLUMN).column_letter}${last_chart_row}"
    )
    return category_range, value_range


def _write_assumptions_sheet(workbook, backlog: Dict[str, Any], end_role_row: int = 10) -> None:
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
            f"=SUM('Role Rates'!E5:E{end_role_row})",
            "Weighted rate calculated from the editable people/role mix on the Role Rates tab.",
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
            "Job Size x effort per point x role-mix weighted daily rate x (1 + contingency)",
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
        (
            "User-business value weight",
            1.0,
            "Editable WSJF Cost of Delay multiplier for the score in the matching backlog column.",
        ),
        (
            "Time criticality weight",
            1.0,
            "Editable WSJF Cost of Delay multiplier for the score in the matching backlog column.",
        ),
        (
            "Risk reduction / opportunity enablement weight",
            1.0,
            "Editable WSJF Cost of Delay multiplier for the score in the matching backlog column.",
        ),
        (
            "Priority score scale",
            "Modified Fibonacci: 1, 2, 3, 5, 8, 13, 20",
            "The generator validates each component and job size against this scale.",
        ),
        (
            "Priority score basis",
            "Relative analyst judgment",
            "Scores are inputs from the generated backlog, not calculated facts or currency; reviewers should validate them.",
        ),
        (
            "Job size basis",
            "Relative size points",
            "Story points are not a direct duration measure. Cost conversion uses the editable effort-per-point assumption above.",
        ),
        (
            "Cost of Delay formula",
            "User-business value x weight + time criticality x weight + risk reduction x weight",
            "Calculated in the backlog from the three component scores and their editable weights.",
        ),
        (
            "WSJF formula",
            "Cost of Delay / job size",
            "Calculated for each work item; component scores and job size are source/agent inputs.",
        ),
        (
            "WSJF rank scope and ties",
            "Rank within work item type; ties share rank",
            "Excel competition ranking: a tie at rank 1 is followed by rank 3.",
        ),
        (
            "Default work item state",
            "In Analysis",
            "Used only when the source backlog item does not specify a state.",
        ),
        (
            "Default strategic theme",
            "Unspecified",
            "Used only when the backlog item has no strategic_theme.",
        ),
        (
            "Role mix and daily rates",
            "See Role Rates worksheet",
            "Editable role names, effort mix, and illustrative USD daily rates are maintained only on the separate Role Rates worksheet.",
        ),
    ]
    for assumption in assumptions:
        sheet.append(list(assumption))

    sheet["B5"].number_format = '"$"#,##0.00'
    sheet["B6"].number_format = "0.00"
    sheet["B7"].number_format = "0%"
    for cell in ("B13", "B14", "B15"):
        sheet[cell].number_format = "0.00"

    for cell in sheet[3][:3]:
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


def _write_role_rates_sheet(workbook, rate_card: Optional[list[dict[str, Any]]] = None) -> None:
    if "Role Rates" in workbook.sheetnames:
        del workbook["Role Rates"]
    sheet = workbook.create_sheet("Role Rates")
    sheet.merge_cells("A1:F1")
    sheet["A1"] = "Illustrative Role-Based Rate Card"
    sheet["A1"].font = Font(bold=True, size=16, color="FFFFFF")
    sheet["A1"].fill = PatternFill("solid", fgColor="17365D")
    sheet["A1"].alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 30
    sheet.merge_cells("A2:F2")
    sheet["A2"] = (
        "Replace TBD names and illustrative rates/mix with approved project inputs. "
        "Story costs use this weighted role mix."
    )
    sheet["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[2].height = 34
    role_headers = [
        "Person",
        "Delivery Role",
        "Effort Mix",
        "Daily Rate (USD)",
        "Weighted Rate Contribution (USD/day)",
        "Rate Basis",
    ]
    for column, header in enumerate(role_headers, start=1):
        cell = sheet.cell(4, column, header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4472C4")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[4].height = 32

    if rate_card is None:
        rate_card = [
            {
                "person": person,
                "role": role,
                "effort_mix": mix,
                "daily_rate": rate,
                "basis": basis,
            }
            for person, role, mix, rate, basis in _ROLE_COSTING_DEFAULTS
        ]

    start_row = 5
    end_row = start_row + len(rate_card) - 1
    for row_number, entry in enumerate(rate_card, start=start_row):
        sheet.cell(row_number, 1, entry["person"])
        sheet.cell(row_number, 2, entry["role"])
        sheet.cell(row_number, 3, entry["effort_mix"])
        sheet.cell(row_number, 4, entry["daily_rate"])
        sheet.cell(
            row_number,
            5,
            f"=IFERROR(C{row_number}/SUM($C${start_row}:$C${end_row})*D{row_number},0)",
        )
        sheet.cell(row_number, 6, entry["basis"])
        sheet.cell(row_number, 3).number_format = "0%"
        sheet.cell(row_number, 4).number_format = '"$"#,##0.00'
        sheet.cell(row_number, 5).number_format = '"$"#,##0.00'
        for cell in sheet[row_number][:6]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    total_row = end_row + 1
    sheet.cell(total_row, 1, "Total / Weighted Rate")
    sheet.cell(total_row, 3, f"=SUM(C{start_row}:C{end_row})")
    sheet.cell(total_row, 5, f"=SUM(E{start_row}:E{end_row})")
    sheet.cell(total_row, 3).number_format = "0%"
    sheet.cell(total_row, 5).number_format = '"$"#,##0.00'
    for cell in sheet[total_row][:6]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
    sheet.auto_filter.ref = f"A4:F{end_row}"
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 32
    sheet.column_dimensions["C"].width = 18
    sheet.column_dimensions["D"].width = 22
    sheet.column_dimensions["E"].width = 28
    sheet.column_dimensions["F"].width = 52
    sheet.freeze_panes = "A5"


def _render_workbook(backlog: Dict[str, Any], rows: list[tuple[dict[str, Any], str, str]], path: str) -> None:
    if not os.path.isfile(TEMPLATE_PATH):
        raise FileNotFoundError(f"Enterprise Agile Portfolio Backlog template is missing: {TEMPLATE_PATH}")

    rate_card = build_rate_card(backlog, rows)
    role_to_row = {entry["role"]: 5 + i for i, entry in enumerate(rate_card)}
    start_role_row = 5
    end_role_row = start_role_row + len(rate_card) - 1

    workbook = load_workbook(TEMPLATE_PATH)
    sheet = workbook["Enterprise Agile Backlog"]
    for row_number in range(1, 4):
        sheet.cell(row_number, 4).fill = PatternFill(fill_type=None)
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
    sheet.merge_cells("Q4:S4")
    sheet["Q4"] = "Planning Cost & Staffing"
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
        if item_type == "Story":
            story_res = item.get("resources") or calculate_story_resources(item)
            role_refs = []
            for res in story_res:
                r_name = res["name"]
                pct = res["allocation_percent"] / 100.0
                row_idx = role_to_row.get(r_name)
                if row_idx:
                    role_refs.append(f"'Role Rates'!$B${row_idx}&\" (\"&TEXT({pct:g},\"0%\")&\")\"")
                else:
                    role_refs.append(f"\"{r_name} (\"&TEXT({pct:g},\"0%\")&\")\"")
            costed_roles = "=" + '&"; "&'.join(role_refs)
        else:
            costed_roles = "Rolled up from child items; see story-level roles."
        values = [
            item["id"],
            item["title"],
            item.get("strategic_theme", "Unspecified"),
            item.get("state", "In Analysis"),
            components["user_business_value"],
            components["time_criticality"],
            components["risk_reduction"],
            (
                f"=E{row_number}*'Assumptions'!$B$13"
                f"+F{row_number}*'Assumptions'!$B$14"
                f"+G{row_number}*'Assumptions'!$B$15"
            ),
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
            costed_roles,
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(row_number, column).value = value
            if column >= 14:
                sheet.cell(row_number, column).alignment = Alignment(wrap_text=True, vertical="top")
            sheet.cell(row_number, column).fill = copy.copy(_DATA_ROW_FILL)

        state_font = copy.copy(sheet.cell(row_number, 4).font)
        state_font.color = "1F1F1F"
        sheet.cell(row_number, 4).font = state_font

        if item_type == "Story":
            story_res = item.get("resources") or calculate_story_resources(item)
            rate_terms = []
            for res in story_res:
                r_name = res["name"]
                pct = res["allocation_percent"] / 100.0
                row_idx = role_to_row.get(r_name)
                if row_idx:
                    rate_terms.append(f"{pct:g}*'Role Rates'!$D${row_idx}")
                else:
                    bench_rate = ROLE_BENCHMARK_RATES.get(r_name, (1200.0, ""))[0]
                    rate_terms.append(f"{pct:g}*{bench_rate:g}")
            default_weighted = (
                f"SUMPRODUCT('Role Rates'!$C${start_role_row}:$C${end_role_row},"
                f"'Role Rates'!$D${start_role_row}:$D${end_role_row})/"
                f"SUM('Role Rates'!$C${start_role_row}:$C${end_role_row})"
            )
            rate_formula = " + ".join(rate_terms) if rate_terms else default_weighted
            sheet.cell(
                row_number,
                17,
                f"=I{row_number}*'Assumptions'!$B$6*(1+'Assumptions'!$B$7)*({rate_formula})",
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
    sheet.cell(summary_row, 19).value = "Story costs use activity-based role allocations from the Role Rates tab."

    category_range, value_range = _write_epic_chart_data(sheet, rows)
    for chart in sheet._charts:
        chart.anchor = f"A{summary_row + 3}"
        chart.visible_cells_only = False
        for series in chart.series:
            if series.cat is not None:
                series.cat.numRef = None
                series.cat.strRef = StrRef(f=category_range)
            if series.val is not None and series.val.numRef is not None:
                series.val.numRef.f = value_range

    sheet.auto_filter.ref = f"A5:S{last_data_row}"
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
    sheet.column_dimensions["S"].width = 64
    for row_number in range(_DATA_START_ROW, last_data_row + 1):
        sheet.row_dimensions[row_number].height = 48

    _write_assumptions_sheet(workbook, backlog, end_role_row)
    _write_role_rates_sheet(workbook, rate_card)
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
        role_alloc_sums: Dict[str, float] = {}
        for item, item_type, _ in work_items:
            if item_type == "Story":
                for r in item.get("resources") or []:
                    r_name = r.get("name")
                    if r_name:
                        role_alloc_sums[r_name] = role_alloc_sums.get(r_name, 0.0) + float(r.get("allocation_percent", 0))
        total_alloc = sum(role_alloc_sums.values())
        if total_alloc > 0:
            backlog["resources"] = [
                {"name": name, "allocation_percent": round((val / total_alloc) * 100.0, 1)}
                for name, val in sorted(role_alloc_sums.items())
            ]
        backlog["rate_card"] = build_rate_card(backlog, work_items)
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
            f"SUCCESS: Enterprise Agile Portfolio Backlog saved to {json_path}; "
            f"workbook generated at {workbook_path} "
            f"({len(work_items)} work items, {len(backlog['epics'])} epics)."
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        return f"ERROR: Could not save Enterprise Agile Portfolio Backlog: {error}"


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
