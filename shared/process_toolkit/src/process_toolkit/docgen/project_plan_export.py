"""On-demand Microsoft Project / ProjectLibre interchange-format (MSPDI XML,
`<Project xmlns="http://schemas.microsoft.com/project">`) export for the
Portfolio Backlog and Proposal Response artifacts ONLY -- no other domain in
this codebase gets a project plan. Deliberately NOT wired into either
pipeline's own generate/review loop -- same "explicit, standalone, on-demand
action" shape as vsdx_export.py's own process/design/cloudarch Visio export.

Neither source schema (portfolio_backlog.json / proposal_response.json) has
any date/duration field -- deliberate, matching the "enforced by absence"
anti-fabrication discipline used everywhere else in this codebase. A real
schedule needs durations, so this module computes ILLUSTRATIVE, clearly
labeled durations at render time only (never written back into either saved
JSON): Portfolio Backlog converts each story's `job_size` (Fibonacci points)
into a working-day duration via DEFAULT_WORKING_DAYS_PER_POINT, the same
"editable, explicitly-illustrative" discipline portfolio_backlog.py's own
cost-per-point assumption already uses; Proposal Response best-effort parses
each implementation_plan phase's own free-text `timing` field, falling back
to a nominal default when unparseable -- the original `timing` text is
ALWAYS preserved verbatim in the task's own Notes either way, so nothing is
ever silently dropped or misrepresented.

The MSPDI tree is hand-rolled via xml.etree.ElementTree -- no proprietary
binary (.mpp / ProjectLibre's own .pod) dependency, same "write the open
interchange format by hand" discipline already used for drawio XML
elsewhere in this codebase. Both Microsoft Project and ProjectLibre can
import/export this format directly.
"""

import datetime as _dt
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from process_toolkit import paths
from process_toolkit.portfolio_backlog.portfolio_backlog import load_portfolio_backlog
from process_toolkit.proposal_response.proposal_response import load_proposal_response

PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME = "portfolio_backlog_project_plan.xml"
PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME = "proposal_response_project_plan.xml"

# Illustrative planning assumption, NOT written into the saved backlog JSON --
# mirrors portfolio_backlog.py's own "editable, explicitly illustrative"
# cost-per-point discipline, applied to duration instead of cost.
DEFAULT_WORKING_DAYS_PER_POINT = 1.0

# Nominal fallback when a Proposal Response phase's own free-text "timing"
# field can't be confidently parsed (see _parse_timing_to_days below). The
# original text is always preserved verbatim in the task's Notes regardless.
_DEFAULT_PHASE_DURATION_DAYS = 10  # 2 working weeks

_WORK_START_HOUR = 8
_WORK_END_HOUR = 16
_WORK_HOURS_PER_DAY = _WORK_END_HOUR - _WORK_START_HOUR  # 8, matches the single-block
# Standard calendar declared below (08:00-16:00, no lunch-break split) -- kept
# deliberately simple so a tool re-deriving Start/Finish from Duration +
# Predecessors + this same Calendar on open recomputes the IDENTICAL dates
# this module already wrote, rather than silently drifting from them.

_MSPDI_NS = "http://schemas.microsoft.com/project"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def portfolio_backlog_project_plan_exists() -> bool:
    return os.path.isfile(paths.output_path(PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME))


def proposal_response_project_plan_exists() -> bool:
    return os.path.isfile(paths.output_path(PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME))


# ---------------------------------------------------------------------------
# Working-day calendar arithmetic
# ---------------------------------------------------------------------------

def _is_working_day(day: _dt.date) -> bool:
    return day.weekday() < 5  # Monday=0 .. Sunday=6


def _first_working_day_on_or_after(day: _dt.date) -> _dt.date:
    while not _is_working_day(day):
        day += _dt.timedelta(days=1)
    return day


def _next_working_day(day: _dt.date) -> _dt.date:
    nxt = day + _dt.timedelta(days=1)
    return _first_working_day_on_or_after(nxt)


def _advance_working_days(start: _dt.date, duration_days: int) -> _dt.date:
    """Returns the date of the last working day in a span of `duration_days`
    consecutive working days starting at `start` (which must itself already
    be a working day)."""
    current = start
    remaining = max(duration_days, 1) - 1
    while remaining > 0:
        current = _next_working_day(current)
        remaining -= 1
    return current


