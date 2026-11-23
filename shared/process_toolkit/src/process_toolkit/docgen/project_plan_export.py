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

Optionally also accepts `resources` (a named role/person + % allocation,
e.g. "Project Manager" at 50%) and `holiday_calendar` ("uk" or None) --
NEITHER exists in either source schema either, so both are supplied by the
caller at export time (typically extracted from the user's own request
wording by the calling agent), never fabricated here. Resources are
rendered as MSPDI <Resources>/<Assignments> (every resource assigned to
every leaf task, Units = allocation_percent/100, Work = task duration *
that fraction -- there is no finer-grained role-to-task mapping anywhere
in either source schema to assign more precisely than that). A UK holiday
calendar marks real UK bank holidays (fixed-date + Easter-based + nth-
weekday rules, with the standard weekend-substitution rule) as Calendar
Exceptions, so the working-day scheduler actually skips them rather than
only skipping weekends. An optional `target_duration_weeks` is a POST-HOC
check only -- if the sequenced plan overruns it, a WARNING is appended to
both the root task's Notes and the function's own returned message, never
silently compressed/clipped to force a fit.

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
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from process_toolkit import paths
from process_toolkit.portfolio_backlog.portfolio_backlog import load_portfolio_backlog
from process_toolkit.proposal_response.proposal_response import load_proposal_response
from process_toolkit.docgen.pert_cpm_export import generate_pert_cpm_diagram

PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME = "portfolio_backlog_project_plan.xml"
PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME = "proposal_response_project_plan.xml"
PORTFOLIO_BACKLOG_PERT_CPM_FILENAME = "portfolio_backlog_pert_cpm.png"
PROPOSAL_RESPONSE_PERT_CPM_FILENAME = "proposal_response_pert_cpm.png"

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
# UK bank holiday calendar (England & Wales dates -- the common default;
# Scotland/Northern Ireland observe a few different substitute days, which
# this does not attempt to model, since nothing in either source schema or
# caller wording distinguishes which nation's calendar is meant).
# ---------------------------------------------------------------------------