def _count_working_days(start: _dt.date, finish: _dt.date) -> int:
    """Inclusive count of working days between two dates -- used for a
    summary task's own displayed Duration, so it reflects actual working
    time spanned rather than raw calendar days (which would overstate it
    whenever the span crosses a weekend)."""
    if finish < start:
        return 1
    count = 0
    current = start
    while current <= finish:
        if _is_working_day(current):
            count += 1
        current += _dt.timedelta(days=1)
    return max(count, 1)


# ---------------------------------------------------------------------------
# Internal task model
# ---------------------------------------------------------------------------

class _Task:
    def __init__(self, uid: int, name: str, outline_level: int, is_summary: bool, notes: str = ""):
        self.uid = uid
        self.name = name
        self.outline_level = outline_level
        self.is_summary = is_summary
        self.notes = notes
        self.duration_days: int = 0  # leaf tasks only; summary tasks derive their own span
        self.start: Optional[_dt.date] = None
        self.finish: Optional[_dt.date] = None
        self.predecessor_uid: Optional[int] = None
        self.children: List["_Task"] = []


def _schedule_sequential_leaf(task: "_Task", anchor_start: _dt.date) -> _dt.date:
    """Schedules one leaf task starting at anchor_start, returns its finish date."""
    task.start = anchor_start
    task.finish = _advance_working_days(anchor_start, max(task.duration_days, 1))
    return task.finish


def _schedule_tree(tasks: List["_Task"], project_start: _dt.date) -> None:
    """Schedules a flat, already-ordered top-level task list (each possibly
    a summary task with its own nested children) sequentially,
    Finish-to-Start, with zero lag -- the only dependency information this
    module has (no real predecessor data exists in either source schema).
    Mutates every task's .start/.finish in place, including summary tasks
    (set to their own first/last child's span)."""
    cursor = _first_working_day_on_or_after(project_start)
    previous_uid: Optional[int] = None
    for task in tasks:
        if previous_uid is not None:
            task.predecessor_uid = previous_uid
        finish = _schedule_subtree(task, cursor)
        cursor = _next_working_day(finish)
        previous_uid = task.uid


def _schedule_subtree(task: "_Task", anchor_start: _dt.date) -> _dt.date:
    if not task.children:
        return _schedule_sequential_leaf(task, anchor_start)

    task.start = anchor_start
    cursor = anchor_start
    previous_uid: Optional[int] = None
    for i, child in enumerate(task.children):
        if i > 0:
            child.predecessor_uid = previous_uid
        finish = _schedule_subtree(child, cursor)
        cursor = _next_working_day(finish)
        previous_uid = child.uid
    task.finish = task.children[-1].finish or task.start
    return task.finish


def _flatten(tasks: List["_Task"]) -> List["_Task"]:
    flat: List["_Task"] = []
    for task in tasks:
        flat.append(task)
        flat.extend(_flatten(task.children))
    return flat


# ---------------------------------------------------------------------------
# MSPDI XML rendering
# ---------------------------------------------------------------------------

def _wbs_numbers(tasks: List["_Task"], prefix: str = "") -> Dict[int, str]:
    numbers: Dict[int, str] = {}
    for index, task in enumerate(tasks, start=1):
        wbs = f"{prefix}{index}" if not prefix else f"{prefix}.{index}"
        numbers[task.uid] = wbs
        numbers.update(_wbs_numbers(task.children, wbs))
    return numbers


def _duration_xml(days: int) -> str:
    hours = max(days, 1) * _WORK_HOURS_PER_DAY
    return f"PT{hours}H0M0S"


def _date_xml(day: _dt.date, hour: int) -> str:
    return _dt.datetime.combine(day, _dt.time(hour, 0, 0)).strftime(_DATE_FORMAT)