def _easter_sunday(year: int) -> _dt.date:
    """Anonymous Gregorian algorithm -- Good Friday/Easter Monday are both
    computed relative to this."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return _dt.date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    """The nth occurrence of `weekday` (Monday=0..Sunday=6) in `month`,
    1-based; n=-1 means the LAST occurrence in the month instead."""
    if n > 0:
        day = _dt.date(year, month, 1)
        count = 0
        while True:
            if day.weekday() == weekday:
                count += 1
                if count == n:
                    return day
            day += _dt.timedelta(days=1)
    day = (
        _dt.date(year, 12, 31) if month == 12
        else _dt.date(year, month + 1, 1) - _dt.timedelta(days=1)
    )
    while day.weekday() != weekday:
        day -= _dt.timedelta(days=1)
    return day


def _with_weekend_substitution(fixed_dates: List[_dt.date]) -> FrozenSet[_dt.date]:
    """UK rule: a fixed-date holiday that falls on a weekend gets a
    substitute weekday, normally the next Monday -- but Christmas Day and
    Boxing Day can collide (both land on a weekend in the same year), so
    each substitute must also skip any date already claimed by an earlier
    substitute in this same batch, not just the original fixed dates."""
    claimed = set(fixed_dates)
    observed = set()
    for fixed in sorted(fixed_dates):
        if fixed.weekday() < 5:
            observed.add(fixed)
            continue
        substitute = fixed + _dt.timedelta(days=1)
        while substitute.weekday() >= 5 or substitute in claimed or substitute in observed:
            substitute += _dt.timedelta(days=1)
        observed.add(substitute)
        claimed.add(substitute)
    return frozenset(observed)


def uk_bank_holidays(year: int) -> FrozenSet[_dt.date]:
    """UK (England & Wales) bank holidays actually observed in `year`:
    New Year's Day, Good Friday, Easter Monday, the early-May and Spring
    and Summer bank holidays, Christmas Day, and Boxing Day -- fixed dates
    get the standard weekend-substitution rule; the Easter-based and
    nth-weekday ones never need it (they're pinned to a weekday by
    construction)."""
    easter = _easter_sunday(year)
    movable = {
        easter - _dt.timedelta(days=2),  # Good Friday
        easter + _dt.timedelta(days=1),  # Easter Monday
        _nth_weekday(year, 5, 0, 1),  # Early May bank holiday
        _nth_weekday(year, 5, 0, -1),  # Spring bank holiday
        _nth_weekday(year, 8, 0, -1),  # Summer bank holiday
    }
    fixed_with_substitution = _with_weekend_substitution(
        [_dt.date(year, 1, 1), _dt.date(year, 12, 25), _dt.date(year, 12, 26)]
    )
    return frozenset(movable | fixed_with_substitution)


def _uk_bank_holidays_covering(start: _dt.date, years_ahead: int = 2) -> FrozenSet[_dt.date]:
    """Holidays for `start`'s own year through `years_ahead` years after it
    -- comfortably covers any plan of ordinary (a few months to ~2 years)
    length starting at `start`, without needing to know the computed finish
    date up front (which would be circular -- the finish date depends on
    which days are holidays)."""
    holidays: set = set()
    for year in range(start.year, start.year + years_ahead + 1):
        holidays |= uk_bank_holidays(year)
    return frozenset(holidays)


# ---------------------------------------------------------------------------
# Working-day calendar arithmetic
# ---------------------------------------------------------------------------

_NO_HOLIDAYS: FrozenSet[_dt.date] = frozenset()


def _is_working_day(day: _dt.date, holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS) -> bool:
    return day.weekday() < 5 and day not in holidays  # Monday=0 .. Sunday=6


def _first_working_day_on_or_after(
    day: _dt.date, holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS,
) -> _dt.date:
    while not _is_working_day(day, holidays):
        day += _dt.timedelta(days=1)
    return day


def _next_working_day(day: _dt.date, holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS) -> _dt.date:
    nxt = day + _dt.timedelta(days=1)
    return _first_working_day_on_or_after(nxt, holidays)


def _advance_working_days(
    start: _dt.date, duration_days: int, holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS,
) -> _dt.date:
    """Returns the date of the last working day in a span of `duration_days`
    consecutive working days starting at `start` (which must itself already
    be a working day)."""
    current = start
    remaining = max(duration_days, 1) - 1
    while remaining > 0:
        current = _next_working_day(current, holidays)
        remaining -= 1
    return current


def _count_working_days(
    start: _dt.date, finish: _dt.date, holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS,
) -> int:
    """Inclusive count of working days between two dates -- used for a
    summary task's own displayed Duration, so it reflects actual working
    time spanned rather than raw calendar days (which would overstate it
    whenever the span crosses a weekend or holiday)."""
    if finish < start:
        return 1
    count = 0
    current = start
    while current <= finish:
        if _is_working_day(current, holidays):
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
        self.resources: List[Tuple[str, float]] = []


def _schedule_sequential_leaf(
    task: "_Task", anchor_start: _dt.date, holidays: FrozenSet[_dt.date],
) -> _dt.date:
    """Schedules one leaf task starting at anchor_start, returns its finish date."""
    task.start = anchor_start
    task.finish = _advance_working_days(anchor_start, max(task.duration_days, 1), holidays)
    return task.finish


def _schedule_subtree(
    task: "_Task", anchor_start: _dt.date, holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS,
) -> _dt.date:
    if not task.children:
        return _schedule_sequential_leaf(task, anchor_start, holidays)

    task.start = anchor_start
    cursor = anchor_start
    previous_uid: Optional[int] = None
    for i, child in enumerate(task.children):
        if i > 0:
            child.predecessor_uid = previous_uid
        finish = _schedule_subtree(child, cursor, holidays)
        cursor = _next_working_day(finish, holidays)
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


def _normalize_resources(resources: Optional[List[Dict[str, Any]]]) -> List[tuple]:
    """Validates/normalizes the caller-supplied resources list into
    `(name, allocation_fraction)` pairs, 0 < fraction <= 1. Silently skips
    an entry with no name or a non-numeric/out-of-range percent rather than
    raising -- a malformed resource entry shouldn't abort the whole export,
    but it also never gets fabricated a default allocation; it's just
    dropped, and the caller's own instructions are what keep this rare in
    the first place."""
    normalized = []
    for entry in resources or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        try:
            percent = float(entry.get("allocation_percent"))
        except (TypeError, ValueError):
            continue
        if not (0 < percent <= 100):
            continue
        normalized.append((name, percent / 100.0))
    return normalized


def _resolve_resource_hourly_rate(name: str, rates_by_name: Optional[Dict[str, float]]) -> Optional[float]:
    """Resolves hourly rate for a resource from explicit rate card or sensible benchmark estimations."""
    if rates_by_name and name in rates_by_name:
        rate = rates_by_name[name]
        if rate and rate > 0:
            return rate
    from process_toolkit.portfolio_backlog.portfolio_backlog import ROLE_BENCHMARK_RATES
    if name in ROLE_BENCHMARK_RATES:
        return ROLE_BENCHMARK_RATES[name][0] / _WORK_HOURS_PER_DAY
    lower = name.lower()
    for role, (daily, _) in ROLE_BENCHMARK_RATES.items():
        if role.lower() in lower or lower in role.lower():
            return daily / _WORK_HOURS_PER_DAY
    if "delivery" in lower or "programme" in lower:
        return 1300.0 / _WORK_HOURS_PER_DAY
    if "project manager" in lower or "pm" in lower.split():
        return 1200.0 / _WORK_HOURS_PER_DAY
    if "architect" in lower:
        return 1500.0 / _WORK_HOURS_PER_DAY
    if "lead" in lower and "analyst" in lower:
        return 1100.0 / _WORK_HOURS_PER_DAY
    if "analyst" in lower:
        return 1000.0 / _WORK_HOURS_PER_DAY
    if "engineer" in lower or "developer" in lower:
        return 1275.0 / _WORK_HOURS_PER_DAY
    if "qa" in lower or "test" in lower:
        return 1000.0 / _WORK_HOURS_PER_DAY
    return 1200.0 / _WORK_HOURS_PER_DAY


def _render_mspdi(
    project_name: str,
    top_level_tasks: List["_Task"],
    project_start: _dt.date,
    holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS,
    resources: Optional[List[tuple]] = None,
    rates_by_name: Optional[Dict[str, float]] = None,
) -> str:
    ET.register_namespace("", _MSPDI_NS)
    root = ET.Element(f"{{{_MSPDI_NS}}}Project")

    all_tasks = _flatten(top_level_tasks)
    overall_finish = max((t.finish for t in all_tasks if t.finish), default=project_start)
    normalized_resources = resources or []

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

    # Holiday exceptions, restricted to the plan's own actual date span --
    # each marks that single date as non-working, so a tool re-deriving
    # Start/Finish from Duration + Predecessors + this same Calendar on
    # open skips it exactly like this module's own scheduler already did.
    relevant_holidays = sorted(d for d in holidays if project_start <= d <= overall_finish)
    if relevant_holidays:
        exceptions = ET.SubElement(calendar, "Exceptions")
        for index, holiday in enumerate(relevant_holidays, start=1):
            exception = ET.SubElement(exceptions, "Exception")
            ET.SubElement(exception, "UID").text = str(index)
            ET.SubElement(exception, "Name").text = "UK bank holiday"
            ET.SubElement(exception, "DayWorking").text = "0"
            period = ET.SubElement(exception, "TimePeriod")
            ET.SubElement(period, "FromDate").text = _date_xml(holiday, 0)
            ET.SubElement(period, "ToDate").text = _date_xml(holiday, 0)

    wbs_by_uid = _wbs_numbers(top_level_tasks)
    tasks_el = ET.SubElement(root, "Tasks")
    leaf_duration_hours: Dict[int, int] = {}
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
            else _count_working_days(task.start, task.finish, holidays) if task.start and task.finish
            else 1
        )
        duration_hours = max(duration_days, 1) * _WORK_HOURS_PER_DAY
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
        if not task.children:
            leaf_duration_hours[task.uid] = duration_hours

    # Collect all resources to be defined in <Resources>
    # Either from caller-supplied resources (which override/set global resourcing)
    # or from leaf tasks' activity-based resources.
    resource_catalog: Dict[str, float] = {}
    if normalized_resources:
        for name, fraction in normalized_resources:
            resource_catalog[name] = max(resource_catalog.get(name, 0.0), fraction)
    else:
        for task in all_tasks:
            if not task.children and task.resources:
                for name, fraction in task.resources:
                    resource_catalog[name] = max(resource_catalog.get(name, 0.0), fraction)

    if resource_catalog:
        resources_el = ET.SubElement(root, "Resources")
        resource_uids: Dict[str, int] = {}
        for index, (name, max_fraction) in enumerate(resource_catalog.items(), start=1):
            resource_uids[name] = index
            resource_el = ET.SubElement(resources_el, "Resource")
            ET.SubElement(resource_el, "UID").text = str(index)
            ET.SubElement(resource_el, "ID").text = str(index)
            ET.SubElement(resource_el, "Name").text = name
            ET.SubElement(resource_el, "Type").text = "1"  # 1 = work resource
            ET.SubElement(resource_el, "MaxUnits").text = f"{max_fraction:g}"
            hourly_rate = _resolve_resource_hourly_rate(name, rates_by_name)
            if hourly_rate is not None and hourly_rate > 0:
                ET.SubElement(resource_el, "StandardRate").text = f"{hourly_rate:.2f}"
                ET.SubElement(resource_el, "StandardRateFormat").text = "3"  # 3 = /hour

        # Assign resources to leaf tasks -- either the caller-supplied resources
        # across all leaf tasks, or each leaf task's own activity-based resources.
        assignments_el = ET.SubElement(root, "Assignments")
        assignment_uid = 1
        for task in all_tasks:
            if task.children:
                continue
            duration_hours = leaf_duration_hours.get(task.uid, task.duration_days * _WORK_HOURS_PER_DAY)
            task_assignments = normalized_resources if normalized_resources else task.resources
            for name, fraction in task_assignments:
                r_uid = resource_uids.get(name)
                if r_uid is None:
                    continue
                assignment_el = ET.SubElement(assignments_el, "Assignment")
                ET.SubElement(assignment_el, "UID").text = str(assignment_uid)
                ET.SubElement(assignment_el, "TaskUID").text = str(task.uid)
                ET.SubElement(assignment_el, "ResourceUID").text = str(r_uid)
                ET.SubElement(assignment_el, "Units").text = f"{fraction:g}"
                ET.SubElement(assignment_el, "Work").text = f"PT{round(duration_hours * fraction)}H0M0S"
                hourly_rate = _resolve_resource_hourly_rate(name, rates_by_name)
                if hourly_rate is not None and hourly_rate > 0:
                    cost = round(duration_hours * fraction * hourly_rate, 2)
                    ET.SubElement(assignment_el, "Cost").text = f"{cost:.2f}"
                assignment_uid += 1

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


def _build_and_write_pert_cpm(
    root_task: "_Task", holidays: FrozenSet[_dt.date], filename: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Generates the companion PERT/CPM network diagram (see docgen.
    pert_cpm_export) from the SAME scheduled task tree the MSPDI file was
    just rendered from, and writes it alongside it. Returns (path, None) on
    success or (None, warning) on failure -- a failure here must never fail
    the overall project-plan export, which has already succeeded by the
    time this is called; the warning is instead folded into the caller's
    own returned message, same as _duration_overrun_warning's WARNING.

    Only LEAF (non-summary) tasks become activities -- standard PERT/CPM
    convention shows individual work items, not the summary rollups that
    span (and would visually overlap) their own children's combined dates.
    `gap_working_days_before` is computed here (not inside pert_cpm_export,
    which stays holiday-agnostic) using the same _count_working_days this
    module already uses elsewhere -- 0 when two consecutive leaves are
    scheduled back-to-back (always true under this module's own scheduler
    today, see _schedule_subtree), but a genuine measurement rather than an
    assumption, so pert_cpm_export's own backward pass produces honest,
    future-proof float/critical results instead of a hardcoded shortcut.
    """
    leaves = [t for t in _flatten([root_task]) if not t.is_summary and t.start and t.finish]
    activities = []
    for i, task in enumerate(leaves):
        gap = 0
        if i > 0:
            gap = max(0, _count_working_days(leaves[i - 1].finish, task.start, holidays) - 2)
        activities.append({
            "uid": task.uid, "name": task.name, "start": task.start, "finish": task.finish,
            "duration_days": max(task.duration_days, 1), "gap_working_days_before": gap,
        })
    try:
        return generate_pert_cpm_diagram(activities, root_task.name, filename), None
    except (OSError, ValueError) as e:
        return None, f"WARNING: Could not generate the PERT/CPM diagram: {e}"


def _resolve_holidays(holiday_calendar: Optional[str], project_start: _dt.date) -> FrozenSet[_dt.date]:
    """Only "uk" is recognized -- anything else (None, a typo, a different
    country) resolves to no holidays at all (weekends-only calendar) rather
    than guessing a calendar this module has no real data for."""
    if isinstance(holiday_calendar, str) and holiday_calendar.strip().lower() == "uk":
        return _uk_bank_holidays_covering(project_start)
    return _NO_HOLIDAYS


def _duration_overrun_warning(
    root_task: "_Task", target_duration_weeks: Optional[float],
) -> Optional[str]:
    """Post-hoc check only -- never reshapes the already-sequenced
    schedule to force a fit. Returns None when there's nothing to warn
    about (no target given, or the plan fits within it)."""
    if not target_duration_weeks or not root_task.start or not root_task.finish:
        return None
    target_days = target_duration_weeks * 7
    actual_days = (root_task.finish - root_task.start).days + 1
    if actual_days <= target_days:
        return None
    return (
        f"WARNING: the sequenced plan spans {actual_days} calendar day(s) "
        f"({root_task.start.isoformat()} to {root_task.finish.isoformat()}), which overruns the "
        f"requested {target_duration_weeks:g}-week target ({target_days:g} day(s)) by "
        f"{actual_days - target_days:g} day(s). Durations/sequencing were not compressed to force "
        f"a fit -- review scope, resourcing, or the target itself."
    )