def _render_mspdi(project_name: str, top_level_tasks: List["_Task"], project_start: _dt.date) -> str:
    ET.register_namespace("", _MSPDI_NS)
    root = ET.Element(f"{{{_MSPDI_NS}}}Project")

    all_tasks = _flatten(top_level_tasks)
    overall_finish = max((t.finish for t in all_tasks if t.finish), default=project_start)

    ET.SubElement(root, "SaveVersion").text = "1"
    ET.SubElement(root, "Name").text = project_name
    ET.SubElement(root, "Title").text = project_name
    creation = _dt.datetime.now().strftime(_DATE_FORMAT)
    ET.SubElement(root, "CreationDate").text = creation
    ET.SubElement(root, "StartDate").text = _date_xml(project_start, _WORK_START_HOUR)
    ET.SubElement(root, "FinishDate").text = _date_xml(overall_finish, _WORK_END_HOUR)
    ET.SubElement(root, "CalendarUID").text = "1"
    ET.SubElement(root, "DefaultStartTime").text = f"{_WORK_START_HOUR:02d}:00:00"
    ET.SubElement(root, "DefaultFinishTime").text = f"{_WORK_END_HOUR:02d}:00:00"
    ET.SubElement(root, "MinutesPerDay").text = str(_WORK_HOURS_PER_DAY * 60)
    ET.SubElement(root, "MinutesPerWeek").text = str(_WORK_HOURS_PER_DAY * 60 * 5)
    ET.SubElement(root, "DaysPerMonth").text = "20"
    ET.SubElement(root, "DefaultTaskType").text = "0"

    calendars = ET.SubElement(root, "Calendars")
    calendar = ET.SubElement(calendars, "Calendar")
    ET.SubElement(calendar, "UID").text = "1"
    ET.SubElement(calendar, "Name").text = "Standard"
    ET.SubElement(calendar, "IsBaseCalendar").text = "1"
    weekdays = ET.SubElement(calendar, "WeekDays")
    for day_type in range(1, 8):  # 1=Sunday .. 7=Saturday, MSPDI convention
        weekday = ET.SubElement(weekdays, "WeekDay")
        ET.SubElement(weekday, "DayType").text = str(day_type)
        is_working = day_type not in (1, 7)
        ET.SubElement(weekday, "DayWorking").text = "1" if is_working else "0"
        if is_working:
            times = ET.SubElement(weekday, "WorkingTimes")
            working_time = ET.SubElement(times, "WorkingTime")
            ET.SubElement(working_time, "FromTime").text = f"{_WORK_START_HOUR:02d}:00:00"
            ET.SubElement(working_time, "ToTime").text = f"{_WORK_END_HOUR:02d}:00:00"

    wbs_by_uid = _wbs_numbers(top_level_tasks)
    tasks_el = ET.SubElement(root, "Tasks")
    for order, task in enumerate(all_tasks, start=1):
        task_el = ET.SubElement(tasks_el, "Task")
        ET.SubElement(task_el, "UID").text = str(task.uid)
        ET.SubElement(task_el, "ID").text = str(order)
        ET.SubElement(task_el, "Name").text = task.name
        ET.SubElement(task_el, "OutlineLevel").text = str(task.outline_level)
        ET.SubElement(task_el, "WBS").text = wbs_by_uid.get(task.uid, str(order))
        ET.SubElement(task_el, "Priority").text = "500"
        ET.SubElement(task_el, "Summary").text = "1" if task.is_summary else "0"
        ET.SubElement(task_el, "Milestone").text = "0"
        if task.start:
            ET.SubElement(task_el, "Start").text = _date_xml(task.start, _WORK_START_HOUR)
        if task.finish:
            ET.SubElement(task_el, "Finish").text = _date_xml(task.finish, _WORK_END_HOUR)
        duration_days = (
            task.duration_days if not task.children
            else _count_working_days(task.start, task.finish) if task.start and task.finish
            else 1
        )
        ET.SubElement(task_el, "Duration").text = _duration_xml(duration_days)
        ET.SubElement(task_el, "DurationFormat").text = "7"  # 7 = days, display hint only
        if task.notes:
            ET.SubElement(task_el, "Notes").text = task.notes
        if task.predecessor_uid is not None:
            pred = ET.SubElement(task_el, "PredecessorLink")
            ET.SubElement(pred, "PredecessorUID").text = str(task.predecessor_uid)
            ET.SubElement(pred, "Type").text = "1"  # Finish-to-Start
            ET.SubElement(pred, "CrossProject").text = "0"
            ET.SubElement(pred, "LinkLag").text = "0"
            ET.SubElement(pred, "LagFormat").text = "7"

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def _parse_start_date(start_date: Optional[str]) -> _dt.date:
    if start_date:
        try:
            return _dt.date.fromisoformat(start_date)
        except ValueError:
            pass
    return _dt.date.today()