# ---------------------------------------------------------------------------
# Portfolio Backlog
# ---------------------------------------------------------------------------

_BACKLOG_DISCLOSURE = (
    "Illustrative delivery schedule: {days_per_point:g} working day(s) per story point "
    "(job_size), sequenced strictly in epic -> feature -> story order. This is a planning "
    "estimate, not a committed schedule -- durations and sequencing must be validated and "
    "adjusted by the delivery team before being treated as a commitment."
)


def build_portfolio_backlog_project_plan(
    start_date: Optional[str] = None,
    resources: Optional[List[Dict[str, Any]]] = None,
    target_duration_weeks: Optional[float] = None,
    holiday_calendar: Optional[str] = None,
) -> str:
    """Exports the current saved Enterprise Agile Portfolio Backlog as an
    MSPDI project plan. Same "ERROR: ..."/"<thing> export failed: ..." string
    convention as vsdx_export.py's own build_* functions -- never raises to
    the caller. `resources` is an optional list of {"name": str,
    "allocation_percent": number} -- neither this nor `target_duration_weeks`/
    `holiday_calendar` exist in the saved backlog JSON; all three are
    supplied by the caller at export time only (see module docstring)."""
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
                story_res = story.get("resources")
                if not story_res:
                    from process_toolkit.portfolio_backlog.portfolio_backlog import calculate_story_resources
                    story_res = calculate_story_resources(story)
                story_task.resources = _normalize_resources(story_res)
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

    project_start = _parse_start_date(start_date)
    holidays = _resolve_holidays(holiday_calendar, project_start)
    _schedule_subtree(root, _first_working_day_on_or_after(project_start, holidays), holidays)

    overrun_warning = _duration_overrun_warning(root, target_duration_weeks)
    if overrun_warning:
        root.notes = f"{root.notes}\n\n{overrun_warning}"

    rates_by_name: Dict[str, float] = {}
    for entry in backlog.get("rate_card") or []:
        if isinstance(entry, dict):
            r_name = entry.get("role") or entry.get("name")
            daily = entry.get("daily_rate") or entry.get("rate")
            if r_name and daily:
                try:
                    rates_by_name[str(r_name)] = float(daily) / _WORK_HOURS_PER_DAY
                except (ValueError, TypeError):
                    pass
    from process_toolkit.portfolio_backlog.portfolio_backlog import ROLE_BENCHMARK_RATES
    for r_name, (daily, _) in ROLE_BENCHMARK_RATES.items():
        rates_by_name.setdefault(r_name, daily / _WORK_HOURS_PER_DAY)

    normalized_resources = _normalize_resources(resources)
    xml_text = _render_mspdi(
        root.name, [root], root.start or project_start, holidays, normalized_resources, rates_by_name,
    )
    try:
        out_path = _write_output(xml_text, PORTFOLIO_BACKLOG_PROJECT_PLAN_FILENAME)
    except OSError as e:
        return f"Project plan export failed: {e}"
    message = f"Project plan successfully exported to {out_path}"
    pert_cpm_path, pert_cpm_warning = _build_and_write_pert_cpm(
        root, holidays, PORTFOLIO_BACKLOG_PERT_CPM_FILENAME,
    )
    if pert_cpm_path:
        message += f"\nA PERT/CPM network diagram was also generated at {pert_cpm_path}."
    elif pert_cpm_warning:
        message += f"\n{pert_cpm_warning}"
    return f"{message}\n\n{overrun_warning}" if overrun_warning else message


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


def build_proposal_response_project_plan(
    start_date: Optional[str] = None,
    resources: Optional[List[Dict[str, Any]]] = None,
    target_duration_weeks: Optional[float] = None,
    holiday_calendar: Optional[str] = None,
) -> str:
    """Exports the current saved proposal response's implementation_plan as
    an MSPDI project plan. Same string-return convention as
    build_portfolio_backlog_project_plan above, including the same
    resources/target_duration_weeks/holiday_calendar parameters."""
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
        if phase.get("resources"):
            phase_task.resources = _normalize_resources(phase.get("resources"))
        root.children.append(phase_task)

    if not root.children:
        return "ERROR: No saved proposal response found. Create one first."

    project_start = _parse_start_date(start_date)
    holidays = _resolve_holidays(holiday_calendar, project_start)
    _schedule_subtree(root, _first_working_day_on_or_after(project_start, holidays), holidays)

    overrun_warning = _duration_overrun_warning(root, target_duration_weeks)
    if overrun_warning:
        root.notes = f"{root.notes}\n\n{overrun_warning}"

    rates_by_name_proposal: Dict[str, float] = {}
    for entry in response.get("rate_card") or []:
        if isinstance(entry, dict):
            r_name = entry.get("role") or entry.get("name")
            daily = entry.get("daily_rate") or entry.get("rate")
            if r_name and daily:
                try:
                    rates_by_name_proposal[str(r_name)] = float(daily) / _WORK_HOURS_PER_DAY
                except (ValueError, TypeError):
                    pass
    from process_toolkit.portfolio_backlog.portfolio_backlog import ROLE_BENCHMARK_RATES
    for r_name, (daily, _) in ROLE_BENCHMARK_RATES.items():
        rates_by_name_proposal.setdefault(r_name, daily / _WORK_HOURS_PER_DAY)

    normalized_resources = _normalize_resources(resources)
    xml_text = _render_mspdi(
        root.name, [root], root.start or project_start, holidays, normalized_resources, rates_by_name_proposal,
    )
    try:
        out_path = _write_output(xml_text, PROPOSAL_RESPONSE_PROJECT_PLAN_FILENAME)
    except OSError as e:
        return f"Project plan export failed: {e}"
    message = f"Project plan successfully exported to {out_path}"
    pert_cpm_path, pert_cpm_warning = _build_and_write_pert_cpm(
        root, holidays, PROPOSAL_RESPONSE_PERT_CPM_FILENAME,
    )
    if pert_cpm_path:
        message += f"\nA PERT/CPM network diagram was also generated at {pert_cpm_path}."
    elif pert_cpm_warning:
        message += f"\n{pert_cpm_warning}"
    return f"{message}\n\n{overrun_warning}" if overrun_warning else message