def _write_output(xml_text: str, filename: str) -> str:
    out_path = paths.output_path(filename)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as file:
        file.write(xml_text)
    return out_path


# ---------------------------------------------------------------------------
# Portfolio Backlog
# ---------------------------------------------------------------------------

_BACKLOG_DISCLOSURE = (
    "Illustrative delivery schedule: {days_per_point:g} working day(s) per story point "
    "(job_size), sequenced strictly in epic -> feature -> story order. This is a planning "
    "estimate, not a committed schedule -- durations and sequencing must be validated and "
    "adjusted by the delivery team before being treated as a commitment."
)


def build_portfolio_backlog_project_plan(start_date: Optional[str] = None) -> str:
    """Exports the current saved Enterprise Agile Portfolio Backlog as an
    MSPDI project plan. Same "ERROR: ..."/"<thing> export failed: ..." string
    convention as vsdx_export.py's own build_* functions -- never raises to
    the caller."""
    backlog = load_portfolio_backlog()
    if backlog.get("status") != "OK" or not backlog.get("epics"):
        return "ERROR: No saved portfolio backlog found. Create one first."

    uid_counter = [0]

    def next_uid() -> int:
        uid_counter[0] += 1
        return uid_counter[0]

    root = _Task(
        uid=next_uid(),
        name=backlog.get("name") or "Portfolio Backlog",
        outline_level=1,
        is_summary=True,
        notes=_BACKLOG_DISCLOSURE.format(days_per_point=DEFAULT_WORKING_DAYS_PER_POINT),
    )
    for epic in backlog.get("epics") or []:
        epic_task = _Task(
            uid=next_uid(), name=epic.get("title") or epic.get("id") or "Epic",
            outline_level=2, is_summary=True,
        )
        for feature in epic.get("features") or []:
            feature_task = _Task(
                uid=next_uid(), name=feature.get("title") or feature.get("id") or "Feature",
                outline_level=3, is_summary=True,
            )
            for story in feature.get("stories") or []:
                job_size = story.get("job_size")
                try:
                    points = float(job_size)
                except (TypeError, ValueError):
                    points = 1.0
                duration_days = max(1, round(points * DEFAULT_WORKING_DAYS_PER_POINT))
                story_task = _Task(
                    uid=next_uid(), name=story.get("title") or story.get("id") or "Story",
                    outline_level=4, is_summary=False,
                    notes=f"job_size={job_size!r}; illustrative duration only.",
                )
                story_task.duration_days = duration_days
                feature_task.children.append(story_task)
            if not feature_task.children:
                feature_task.children.append(
                    _Task(uid=next_uid(), name="(no stories)", outline_level=4, is_summary=False)
                )
                feature_task.children[-1].duration_days = 1
            epic_task.children.append(feature_task)
        if not epic_task.children:
            epic_task.children.append(
                _Task(uid=next_uid(), name="(no features)", outline_level=3, is_summary=True)
            )
            epic_task.children[-1].children.append(
                _Task(uid=next_uid(), name="(no stories)", outline_level=4, is_summary=False)
            )
            epic_task.children[-1].children[-1].duration_days = 1
        root.children.append(epic_task)

    _schedule_subtree(root, _first_working_day_on_or_after(_parse_start_date(start_date)))

    xml_text = _render_mspdi(root.name, [root], root.start or _parse_start_date(start_date))
    try:
        out_path = _write_output(xml_text, PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)
    except OSError as e:
        return f"Project plan export failed: {e}"
    return f"Project plan successfully exported to {out_path}"


# ---------------------------------------------------------------------------
# Proposal Response
# ---------------------------------------------------------------------------