# ---------------------------------------------------------------------------
# Reading an existing MSPDI file back (the reverse direction of everything
# above) -- shared by ingestion/extractors.py's own directory-import text
# formatting AND the web client's "Diagrams" tab Gantt view, so an MSPDI
# file's own <Tasks> structure is only ever walked in one place.
# ---------------------------------------------------------------------------

def _parse_mspdi_root(path: str) -> Optional[ET.Element]:
    """Returns the parsed root element if `path` is actually an MSPDI file
    (the exact format this module itself writes), else None -- malformed
    XML or a real root element that isn't the MSPDI namespace's own
    <Project> are both "not MSPDI", not an error, since a caller's own job
    is to fall back to generic handling in that case."""
    if not os.path.isfile(path):
        return None
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    if root.tag != f"{{{_MSPDI_NS}}}Project":
        return None
    return root


def mspdi_project_title(path: str) -> Optional[str]:
    """The project's own Title (falling back to Name), or None if `path`
    isn't MSPDI at all."""
    root = _parse_mspdi_root(path)
    if root is None:
        return None
    ns = {"p": _MSPDI_NS}
    return root.findtext("p:Title", default="", namespaces=ns) or root.findtext("p:Name", default="", namespaces=ns) or None


def parse_mspdi_resources(path: str) -> Optional[List[Dict[str, Any]]]:
    """Parses an existing MSPDI file's <Resources> into a list of plain dicts:
    {"uid", "id", "name", "type", "max_units"}. Returns None if path isn't MSPDI."""
    root = _parse_mspdi_root(path)
    if root is None:
        return None

    ns = {"p": _MSPDI_NS}
    resources: List[Dict[str, Any]] = []
    for res_el in root.findall(".//p:Resources/p:Resource", ns):
        uid_str = res_el.findtext("p:UID", default="", namespaces=ns) or None
        id_str = res_el.findtext("p:ID", default="", namespaces=ns) or uid_str
        name = (res_el.findtext("p:Name", default="", namespaces=ns) or "").strip()
        type_str = res_el.findtext("p:Type", default="1", namespaces=ns)
        max_units_str = res_el.findtext("p:MaxUnits", default="", namespaces=ns)
        max_units = None
        if max_units_str:
            try:
                max_units = float(max_units_str)
            except ValueError:
                pass
        std_rate_str = res_el.findtext("p:StandardRate", default="", namespaces=ns)
        standard_rate = None
        if std_rate_str:
            try:
                standard_rate = float(std_rate_str)
            except ValueError:
                pass
        resources.append({
            "uid": uid_str,
            "id": id_str,
            "name": name,
            "type": int(type_str) if type_str.isdigit() else 1,
            "max_units": max_units,
            "standard_rate": standard_rate,
        })
    return resources