_WEEK_RANGE_RE = re.compile(r"weeks?\s*(\d+)\s*[-to]+\s*(\d+)", re.IGNORECASE)
_WEEK_SINGLE_RE = re.compile(r"weeks?\s*(\d+)(?!\s*[-to])", re.IGNORECASE)
_N_WEEKS_RE = re.compile(r"(\d+)\s*weeks?", re.IGNORECASE)
_N_MONTHS_RE = re.compile(r"(\d+)\s*months?", re.IGNORECASE)
_N_DAYS_RE = re.compile(r"(\d+)\s*days?", re.IGNORECASE)

_WORKING_DAYS_PER_WEEK = 5
_WORKING_DAYS_PER_MONTH = 20


def _parse_timing_to_days(timing: str) -> int:
    """Best-effort parse of a free-text `timing` field (e.g. "Weeks 1-4",
    "Month 2", "2 weeks", "10 days") into a working-day duration. Falls back
    to _DEFAULT_PHASE_DURATION_DAYS when unparseable -- the original text is
    ALWAYS preserved verbatim in the task's own Notes by the caller
    regardless of which branch (or the fallback) fires here, so nothing is
    ever silently dropped or misrepresented by an approximate parse."""
    if not isinstance(timing, str) or not timing.strip():
        return _DEFAULT_PHASE_DURATION_DAYS

    match = _WEEK_RANGE_RE.search(timing)
    if match:
        start_week, end_week = int(match.group(1)), int(match.group(2))
        span_weeks = max(1, end_week - start_week + 1)
        return span_weeks * _WORKING_DAYS_PER_WEEK

    if _WEEK_SINGLE_RE.search(timing):
        return _WORKING_DAYS_PER_WEEK

    match = _N_WEEKS_RE.search(timing)
    if match:
        return max(1, int(match.group(1))) * _WORKING_DAYS_PER_WEEK

    match = _N_MONTHS_RE.search(timing)
    if match:
        return max(1, int(match.group(1))) * _WORKING_DAYS_PER_MONTH

    match = _N_DAYS_RE.search(timing)
    if match:
        return max(1, int(match.group(1)))

    return _DEFAULT_PHASE_DURATION_DAYS


def build_proposal_response_project_plan(start_date: Optional[str] = None) -> str:
    """Exports the current saved proposal response's implementation_plan as
    an MSPDI project plan. Same string-return convention as
    build_portfolio_backlog_project_plan above."""
    response = load_proposal_response()
    if response.get("status") != "OK" or not response.get("implementation_plan"):
        return "ERROR: No saved proposal response found. Create one first."

    uid_counter = [0]

    def next_uid() -> int:
        uid_counter[0] += 1
        return uid_counter[0]

    root = _Task(
        uid=next_uid(), name=response.get("name") or "Proposal Response",
        outline_level=1, is_summary=True,
        notes=(
            "Illustrative delivery schedule derived from this proposal's own implementation_plan "
            "phase order and free-text timing descriptions. This is a planning estimate, not a "
            "committed schedule -- durations and sequencing must be validated before being "
            "treated as a commitment."
        ),
    )
    for phase in response.get("implementation_plan") or []:
        timing_text = phase.get("timing") or ""
        notes_parts = [f"Original timing: {timing_text!r}" if timing_text else "No timing text provided."]
        if phase.get("deliverable"):
            notes_parts.append(f"Deliverable: {phase['deliverable']}")
        if phase.get("acceptance_criteria"):
            notes_parts.append(f"Acceptance criteria: {phase['acceptance_criteria']}")
        phase_task = _Task(
            uid=next_uid(), name=phase.get("phase") or "Phase",
            outline_level=2, is_summary=False,
            notes="\n".join(notes_parts),
        )
        phase_task.duration_days = _parse_timing_to_days(timing_text)
        root.children.append(phase_task)

    if not root.children:
        return "ERROR: No saved proposal response found. Create one first."

    _schedule_subtree(root, _first_working_day_on_or_after(_parse_start_date(start_date)))

    xml_text = _render_mspdi(root.name, [root], root.start or _parse_start_date(start_date))
    try:
        out_path = _write_output(xml_text, PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME)
    except OSError as e:
        return f"Project plan export failed: {e}"
    return f"Project plan successfully exported to {out_path}"