def parse_mspdi_assignments(path: str) -> Optional[List[Dict[str, Any]]]:
    """Parses an existing MSPDI file's <Assignments> into a list of plain dicts:
    {"uid", "task_uid", "resource_uid", "resource_name", "units", "work", "work_hours", "cost"}.
    Returns None if path isn't MSPDI."""
    root = _parse_mspdi_root(path)
    if root is None:
        return None

    ns = {"p": _MSPDI_NS}
    resource_name_by_uid: Dict[str, str] = {}
    for res_el in root.findall(".//p:Resources/p:Resource", ns):
        uid_str = res_el.findtext("p:UID", default="", namespaces=ns)
        name = (res_el.findtext("p:Name", default="", namespaces=ns) or "").strip()
        if uid_str:
            resource_name_by_uid[uid_str] = name

    assignments: List[Dict[str, Any]] = []
    for a_el in root.findall(".//p:Assignments/p:Assignment", ns):
        uid_str = a_el.findtext("p:UID", default="", namespaces=ns) or None
        task_uid_str = a_el.findtext("p:TaskUID", default="", namespaces=ns) or None
        res_uid_str = a_el.findtext("p:ResourceUID", default="", namespaces=ns) or None
        units_str = a_el.findtext("p:Units", default="", namespaces=ns)
        work_str = a_el.findtext("p:Work", default="", namespaces=ns) or None
        cost_str = a_el.findtext("p:Cost", default="", namespaces=ns)
        units = None
        if units_str:
            try:
                units = float(units_str)
            except ValueError:
                pass
        work_hours = None
        if work_str:
            m = re.match(r"PT(\d+(?:\.\d+)?)H", work_str)
            if m:
                work_hours = float(m.group(1))
        cost = None
        if cost_str:
            try:
                cost = float(cost_str)
            except ValueError:
                pass

        assignments.append({
            "uid": uid_str,
            "task_uid": task_uid_str,
            "resource_uid": res_uid_str,
            "resource_name": resource_name_by_uid.get(res_uid_str or "", ""),
            "units": units,
            "work": work_str,
            "work_hours": work_hours,
            "cost": cost,
        })
    return assignments


def parse_mspdi_tasks(path: str) -> Optional[List[Dict[str, Any]]]:
    """Parses an existing MSPDI file's <Tasks> into a list of plain dicts,
    one per task, in document order: {"uid", "name", "outline_level",
    "is_summary", "start", "finish", "duration_hours", "predecessor_uid",
    "notes", "resources", "assignments", "cost"}. start/finish are the raw MSPDI date-time strings (or None);
    duration_hours is a float parsed from the task's own "PT#H#M#S" value
    (or None if absent/unparseable). Each task includes its assigned resources
    and allocation details. Returns None if `path` isn't actually MSPDI,
    so callers can fall back to generic handling the same way
    _parse_mspdi_root's own callers do."""
    root = _parse_mspdi_root(path)
    if root is None:
        return None

    ns = {"p": _MSPDI_NS}
    resource_name_by_uid: Dict[str, str] = {}
    for res_el in root.findall(".//p:Resources/p:Resource", ns):
        uid_str = res_el.findtext("p:UID", default="", namespaces=ns)
        name = (res_el.findtext("p:Name", default="", namespaces=ns) or "").strip()
        if uid_str:
            resource_name_by_uid[uid_str] = name

    assignments_by_task: Dict[str, List[Dict[str, Any]]] = {}
    for a_el in root.findall(".//p:Assignments/p:Assignment", ns):
        uid_str = a_el.findtext("p:UID", default="", namespaces=ns) or None
        task_uid_str = a_el.findtext("p:TaskUID", default="", namespaces=ns) or ""
        res_uid_str = a_el.findtext("p:ResourceUID", default="", namespaces=ns) or ""
        units_str = a_el.findtext("p:Units", default="", namespaces=ns)
        work_str = a_el.findtext("p:Work", default="", namespaces=ns) or None
        cost_str = a_el.findtext("p:Cost", default="", namespaces=ns)
        units = None
        if units_str:
            try:
                units = float(units_str)
            except ValueError:
                pass
        work_hours = None
        if work_str:
            m = re.match(r"PT(\d+(?:\.\d+)?)H", work_str)
            if m:
                work_hours = float(m.group(1))
        cost = None
        if cost_str:
            try:
                cost = float(cost_str)
            except ValueError:
                pass

        assignment_data = {
            "uid": uid_str,
            "task_uid": task_uid_str,
            "resource_uid": res_uid_str,
            "resource_name": resource_name_by_uid.get(res_uid_str, ""),
            "units": units,
            "work": work_str,
            "work_hours": work_hours,
            "cost": cost,
        }
        assignments_by_task.setdefault(task_uid_str, []).append(assignment_data)

    tasks: List[Dict[str, Any]] = []
    for task_el in root.findall(".//p:Tasks/p:Task", ns):
        try:
            outline_level = int(task_el.findtext("p:OutlineLevel", default="1", namespaces=ns))
        except ValueError:
            outline_level = 1

        duration_hours: Optional[float] = None
        match = re.match(r"PT(\d+(?:\.\d+)?)H", task_el.findtext("p:Duration", default="", namespaces=ns) or "")
        if match:
            duration_hours = float(match.group(1))

        predecessor_uid = task_el.findtext("p:PredecessorLink/p:PredecessorUID", default="", namespaces=ns) or None
        task_uid = task_el.findtext("p:UID", default="", namespaces=ns) or None
        task_assigns = assignments_by_task.get(task_uid or "", [])
        task_resources = [
            {
                "resource_uid": a["resource_uid"],
                "name": a["resource_name"],
                "units": a["units"],
                "work": a["work"],
                "work_hours": a["work_hours"],
                "cost": a.get("cost"),
            }
            for a in task_assigns
        ]
        task_cost_vals = [a["cost"] for a in task_assigns if a.get("cost") is not None]
        task_cost = round(sum(task_cost_vals), 2) if task_cost_vals else None

        tasks.append({
            "uid": task_uid,
            "name": (task_el.findtext("p:Name", default="", namespaces=ns) or "").strip(),
            "outline_level": outline_level,
            "is_summary": (task_el.findtext("p:Summary", default="0", namespaces=ns) or "0") == "1",
            "start": task_el.findtext("p:Start", default="", namespaces=ns) or None,
            "finish": task_el.findtext("p:Finish", default="", namespaces=ns) or None,
            "duration_hours": duration_hours,
            "predecessor_uid": predecessor_uid,
            "notes": (task_el.findtext("p:Notes", default="", namespaces=ns) or "").strip(),
            "resources": task_resources,
            "assignments": task_assigns,
            "cost": task_cost,
        })
    return tasks


def parse_mspdi_project(path: str) -> Optional[Dict[str, Any]]:
    """Parses an existing MSPDI file into a complete Project JSON representation:
    {"title", "start_date", "finish_date", "tasks", "resources", "assignments", "total_cost"}.
    Includes resource allocation and costing on the project level and on every task. Returns None if path isn't MSPDI.
    """
    root = _parse_mspdi_root(path)
    if root is None:
        return None

    ns = {"p": _MSPDI_NS}
    title = root.findtext("p:Title", default="", namespaces=ns) or root.findtext("p:Name", default="", namespaces=ns) or None
    start_date = root.findtext("p:StartDate", default="", namespaces=ns) or None
    finish_date = root.findtext("p:FinishDate", default="", namespaces=ns) or None
    tasks = parse_mspdi_tasks(path) or []
    resources = parse_mspdi_resources(path) or []
    assignments = parse_mspdi_assignments(path) or []
    cost_vals = [a["cost"] for a in assignments if a.get("cost") is not None]
    total_cost = round(sum(cost_vals), 2) if cost_vals else None

    return {
        "title": title,
        "start_date": start_date,
        "finish_date": finish_date,
        "tasks": tasks,
        "resources": resources,
        "assignments": assignments,
        "total_cost": total_cost,
    }
