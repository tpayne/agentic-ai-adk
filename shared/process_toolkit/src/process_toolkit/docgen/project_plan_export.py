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
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from process_toolkit import paths
from process_toolkit.portfolio_backlog.portfolio_backlog import load_portfolio_backlog
from process_toolkit.proposal_response.proposal_response import load_proposal_response
from process_toolkit.docgen.pert_cpm_export import generate_pert_cpm_diagram

logger = logging.getLogger("ProcessArchitect.ProjectPlanExport")

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
        self.predecessor_uids: List[int] = []
        self.children: List["_Task"] = []
        self.resources: List[Tuple[str, float]] = []
        self.has_explicit_resources: bool = False
        self.item_id: Optional[str] = None
        self.dependencies: List[str] = []
        self.start_week: Optional[int] = None
        self.end_week: Optional[int] = None
        self.is_milestone: bool = False


def _schedule_sequential_leaf(
    task: "_Task", anchor_start: _dt.date, holidays: FrozenSet[_dt.date],
) -> _dt.date:
    """Schedules one leaf task starting at anchor_start, returns its finish date."""
    task.start = anchor_start
    if getattr(task, "is_milestone", False) or task.duration_days == 0:
        task.finish = anchor_start
        task.duration_days = 0
    else:
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
            if previous_uid is not None and previous_uid not in child.predecessor_uids:
                child.predecessor_uids.append(previous_uid)
        finish = _schedule_subtree(child, cursor, holidays)
        cursor = _next_working_day(finish, holidays)
        previous_uid = child.uid
    task.finish = task.children[-1].finish or task.start
    return task.finish


def _schedule_task_tree(
    root: "_Task",
    anchor_start: _dt.date,
    holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS,
    target_duration_weeks: Optional[float] = None,
) -> _dt.date:
    all_tasks = _flatten([root])
    has_explicit_deps = any(t.dependencies or t.predecessor_uids or (t.start_week and t.start_week > 1) for t in all_tasks)
    logger.info(
        "_schedule_task_tree: scheduling root %r (%d total tasks, %d leaves, has_explicit_deps=%s, target_duration_weeks=%s)",
        root.name, len(all_tasks), len([t for t in all_tasks if not t.children]), has_explicit_deps, target_duration_weeks,
    )
    if not has_explicit_deps:
        return _schedule_subtree(root, anchor_start, holidays)

    # Build identifier lookup
    task_by_id: Dict[str, _Task] = {}
    task_by_uid: Dict[int, _Task] = {t.uid: t for t in all_tasks}
    for t in all_tasks:
        if t.item_id:
            task_by_id[t.item_id.strip()] = t
            task_by_id[t.item_id.strip().lower()] = t
        if t.name:
            task_by_id[t.name.strip()] = t
            task_by_id[t.name.strip().lower()] = t

    def _terminal_leaf_uids(task: "_Task") -> List[int]:
        leaves = [l for l in _flatten([task]) if not l.children]
        return [leaves[-1].uid] if leaves else []

    def _initial_leaf_tasks(task: "_Task") -> List["_Task"]:
        if not task.children:
            return [task]
        return _initial_leaf_tasks(task.children[0])

    # Resolve dependencies into predecessor_uids
    for t in all_tasks:
        for dep in (t.dependencies or []):
            dep_clean = str(dep).strip()
            target = task_by_id.get(dep_clean) or task_by_id.get(dep_clean.lower())
            if target:
                if target.is_summary:
                    for leaf_uid in _terminal_leaf_uids(target):
                        if leaf_uid != t.uid and leaf_uid not in t.predecessor_uids:
                            t.predecessor_uids.append(leaf_uid)
                else:
                    if target.uid != t.uid and target.uid not in t.predecessor_uids:
                        t.predecessor_uids.append(target.uid)

    # Propagate summary task predecessors to initial leaf tasks
    for t in all_tasks:
        if t.is_summary and t.predecessor_uids:
            for init_leaf in _initial_leaf_tasks(t):
                for p in t.predecessor_uids:
                    if p != init_leaf.uid and p not in init_leaf.predecessor_uids:
                        init_leaf.predecessor_uids.append(p)

    # Link intra-branch siblings without explicit dependencies
    def _link_internal_siblings(parent: "_Task"):
        for i, child in enumerate(parent.children):
            if i > 0 and not child.dependencies and not child.predecessor_uids:
                prev_sibling = parent.children[i - 1]
                prev_leaves = _terminal_leaf_uids(prev_sibling)
                for init_leaf in _initial_leaf_tasks(child):
                    for p in prev_leaves:
                        if p != init_leaf.uid and p not in init_leaf.predecessor_uids:
                            init_leaf.predecessor_uids.append(p)
            if child.children:
                _link_internal_siblings(child)

    _link_internal_siblings(root)

    # At root level: ensure every top-level epic i > 0 has at least one predecessor
    if len(root.children) > 1:
        phase1_leaves = _terminal_leaf_uids(root.children[0])
        for i in range(1, len(root.children)):
            epic = root.children[i]
            if not epic.predecessor_uids:
                for init_leaf in _initial_leaf_tasks(epic):
                    if not init_leaf.predecessor_uids and phase1_leaves:
                        init_leaf.predecessor_uids.append(phase1_leaves[-1])

    leaf_tasks = [t for t in all_tasks if not t.children]
    scheduled: Set[int] = set()

    # Pre-calibrate leaf task durations when target_duration_weeks is specified
    if target_duration_weeks and target_duration_weeks > 0:
        cal_finish = anchor_start + _dt.timedelta(days=round(target_duration_weeks * 7) - 3)
        target_finish_limit = cal_finish
        while not _is_working_day(target_finish_limit, holidays):
            target_finish_limit -= _dt.timedelta(days=1)
        total_target_working_days = _count_working_days(anchor_start, target_finish_limit, holidays)

        # Compute longest sequential path in leaf DAG
        longest_path: Dict[int, int] = {}
        for leaf in leaf_tasks:
            preds = [p for p in leaf.predecessor_uids if p in task_by_uid]
            dur = 0 if (getattr(leaf, "is_milestone", False) or leaf.duration_days == 0) else max(leaf.duration_days, 1)
            week_offset = ((leaf.start_week - 1) * 5) if (leaf.start_week and leaf.start_week > 1) else 0
            if preds:
                longest_path[leaf.uid] = max(max(longest_path.get(p, task_by_uid[p].duration_days) for p in preds), week_offset) + dur
            else:
                longest_path[leaf.uid] = week_offset + dur
        max_path_len = max(longest_path.values(), default=0)

        # Proportionally compress leaf task durations if total critical path overruns target
        if max_path_len > total_target_working_days and total_target_working_days > 0:
            scale = total_target_working_days / max_path_len
            logger.info(
                "_schedule_task_tree: critical path length (%d days) exceeds target (%d working days); compressing leaf durations with scale factor %.4f",
                max_path_len, total_target_working_days, scale,
            )
            for leaf in leaf_tasks:
                if not getattr(leaf, "is_milestone", False) and leaf.duration_days > 0:
                    leaf.duration_days = max(1, round(leaf.duration_days * scale))
        else:
            logger.info(
                "_schedule_task_tree: critical path length (%d days) fits within target (%d working days)",
                max_path_len, total_target_working_days,
            )

    for _ in range(len(leaf_tasks) * 2):
        progress = False
        for leaf in leaf_tasks:
            if leaf.uid in scheduled:
                continue
            preds = [p for p in leaf.predecessor_uids if p in task_by_uid]
            if all(p in scheduled for p in preds):
                is_ms = getattr(leaf, "is_milestone", False) or leaf.duration_days == 0
                if preds:
                    max_pred_finish = max(task_by_uid[p].finish for p in preds if task_by_uid[p].finish)
                    earliest = max_pred_finish if is_ms else _next_working_day(max_pred_finish, holidays)
                else:
                    earliest = anchor_start

                if not is_ms and leaf.start_week and leaf.start_week > 1:
                    cal_week_start = anchor_start + _dt.timedelta(days=(leaf.start_week - 1) * 7)
                    week_start = _first_working_day_on_or_after(cal_week_start, holidays)
                    earliest = max(earliest, week_start)

                if is_ms:
                    leaf.start = earliest
                    leaf.finish = earliest
                    leaf.duration_days = 0
                else:
                    leaf.start = _first_working_day_on_or_after(earliest, holidays)
                    leaf.finish = _advance_working_days(leaf.start, max(leaf.duration_days, 1), holidays)

                if not is_ms and target_duration_weeks and target_duration_weeks > 0:
                    cal_finish = anchor_start + _dt.timedelta(days=round(target_duration_weeks * 7) - 3)
                    target_finish_limit = cal_finish
                    while not _is_working_day(target_finish_limit, holidays):
                        target_finish_limit -= _dt.timedelta(days=1)
                    if leaf.start <= target_finish_limit and leaf.finish > target_finish_limit:
                        avail = _count_working_days(leaf.start, target_finish_limit, holidays)
                        leaf.duration_days = max(avail, 1)
                        leaf.finish = _advance_working_days(leaf.start, leaf.duration_days, holidays)

                if leaf.predecessor_uids:
                    leaf.predecessor_uid = leaf.predecessor_uids[-1]
                scheduled.add(leaf.uid)
                progress = True
        if not progress:
            break

    for leaf in leaf_tasks:
        if leaf.uid not in scheduled:
            cur_start = anchor_start
            is_ms = getattr(leaf, "is_milestone", False) or leaf.duration_days == 0
            if is_ms:
                leaf.start = _first_working_day_on_or_after(cur_start, holidays)
                leaf.finish = leaf.start
                leaf.duration_days = 0
            else:
                leaf.start = _first_working_day_on_or_after(cur_start, holidays)
                leaf.finish = _advance_working_days(leaf.start, max(leaf.duration_days, 1), holidays)
            if not is_ms and target_duration_weeks and target_duration_weeks > 0:
                cal_finish = anchor_start + _dt.timedelta(days=round(target_duration_weeks * 7) - 3)
                target_finish_limit = cal_finish
                while not _is_working_day(target_finish_limit, holidays):
                    target_finish_limit -= _dt.timedelta(days=1)
                if leaf.start <= target_finish_limit and leaf.finish > target_finish_limit:
                    avail = _count_working_days(leaf.start, target_finish_limit, holidays)
                    leaf.duration_days = max(avail, 1)
                    leaf.finish = _advance_working_days(leaf.start, leaf.duration_days, holidays)
            scheduled.add(leaf.uid)

    def _rollup(task: "_Task"):
        for child in task.children:
            if child.children:
                _rollup(child)
        child_starts = [c.start for c in task.children if c.start]
        child_finishes = [c.finish for c in task.children if c.finish]
        if child_starts and child_finishes:
            task.start = min(child_starts)
            task.finish = max(child_finishes)
            task.duration_days = _count_working_days(task.start, task.finish, holidays)
            if task.predecessor_uids and not task.predecessor_uid:
                task.predecessor_uid = task.predecessor_uids[-1]

    _rollup(root)
    total_w_days = _count_working_days(root.start, root.finish, holidays) if root.start and root.finish else 0
    logger.info(
        "_schedule_task_tree: scheduled project %r from %s to %s (%d working days)",
        root.name, root.start, root.finish, total_w_days,
    )
    return root.finish or anchor_start


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


def _date_xml(day: _dt.date, hour: int, minute: int = 0, second: int = 0) -> str:
    return _dt.datetime.combine(day, _dt.time(hour, minute, second)).strftime(_DATE_FORMAT)


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


ROLE_ALIASES: Dict[str, str] = {
    "pdm": "Programme Delivery Manager",
    "programme delivery manager": "Programme Delivery Manager",
    "program delivery manager": "Programme Delivery Manager",
    "lead ba": "Lead Business Analyst",
    "lead business analyst": "Lead Business Analyst",
    "ba": "Business Analyst",
    "business analyst": "Business Analyst",
    "sa": "Solution Architect",
    "solution architect": "Solution Architect",
    "solutions architect": "Solution Architect",
    "pm": "Project Manager",
    "project manager": "Project Manager",
    "po": "Product Owner",
    "product owner": "Product Owner",
    "ea": "Enterprise Architect",
    "enterprise architect": "Enterprise Architect",
    "qa": "QA Engineer",
    "qa engineer": "QA Engineer",
    "devops": "DevOps Engineer",
    "devops engineer": "DevOps Engineer",
    "swe": "Software Engineer",
    "software engineer": "Software Engineer",
}


def _canonical_role(name: str) -> str:
    key = str(name).strip().lower()
    return ROLE_ALIASES.get(key, str(name).strip())


def _resolve_resource_hourly_rate(name: str, rates_by_name: Optional[Dict[str, float]]) -> Optional[float]:
    """Resolves hourly rate for a resource from explicit rate card or sensible benchmark estimations."""
    cname = _canonical_role(name)
    if rates_by_name:
        for candidate in (name, cname, name.lower(), cname.lower()):
            if candidate in rates_by_name and rates_by_name[candidate] > 0:
                return rates_by_name[candidate]
        for r_k, r_v in rates_by_name.items():
            if _canonical_role(r_k).lower() == cname.lower() and r_v > 0:
                return r_v

    from process_toolkit.portfolio_backlog.portfolio_backlog import get_role_benchmark
    daily_rate, _ = get_role_benchmark(cname or name)
    return daily_rate / _WORK_HOURS_PER_DAY


def _render_mspdi(
    project_name: str,
    top_level_tasks: List["_Task"],
    project_start: _dt.date,
    holidays: FrozenSet[_dt.date] = _NO_HOLIDAYS,
    resources: Optional[List[tuple]] = None,
    rates_by_name: Optional[Dict[str, float]] = None,
    caller_resources: Optional[List[tuple]] = None,
    currency_code: Optional[str] = None,
    currency_symbol: Optional[str] = None,
) -> str:
    ET.register_namespace("", _MSPDI_NS)
    root = ET.Element(f"{{{_MSPDI_NS}}}Project")

    all_tasks = _flatten(top_level_tasks)
    overall_finish = max((t.finish for t in all_tasks if t.finish), default=project_start)
    normalized_resources = resources or []

    # Currency detection
    if not currency_code:
        currency_code = "GBP"
        currency_symbol = "£"
        text_corpus = (project_name or "").lower()
        if "$" in text_corpus or "usd" in text_corpus:
            currency_code = "USD"
            currency_symbol = "$"
        elif "€" in text_corpus or "eur" in text_corpus:
            currency_code = "EUR"
            currency_symbol = "€"
    elif not currency_symbol:
        currency_symbol = "£" if currency_code == "GBP" else ("€" if currency_code == "EUR" else "$")

    creation = _dt.datetime.now().strftime(_DATE_FORMAT)

    ET.SubElement(root, "SaveVersion").text = "14"
    ET.SubElement(root, "Name").text = project_name
    ET.SubElement(root, "Title").text = project_name
    ET.SubElement(root, "CreationDate").text = creation
    ET.SubElement(root, "LastSaved").text = creation
    ET.SubElement(root, "ScheduleFromStart").text = "1"
    ET.SubElement(root, "StartDate").text = _date_xml(project_start, _WORK_START_HOUR)
    ET.SubElement(root, "FinishDate").text = _date_xml(overall_finish, _WORK_END_HOUR)
    ET.SubElement(root, "FYStartDate").text = "1"
    ET.SubElement(root, "CalendarUID").text = "1"
    ET.SubElement(root, "DefaultStartTime").text = f"{_WORK_START_HOUR:02d}:00:00"
    ET.SubElement(root, "DefaultFinishTime").text = f"{_WORK_END_HOUR:02d}:00:00"
    ET.SubElement(root, "MinutesPerDay").text = str(_WORK_HOURS_PER_DAY * 60)
    ET.SubElement(root, "MinutesPerWeek").text = str(_WORK_HOURS_PER_DAY * 60 * 5)
    ET.SubElement(root, "DaysPerMonth").text = "20"
    ET.SubElement(root, "DefaultTaskType").text = "0"
    ET.SubElement(root, "DefaultFixedCostAccrual").text = "3"  # 3 = Prorated
    ET.SubElement(root, "CurrencyCode").text = currency_code
    ET.SubElement(root, "CurrencySymbol").text = currency_symbol
    ET.SubElement(root, "CurrencyDigits").text = "2"
    ET.SubElement(root, "DurationFormat").text = "7"  # 7 = days
    ET.SubElement(root, "WorkFormat").text = "2"  # 2 = hours

    calendars = ET.SubElement(root, "Calendars")
    calendar = ET.SubElement(calendars, "Calendar")
    ET.SubElement(calendar, "UID").text = "1"
    ET.SubElement(calendar, "ID").text = "1"
    ET.SubElement(calendar, "Name").text = "Standard"
    ET.SubElement(calendar, "IsBaseCalendar").text = "1"
    ET.SubElement(calendar, "IsBaselineCalendar").text = "0"
    ET.SubElement(calendar, "BaseCalendarUID").text = "-1"
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

    relevant_holidays = sorted(d for d in holidays if project_start <= d <= overall_finish)
    if relevant_holidays:
        exceptions = ET.SubElement(calendar, "Exceptions")
        for index, holiday in enumerate(relevant_holidays, start=1):
            exception = ET.SubElement(exceptions, "Exception")
            ET.SubElement(exception, "UID").text = str(index)
            ET.SubElement(exception, "ID").text = str(index)
            ET.SubElement(exception, "EnteredByOccurrences").text = "0"
            period = ET.SubElement(exception, "TimePeriod")
            ET.SubElement(period, "FromDate").text = _date_xml(holiday, 0, 0, 0)
            ET.SubElement(period, "ToDate").text = _date_xml(holiday, 23, 59, 59)
            ET.SubElement(exception, "Occurrences").text = "1"
            ET.SubElement(exception, "Name").text = "UK bank holiday"
            ET.SubElement(exception, "Type").text = "1"
            ET.SubElement(exception, "DayWorking").text = "0"

    # Pre-compute resource catalog and assignments
    resource_catalog: Dict[str, float] = {}
    if caller_resources:
        for name, fraction in caller_resources:
            cname = _canonical_role(name)
            resource_catalog[cname] = fraction
    else:
        if normalized_resources:
            for name, fraction in normalized_resources:
                cname = _canonical_role(name)
                resource_catalog[cname] = fraction
        for task in all_tasks:
            if not task.children and task.resources:
                for name, fraction in task.resources:
                    cname = _canonical_role(name)
                    if cname not in resource_catalog:
                        resource_catalog[cname] = fraction

    resource_uids: Dict[str, int] = {}
    if resource_catalog:
        for index, (name, _) in enumerate(resource_catalog.items(), start=1):
            resource_uids[name] = index
            resource_uids[name.lower()] = index
            for alias, canon in ROLE_ALIASES.items():
                if canon.lower() == name.lower():
                    resource_uids[alias] = index

    # Plan assignments and calculate task work and cost
    assignments_list: List[Dict[str, Any]] = []
    task_work_map: Dict[int, int] = {}
    task_cost_map: Dict[int, float] = {}
    leaf_duration_hours: Dict[int, int] = {}
    assignment_uid = 1

    for task in all_tasks:
        if task.children:
            continue
        is_milestone = getattr(task, "is_milestone", False) or (task.duration_days == 0 and not task.is_summary)
        if is_milestone:
            leaf_duration_hours[task.uid] = 0
            task_work_map[task.uid] = 0
            task_cost_map[task.uid] = 0.0
            continue

        duration_days = max(task.duration_days, 1)
        dur_hours = duration_days * _WORK_HOURS_PER_DAY
        leaf_duration_hours[task.uid] = dur_hours

        matching_task_resources = []
        if task.resources:
            for name, fraction in task.resources:
                r_uid = (
                    resource_uids.get(name)
                    or resource_uids.get(name.lower())
                    or resource_uids.get(_canonical_role(name).lower())
                )
                if r_uid is not None:
                    matching_task_resources.append((name, fraction))

        if task.has_explicit_resources and matching_task_resources:
            task_assignments = matching_task_resources
        elif caller_resources:
            task_assignments = caller_resources
        elif matching_task_resources:
            task_assignments = matching_task_resources
        else:
            task_assignments = normalized_resources or task.resources

        task_asgn_work = 0
        task_asgn_cost = 0.0
        for name, fraction in task_assignments:
            r_uid = (
                resource_uids.get(name)
                or resource_uids.get(name.lower())
                or resource_uids.get(_canonical_role(name).lower())
            )
            if r_uid is None:
                continue
            work_h = round(dur_hours * fraction)
            task_asgn_work += work_h
            hourly_rate = _resolve_resource_hourly_rate(name, rates_by_name)
            cost = round(work_h * hourly_rate, 2) if hourly_rate and hourly_rate > 0 else 0.0
            task_asgn_cost += cost
            assignments_list.append({
                "uid": assignment_uid,
                "id": assignment_uid,
                "task_uid": task.uid,
                "resource_uid": r_uid,
                "units": fraction,
                "work_hours": work_h,
                "start": task.start or project_start,
                "finish": task.finish or overall_finish,
                "cost": cost if (hourly_rate and hourly_rate > 0) else None,
            })
            assignment_uid += 1

        task_work_map[task.uid] = task_asgn_work if task_assignments else dur_hours
        task_cost_map[task.uid] = round(task_asgn_cost, 2)

    # Rollup work and cost for summary tasks
    def _rollup_task_work_and_cost(t: "_Task") -> Tuple[int, float]:
        if not t.children:
            return task_work_map.get(t.uid, 0), task_cost_map.get(t.uid, 0.0)
        tot_work = 0
        tot_cost = 0.0
        for c in t.children:
            w, cst = _rollup_task_work_and_cost(c)
            tot_work += w
            tot_cost += cst
        task_work_map[t.uid] = tot_work
        task_cost_map[t.uid] = round(tot_cost, 2)
        return tot_work, tot_cost

    for top in top_level_tasks:
        _rollup_task_work_and_cost(top)

    wbs_by_uid = _wbs_numbers(top_level_tasks)
    tasks_el = ET.SubElement(root, "Tasks")
    for order, task in enumerate(all_tasks, start=1):
        task_el = ET.SubElement(tasks_el, "Task")
        ET.SubElement(task_el, "UID").text = str(task.uid)
        ET.SubElement(task_el, "ID").text = str(order)
        ET.SubElement(task_el, "Name").text = task.name
        ET.SubElement(task_el, "Type").text = "0"
        ET.SubElement(task_el, "IsNull").text = "0"
        ET.SubElement(task_el, "CreateDate").text = creation
        wbs_num = wbs_by_uid.get(task.uid, str(order))
        ET.SubElement(task_el, "WBS").text = wbs_num
        ET.SubElement(task_el, "OutlineNumber").text = wbs_num
        ET.SubElement(task_el, "OutlineLevel").text = str(task.outline_level)
        ET.SubElement(task_el, "Priority").text = "500"
        is_milestone = getattr(task, "is_milestone", False) or (task.duration_days == 0 and not task.children and not task.is_summary)
        if task.start:
            s_hour = _WORK_END_HOUR if is_milestone else _WORK_START_HOUR
            ET.SubElement(task_el, "Start").text = _date_xml(task.start, s_hour)
        if task.finish:
            ET.SubElement(task_el, "Finish").text = _date_xml(task.finish, _WORK_END_HOUR)
        duration_days = (
            0 if is_milestone
            else task.duration_days if not task.children
            else _count_working_days(task.start, task.finish, holidays) if task.start and task.finish
            else 1
        )
        if is_milestone:
            ET.SubElement(task_el, "Duration").text = "PT0H0M0S"
        else:
            ET.SubElement(task_el, "Duration").text = _duration_xml(duration_days)
        ET.SubElement(task_el, "DurationFormat").text = "7"  # 7 = days, display hint only
        t_work_h = task_work_map.get(task.uid, 0 if is_milestone else duration_days * _WORK_HOURS_PER_DAY)
        ET.SubElement(task_el, "Work").text = f"PT{t_work_h}H0M0S"
        ET.SubElement(task_el, "RemainingWork").text = f"PT{t_work_h}H0M0S"
        t_cost = task_cost_map.get(task.uid)
        if t_cost is not None and rates_by_name:
            cost_str = f"{t_cost:.2f}"
            ET.SubElement(task_el, "Cost").text = cost_str
            ET.SubElement(task_el, "RemainingCost").text = cost_str
        ET.SubElement(task_el, "PercentComplete").text = "0"
        ET.SubElement(task_el, "PercentWorkComplete").text = "0"
        ET.SubElement(task_el, "Summary").text = "1" if task.is_summary else "0"
        ET.SubElement(task_el, "Milestone").text = "1" if is_milestone else "0"
        ET.SubElement(task_el, "ConstraintType").text = "0"
        predecessors = list(task.predecessor_uids)
        if task.predecessor_uid is not None and task.predecessor_uid not in predecessors:
            predecessors.append(task.predecessor_uid)
        for p_uid in predecessors:
            pred = ET.SubElement(task_el, "PredecessorLink")
            ET.SubElement(pred, "PredecessorUID").text = str(p_uid)
            ET.SubElement(pred, "Type").text = "1"  # Finish-to-Start
            ET.SubElement(pred, "CrossProject").text = "0"
            ET.SubElement(pred, "LinkLag").text = "0"
            ET.SubElement(pred, "LagFormat").text = "7"
        ET.SubElement(task_el, "CalendarUID").text = "1"
        if task.notes:
            ET.SubElement(task_el, "Notes").text = task.notes

    if resource_catalog:
        resources_el = ET.SubElement(root, "Resources")
        for index, (name, max_fraction) in enumerate(resource_catalog.items(), start=1):
            resource_el = ET.SubElement(resources_el, "Resource")
            ET.SubElement(resource_el, "UID").text = str(index)
            ET.SubElement(resource_el, "ID").text = str(index)
            ET.SubElement(resource_el, "Name").text = name
            ET.SubElement(resource_el, "Type").text = "1"  # 1 = work resource
            ET.SubElement(resource_el, "IsNull").text = "0"
            ET.SubElement(resource_el, "MaxUnits").text = f"{max_fraction:g}"
            hourly_rate = _resolve_resource_hourly_rate(name, rates_by_name)
            if hourly_rate is not None and hourly_rate > 0:
                ET.SubElement(resource_el, "StandardRate").text = f"{hourly_rate:.2f}"
                ET.SubElement(resource_el, "StandardRateFormat").text = "2"  # 2 = /hour (MSPDI standard)

        assignments_el = ET.SubElement(root, "Assignments")
        for asgn in assignments_list:
            assignment_el = ET.SubElement(assignments_el, "Assignment")
            ET.SubElement(assignment_el, "UID").text = str(asgn["uid"])
            ET.SubElement(assignment_el, "ID").text = str(asgn["id"])
            ET.SubElement(assignment_el, "TaskUID").text = str(asgn["task_uid"])
            ET.SubElement(assignment_el, "ResourceUID").text = str(asgn["resource_uid"])
            ET.SubElement(assignment_el, "PercentWorkComplete").text = "0"
            ET.SubElement(assignment_el, "Units").text = f"{asgn['units']:g}"
            work_xml = f"PT{asgn['work_hours']}H0M0S"
            ET.SubElement(assignment_el, "Work").text = work_xml
            ET.SubElement(assignment_el, "RegularWork").text = work_xml
            ET.SubElement(assignment_el, "RemainingWork").text = work_xml
            ET.SubElement(assignment_el, "Start").text = _date_xml(asgn["start"], _WORK_START_HOUR)
            ET.SubElement(assignment_el, "Finish").text = _date_xml(asgn["finish"], _WORK_END_HOUR)
            if asgn.get("cost") is not None:
                cost_str = f"{asgn['cost']:.2f}"
                ET.SubElement(assignment_el, "Cost").text = cost_str
                ET.SubElement(assignment_el, "RemainingCost").text = cost_str
            ET.SubElement(assignment_el, "HasFixedRateUnits").text = "1"

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def validate_mspdi_xml(xml_input: str) -> List[str]:
    """Validates an MSPDI XML string or file path against Microsoft Project XML schema
    (SaveVersion 14) and loader compatibility rules. Returns a list of error strings;
    an empty list indicates full compliance.
    """
    errors: List[str] = []
    if not isinstance(xml_input, str) or not xml_input.strip():
        return ["Empty or invalid XML input"]

    root: Optional[ET.Element] = None
    stripped = xml_input.strip()
    if stripped.startswith("<"):
        try:
            root = ET.fromstring(stripped)
        except Exception as e:
            return [f"Malformed XML string: {e}"]
    else:
        if not os.path.isfile(xml_input):
            return [f"File not found: {xml_input}"]
        try:
            tree = ET.parse(xml_input)
            root = tree.getroot()
        except Exception as e:
            return [f"Malformed XML file: {e}"]

    ns = {"p": _MSPDI_NS}
    if not root.tag.endswith("Project"):
        errors.append(f"Root element must be Project, got {root.tag}")
        return errors

    save_version = root.findtext("p:SaveVersion", default="", namespaces=ns)
    if not save_version or save_version not in ("1", "14"):
        errors.append(f"Invalid or missing SaveVersion: {save_version!r} (expected '14')")

    start_date = root.findtext("p:StartDate", default="", namespaces=ns)
    finish_date = root.findtext("p:FinishDate", default="", namespaces=ns)
    if not start_date or not finish_date:
        errors.append("Project StartDate or FinishDate is missing")

    calendar_el = root.find(".//p:Calendars/p:Calendar", ns)
    if calendar_el is None:
        errors.append("Missing Calendars/Calendar element")
    else:
        if not calendar_el.findtext("p:UID", default="", namespaces=ns):
            errors.append("Calendar missing UID")
        if not calendar_el.findtext("p:ID", default="", namespaces=ns):
            errors.append("Calendar missing ID")
        for exc in calendar_el.findall(".//p:Exceptions/p:Exception", ns):
            if not exc.findtext("p:UID", default="", namespaces=ns):
                errors.append("Calendar Exception missing UID")
            if not exc.findtext("p:ID", default="", namespaces=ns):
                errors.append("Calendar Exception missing ID")
            tp = exc.find("p:TimePeriod", ns)
            if tp is None:
                errors.append("Calendar Exception missing TimePeriod")
            else:
                f_date = tp.findtext("p:FromDate", default="", namespaces=ns)
                t_date = tp.findtext("p:ToDate", default="", namespaces=ns)
                if not f_date or not t_date:
                    errors.append("Calendar Exception TimePeriod missing FromDate or ToDate")
                elif f_date >= t_date:
                    errors.append(f"Calendar Exception has zero-length or inverted TimePeriod ({f_date} to {t_date})")

    task_els = root.findall(".//p:Tasks/p:Task", ns)
    if not task_els:
        errors.append("Missing Tasks/Task elements")

    task_uids = set()
    summary_task_uids = set()
    tasks_by_wbs: Dict[str, Dict[str, Any]] = {}
    for task_el in task_els:
        uid = task_el.findtext("p:UID", default="", namespaces=ns)
        tid = task_el.findtext("p:ID", default="", namespaces=ns)
        name = task_el.findtext("p:Name", default="", namespaces=ns)
        wbs = task_el.findtext("p:WBS", default="", namespaces=ns)
        summary = task_el.findtext("p:Summary", default="", namespaces=ns)
        start = task_el.findtext("p:Start", default="", namespaces=ns)
        finish = task_el.findtext("p:Finish", default="", namespaces=ns)
        dur = task_el.findtext("p:Duration", default="", namespaces=ns)
        work = task_el.findtext("p:Work", default="", namespaces=ns)
        cost_txt = task_el.findtext("p:Cost", default="", namespaces=ns)
        cost_val = 0.0
        has_cost = bool(cost_txt)
        if cost_txt:
            try:
                cost_val = float(cost_txt)
            except ValueError:
                errors.append(f"Task {name!r} has invalid Cost {cost_txt!r}")

        if not uid:
            errors.append(f"Task {name!r} missing UID")
        else:
            task_uids.add(uid)
            if summary == "1":
                summary_task_uids.add(uid)

        if not tid:
            errors.append(f"Task {name!r} missing ID")
        if not wbs:
            errors.append(f"Task {name!r} missing WBS")
        else:
            work_h = 0.0
            if work:
                m_work = re.match(r"PT(\d+(?:\.\d+)?)H", work)
                if m_work:
                    work_h = float(m_work.group(1))
            tasks_by_wbs[wbs] = {
                "uid": uid,
                "name": name,
                "summary": summary == "1",
                "start": start,
                "finish": finish,
                "dur": dur,
                "work": work,
                "work_hours": work_h,
                "cost": cost_val,
                "has_cost": has_cost,
            }

        for pred in task_el.findall("p:PredecessorLink", ns):
            p_uid = pred.findtext("p:PredecessorUID", default="", namespaces=ns)
            if not p_uid:
                errors.append(f"Task {name!r} has PredecessorLink without PredecessorUID")
            elif p_uid == uid:
                errors.append(f"Task {name!r} has self-referencing PredecessorLink")

        child_tags = [c.tag.split("}")[-1] for c in task_el]
        if "PredecessorLink" in child_tags and "CalendarUID" in child_tags:
            first_pred = child_tags.index("PredecessorLink")
            cal_idx = child_tags.index("CalendarUID")
            if first_pred > cal_idx:
                errors.append(f"Task {name!r} has PredecessorLink after CalendarUID (violates MSPDI sequence order)")
        if "Work" in child_tags and "Cost" in child_tags:
            if child_tags.index("Work") > child_tags.index("Cost"):
                errors.append(f"Task {name!r} has Work after Cost (violates MSPDI sequence order)")
        if "Cost" in child_tags and "PercentComplete" in child_tags:
            if child_tags.index("Cost") > child_tags.index("PercentComplete"):
                errors.append(f"Task {name!r} has Cost after PercentComplete (violates MSPDI sequence order)")

    currency_code = root.findtext("p:CurrencyCode", default="", namespaces=ns)
    currency_symbol = root.findtext("p:CurrencySymbol", default="", namespaces=ns)
    has_uk_context = currency_code == "GBP" or currency_symbol == "£" or "uk" in (root.findtext("p:Name", default="", namespaces=ns) or "").lower()
    if has_uk_context and calendar_el is not None:
        exc_els = calendar_el.findall(".//p:Exceptions/p:Exception", ns)
        if not exc_els:
            s_date = root.findtext("p:StartDate", default="", namespaces=ns)
            f_date = root.findtext("p:FinishDate", default="", namespaces=ns)
            if s_date and f_date and ("-12-" in s_date or "-12-" in f_date or "-01-" in f_date or "-05-" in f_date):
                errors.append("UK bank holiday plan missing Calendar Exceptions")

    # Verify summary rollup consistency
    for wbs, tdata in tasks_by_wbs.items():
        if tdata["summary"]:
            child_wbs_list = [
                cwbs for cwbs in tasks_by_wbs
                if cwbs.startswith(wbs + ".") and len(cwbs.split(".")) == len(wbs.split(".")) + 1
            ]
            if child_wbs_list:
                child_starts = [tasks_by_wbs[cwbs]["start"] for cwbs in child_wbs_list if tasks_by_wbs[cwbs]["start"]]
                child_finishes = [tasks_by_wbs[cwbs]["finish"] for cwbs in child_wbs_list if tasks_by_wbs[cwbs]["finish"]]
                if child_starts and tdata["start"] != min(child_starts):
                    errors.append(f"Summary task {tdata['name']!r} Start ({tdata['start']}) does not match child min Start ({min(child_starts)})")
                if child_finishes and tdata["finish"] != max(child_finishes):
                    errors.append(f"Summary task {tdata['name']!r} Finish ({tdata['finish']}) does not match child max Finish ({max(child_finishes)})")
                child_works = sum(tasks_by_wbs[cwbs]["work_hours"] for cwbs in child_wbs_list)
                if abs(tdata["work_hours"] - child_works) > 0.01:
                    errors.append(f"Summary task {tdata['name']!r} Work ({tdata['work_hours']}h) does not match sum of child work ({child_works}h)")
                if tdata.get("has_cost"):
                    child_costs = sum(tasks_by_wbs[cwbs]["cost"] for cwbs in child_wbs_list)
                    if abs(tdata["cost"] - child_costs) > 0.05:
                        errors.append(f"Summary task {tdata['name']!r} Cost ({tdata['cost']}) does not match sum of child cost ({child_costs})")

    res_uids = set()
    for res_el in root.findall(".//p:Resources/p:Resource", ns):
        r_uid = res_el.findtext("p:UID", default="", namespaces=ns)
        r_id = res_el.findtext("p:ID", default="", namespaces=ns)
        r_name = res_el.findtext("p:Name", default="", namespaces=ns)
        if not r_uid:
            errors.append(f"Resource {r_name!r} missing UID")
        else:
            res_uids.add(r_uid)
        if not r_id:
            errors.append(f"Resource {r_name!r} missing ID")

    for asgn in root.findall(".//p:Assignments/p:Assignment", ns):
        a_uid = asgn.findtext("p:UID", default="", namespaces=ns)
        a_id = asgn.findtext("p:ID", default="", namespaces=ns)
        t_uid = asgn.findtext("p:TaskUID", default="", namespaces=ns)
        r_uid = asgn.findtext("p:ResourceUID", default="", namespaces=ns)
        units = asgn.findtext("p:Units", default="", namespaces=ns)
        work = asgn.findtext("p:Work", default="", namespaces=ns)

        if not a_uid:
            errors.append("Assignment missing UID")
        if not a_id:
            errors.append(f"Assignment {a_uid} missing ID")
        if not t_uid or t_uid not in task_uids:
            errors.append(f"Assignment {a_uid} references invalid TaskUID {t_uid}")
        elif t_uid in summary_task_uids:
            errors.append(f"Assignment {a_uid} targets summary task UID {t_uid}")
        if not r_uid or r_uid not in res_uids:
            errors.append(f"Assignment {a_uid} references invalid ResourceUID {r_uid}")
        if not units:
            errors.append(f"Assignment {a_uid} missing Units")
        if not work:
            errors.append(f"Assignment {a_uid} missing Work")

    # Verify that each leaf task's Work matches the sum of its assignment Work
    asgn_work_by_task: Dict[str, float] = {}
    for asgn in root.findall(".//p:Assignments/p:Assignment", ns):
        t_uid = asgn.findtext("p:TaskUID", default="", namespaces=ns)
        work = asgn.findtext("p:Work", default="", namespaces=ns)
        if work and t_uid:
            m_aw = re.match(r"PT(\d+(?:\.\d+)?)H", work)
            if m_aw:
                asgn_work_by_task[t_uid] = asgn_work_by_task.get(t_uid, 0.0) + float(m_aw.group(1))

    for tdata in tasks_by_wbs.values():
        t_uid = tdata["uid"]
        if not tdata["summary"] and t_uid in asgn_work_by_task:
            if abs(tdata["work_hours"] - asgn_work_by_task[t_uid]) > 0.01:
                errors.append(f"Task {tdata['name']!r} Work ({tdata['work_hours']}h) does not match sum of assignment work ({asgn_work_by_task[t_uid]}h)")

    return errors


def _parse_start_date(start_date: Optional[str]) -> _dt.date:
    if start_date:
        try:
            return _dt.date.fromisoformat(start_date)
        except ValueError:
            pass
    return _dt.date.today()


def _write_output(xml_text: str, filename: str) -> str:
    validation_errors = validate_mspdi_xml(xml_text)
    if validation_errors:
        logger.warning("MSPDI XML validation warnings in %s (%d error(s)): %s", filename, len(validation_errors), validation_errors)
    else:
        logger.info("MSPDI XML validation passed cleanly for %s", filename)
    out_path = paths.output_path(filename)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as file:
        file.write(xml_text)
    logger.info("Wrote MSPDI XML to %s (%d bytes)", out_path, len(xml_text.encode("utf-8")))
    return out_path


def _build_and_write_pert_cpm(
    root_task: "_Task", holidays: FrozenSet[_dt.date], filename: str,
) -> Tuple[Optional[str], Optional[str]]:
    leaves = [t for t in _flatten([root_task]) if not t.is_summary and t.start and t.finish]
    logger.info(
        "_build_and_write_pert_cpm: generating companion PERT/CPM for %r (%d leaf tasks) -> %s",
        root_task.name, len(leaves), filename,
    )
    activities = []
    for i, task in enumerate(leaves):
        gap = 0
        if i > 0:
            gap = max(0, _count_working_days(leaves[i - 1].finish, task.start, holidays) - 2)
        preds = list(task.predecessor_uids)
        if task.predecessor_uid is not None and task.predecessor_uid not in preds:
            preds.append(task.predecessor_uid)
        is_ms = getattr(task, "is_milestone", False) or task.duration_days == 0
        activities.append({
            "uid": task.uid, "name": task.name, "start": task.start, "finish": task.finish,
            "duration_days": 0 if is_ms else max(task.duration_days, 1), "gap_working_days_before": gap,
            "predecessor_uids": preds,
        })
    try:
        path = generate_pert_cpm_diagram(activities, root_task.name, filename)
        logger.info("_build_and_write_pert_cpm: successfully generated PERT/CPM diagram at %s", path)
        return path, None
    except (OSError, ValueError) as e:
        logger.warning("_build_and_write_pert_cpm: could not generate diagram: %s", e)
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
    include_phase_gates: Optional[bool] = None,
) -> str:
    """Exports the current saved Enterprise Agile Portfolio Backlog as an
    MSPDI project plan. Same "ERROR: ..."/"<thing> export failed: ..." string
    convention as vsdx_export.py's own build_* functions -- never raises to
    the caller. `resources` is an optional list of {"name": str,
    "allocation_percent": number} -- neither this nor `target_duration_weeks`/
    `holiday_calendar` exist in the saved backlog JSON; all three are
    supplied by the caller at export time only (see module docstring)."""
    logger.info(
        "build_portfolio_backlog_project_plan: starting export (start_date=%s, target_duration_weeks=%s, holiday_calendar=%s, include_phase_gates=%s)",
        start_date, target_duration_weeks, holiday_calendar, include_phase_gates,
    )
    backlog = load_portfolio_backlog()
    if backlog.get("status") != "OK" or not backlog.get("epics"):
        logger.debug("build_portfolio_backlog_project_plan: no saved portfolio backlog found (status=%s)", backlog.get("status"))
        return "ERROR: No saved portfolio backlog found. Create one first."

    if include_phase_gates is None:
        if backlog.get("include_phase_gates") is not None:
            include_phase_gates = bool(backlog.get("include_phase_gates"))
        elif backlog.get("phase_gates") is not None:
            include_phase_gates = bool(backlog.get("phase_gates"))
        else:
            corpus = " ".join([
                str(backlog.get("name") or ""),
                str(backlog.get("summary") or ""),
                str(backlog.get("notes") or ""),
            ]).lower()
            include_phase_gates = (
                "phase gate" in corpus or "phase gates" in corpus
                or "phase sign-off" in corpus or "phase sign off" in corpus
                or "sign-off milestone" in corpus or "sign off milestone" in corpus
            )

    if not target_duration_weeks and backlog.get("timescale_weeks"):
        try:
            target_duration_weeks = float(backlog["timescale_weeks"])
        except (ValueError, TypeError):
            pass
    if not holiday_calendar:
        if backlog.get("holiday_calendar"):
            holiday_calendar = backlog["holiday_calendar"]
        else:
            try:
                from process_toolkit.requirements_summary import load_requirements_summary
                req = load_requirements_summary()
                if isinstance(req, dict) and req.get("holiday_calendar"):
                    holiday_calendar = req["holiday_calendar"]
            except Exception:
                pass
        if not holiday_calendar:
            corpus = " ".join([
                str(backlog.get("name") or ""),
                str(backlog.get("summary") or ""),
                str(backlog.get("notes") or ""),
                str(backlog.get("source_name") or ""),
            ]).lower()
            has_gbp = any(
                isinstance(entry, dict) and ("£" in str(entry.get("daily_rate", "")) or "gbp" in str(entry).lower() or "£" in str(entry))
                for entry in (backlog.get("rate_card") or [])
            ) or "£" in corpus or "bank holiday" in corpus or "uk " in corpus or "united kingdom" in corpus or "london" in corpus
            if has_gbp:
                holiday_calendar = "uk"

    uid_counter = [0]

    def next_uid() -> int:
        uid_counter[0] += 1
        return uid_counter[0]

    available_roles: list[str] = []
    for src in (backlog.get("rate_card"), backlog.get("roles"), backlog.get("resources")):
        if isinstance(src, list):
            for r in src:
                if isinstance(r, dict):
                    name = str(r.get("role") or r.get("name") or "").strip()
                    if name and name not in available_roles:
                        available_roles.append(name)
                elif isinstance(r, str) and r.strip() and r.strip() not in available_roles:
                    available_roles.append(r.strip())

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
        epic_task.item_id = epic.get("id")
        epic_task.dependencies = epic.get("dependencies") or epic.get("predecessors") or []
        epic_timing = epic.get("timing") or epic.get("weeks") or epic.get("timing_window") or ""
        timing_w_epic = _parse_timing_window(epic_timing)
        if timing_w_epic[0] is not None:
            epic_task.start_week = timing_w_epic[0]
            epic_task.end_week = timing_w_epic[1]
        for feature in epic.get("features") or []:
            feature_task = _Task(
                uid=next_uid(), name=feature.get("title") or feature.get("id") or "Feature",
                outline_level=3, is_summary=True,
            )
            feature_task.item_id = feature.get("id")
            feature_task.dependencies = feature.get("dependencies") or feature.get("predecessors") or []
            feat_timing = feature.get("timing") or feature.get("weeks") or feature.get("timing_window") or ""
            timing_w_feat = _parse_timing_window(feat_timing)
            if timing_w_feat[0] is not None:
                feature_task.start_week = timing_w_feat[0]
                feature_task.end_week = timing_w_feat[1]
            else:
                feature_task.start_week = epic_task.start_week
                feature_task.end_week = epic_task.end_week
            for story in feature.get("stories") or []:
                job_size = story.get("job_size")
                try:
                    points = float(job_size)
                except (TypeError, ValueError):
                    points = 1.0
                is_story_ms = (
                    bool(story.get("milestone"))
                    or bool(story.get("is_milestone"))
                    or str(story.get("type", "")).lower() == "milestone"
                    or job_size == 0
                )
                explicit_days = story.get("duration_days") or story.get("duration_working_days")
                if explicit_days:
                    try:
                        duration_days = max(1, int(explicit_days))
                    except (ValueError, TypeError):
                        duration_days = max(1, round(points * DEFAULT_WORKING_DAYS_PER_POINT))
                else:
                    duration_days = max(1, round(points * DEFAULT_WORKING_DAYS_PER_POINT))
                story_task = _Task(
                    uid=next_uid(), name=story.get("title") or story.get("id") or "Story",
                    outline_level=4, is_summary=False,
                    notes=f"job_size={job_size!r}; illustrative duration only." if not is_story_ms else "Phase milestone.",
                )
                story_task.is_milestone = is_story_ms
                story_task.duration_days = 0 if is_story_ms else duration_days
                story_task.item_id = story.get("id")
                story_task.dependencies = story.get("dependencies") or story.get("predecessors") or []
                story_timing = story.get("timing") or story.get("weeks") or story.get("timing_window") or ""
                timing_w_story = _parse_timing_window(story_timing)
                if timing_w_story[0] is not None:
                    story_task.start_week = timing_w_story[0]
                    story_task.end_week = timing_w_story[1]
                else:
                    story_task.start_week = feature_task.start_week or epic_task.start_week
                    story_task.end_week = feature_task.end_week or epic_task.end_week
                story_res = story.get("resources") or story.get("roles")
                has_explicit = bool(story_res)
                if not story_res:
                    from process_toolkit.portfolio_backlog.portfolio_backlog import calculate_story_resources
                    story_res = calculate_story_resources(story, available_roles=available_roles or None)
                story_task.resources = _normalize_resources(story_res)
                story_task.has_explicit_resources = has_explicit
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
        if include_phase_gates or epic.get("include_phase_gate") or epic.get("gate"):
            epic_leaves = [t for t in _flatten(epic_task.children) if not t.children]
            epic_title = epic.get("title") or epic.get("id") or "Phase"
            gate_task = _Task(
                uid=next_uid(),
                name=f"{epic_title} - Sign-Off & Gate",
                outline_level=3,
                is_summary=False,
                notes=f"Zero-duration milestone and phase gate sign-off for {epic_title}.",
            )
            gate_task.is_milestone = True
            gate_task.duration_days = 0
            gate_task.item_id = f"{epic.get('id', 'EPIC')}-GATE"
            if epic_leaves:
                gate_task.predecessor_uids = [epic_leaves[-1].uid]
            epic_task.children.append(gate_task)
        root.children.append(epic_task)

    project_start = _parse_start_date(start_date)
    holidays = _resolve_holidays(holiday_calendar, project_start)
    _schedule_task_tree(root, _first_working_day_on_or_after(project_start, holidays), holidays, target_duration_weeks)

    overrun_warning = _duration_overrun_warning(root, target_duration_weeks)
    if overrun_warning:
        root.notes = f"{root.notes}\n\n{overrun_warning}"
    if backlog.get("capacity_notes"):
        root.notes = f"{root.notes}\n\n{backlog['capacity_notes']}".strip()

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
    from process_toolkit.portfolio_backlog.portfolio_backlog import ROLE_BENCHMARK_RATES, resolve_backlog_currency
    for r_name, (daily, _) in ROLE_BENCHMARK_RATES.items():
        rates_by_name.setdefault(r_name, daily / _WORK_HOURS_PER_DAY)

    currency_code = backlog.get("currency")
    currency_symbol = backlog.get("currency_symbol")
    if not currency_code:
        currency_code, currency_symbol = resolve_backlog_currency(backlog)

    caller_resources = _normalize_resources(resources)
    normalized_resources = _normalize_resources(resources or backlog.get("roles") or backlog.get("resources"))
    xml_text = _render_mspdi(
        root.name, [root], root.start or project_start, holidays, normalized_resources, rates_by_name, caller_resources,
        currency_code=currency_code, currency_symbol=currency_symbol,
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


def _parse_timing_window(timing: str) -> Tuple[Optional[int], Optional[int], int]:
    """Parses free-text timing (e.g. "Weeks 2-4", "Week 1", "Weeks 11-12 (10 days)")
    into (start_week, end_week, duration_working_days)."""
    if not isinstance(timing, str) or not timing.strip():
        return None, None, _DEFAULT_PHASE_DURATION_DAYS

    match = _WEEK_RANGE_RE.search(timing)
    if match:
        start_week, end_week = int(match.group(1)), int(match.group(2))
        span_weeks = max(1, end_week - start_week + 1)
        return start_week, end_week, span_weeks * _WORKING_DAYS_PER_WEEK

    match = _WEEK_SINGLE_RE.search(timing)
    if match:
        week = int(match.group(1))
        return week, week, _WORKING_DAYS_PER_WEEK

    return None, None, _parse_timing_to_days(timing)


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
    logger.info(
        "build_proposal_response_project_plan: starting export (start_date=%s, target_duration_weeks=%s, holiday_calendar=%s)",
        start_date, target_duration_weeks, holiday_calendar,
    )
    response = load_proposal_response()
    if response.get("status") != "OK" or not response.get("implementation_plan"):
        logger.debug("build_proposal_response_project_plan: no saved proposal response found (status=%s)", response.get("status"))
        return "ERROR: No saved proposal response found. Create one first."

    uid_counter = [0]

    def next_uid() -> int:
        uid_counter[0] += 1
        return uid_counter[0]

    available_roles: list[str] = []
    for src in (response.get("rate_card"), response.get("roles"), response.get("resources")):
        if isinstance(src, list):
            for r in src:
                if isinstance(r, dict):
                    name = str(r.get("role") or r.get("name") or "").strip()
                    if name and name not in available_roles:
                        available_roles.append(name)
                elif isinstance(r, str) and r.strip() and r.strip() not in available_roles:
                    available_roles.append(r.strip())

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
        timing_w = _parse_timing_window(timing_text)
        phase_task.duration_days = timing_w[2]
        if timing_w[0] is not None:
            phase_task.start_week = timing_w[0]
        if phase.get("dependencies") or phase.get("predecessors"):
            phase_task.dependencies = phase.get("dependencies") or phase.get("predecessors") or []
        phase_task.item_id = phase.get("id") or phase.get("phase")
        if phase.get("resources"):
            phase_task.resources = _normalize_resources(phase.get("resources"))
        root.children.append(phase_task)

    if not root.children:
        return "ERROR: No saved proposal response found. Create one first."

    if not holiday_calendar:
        if response.get("holiday_calendar"):
            holiday_calendar = response["holiday_calendar"]
        else:
            corpus = " ".join([
                str(response.get("name") or ""),
                str(response.get("summary") or ""),
            ]).lower()
            has_gbp = any(
                isinstance(entry, dict) and ("£" in str(entry.get("daily_rate", "")) or "gbp" in str(entry).lower() or "£" in str(entry))
                for entry in (response.get("rate_card") or [])
            ) or "£" in corpus or "bank holiday" in corpus or "uk " in corpus or "united kingdom" in corpus or "london" in corpus
            if has_gbp:
                holiday_calendar = "uk"

    project_start = _parse_start_date(start_date)
    holidays = _resolve_holidays(holiday_calendar, project_start)
    _schedule_task_tree(root, _first_working_day_on_or_after(project_start, holidays), holidays, target_duration_weeks)

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
    from process_toolkit.portfolio_backlog.portfolio_backlog import ROLE_BENCHMARK_RATES, resolve_backlog_currency
    for r_name, (daily, _) in ROLE_BENCHMARK_RATES.items():
        rates_by_name_proposal.setdefault(r_name, daily / _WORK_HOURS_PER_DAY)

    currency_code = response.get("currency")
    currency_symbol = response.get("currency_symbol")
    if not currency_code:
        currency_code, currency_symbol = resolve_backlog_currency(response)

    caller_resources = _normalize_resources(resources)
    normalized_resources = _normalize_resources(resources or response.get("roles") or response.get("resources"))
    xml_text = _render_mspdi(
        root.name, [root], root.start or project_start, holidays, normalized_resources, rates_by_name_proposal, caller_resources,
        currency_code=currency_code, currency_symbol=currency_symbol,
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

        pred_uids = [
            p.text for p in task_el.findall("p:PredecessorLink/p:PredecessorUID", ns) if p.text
        ]
        predecessor_uid = pred_uids[0] if pred_uids else None
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
        task_cost_text = task_el.findtext("p:Cost", default="", namespaces=ns)
        if task_cost_text:
            try:
                task_cost = float(task_cost_text)
            except ValueError:
                task_cost = None
        else:
            task_cost_vals = [a["cost"] for a in task_assigns if a.get("cost") is not None]
            task_cost = round(sum(task_cost_vals), 2) if task_cost_vals else None

        is_milestone = (task_el.findtext("p:Milestone", default="0", namespaces=ns) or "0") == "1"

        tasks.append({
            "uid": task_uid,
            "name": (task_el.findtext("p:Name", default="", namespaces=ns) or "").strip(),
            "outline_level": outline_level,
            "is_summary": (task_el.findtext("p:Summary", default="0", namespaces=ns) or "0") == "1",
            "is_milestone": is_milestone,
            "start": task_el.findtext("p:Start", default="", namespaces=ns) or None,
            "finish": task_el.findtext("p:Finish", default="", namespaces=ns) or None,
            "duration_hours": duration_hours,
            "predecessor_uid": predecessor_uid,
            "predecessor_uids": pred_uids,
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
    if total_cost is None and tasks and tasks[0].get("cost") is not None:
        total_cost = tasks[0]["cost"]

    return {
        "title": title,
        "start_date": start_date,
        "finish_date": finish_date,
        "tasks": tasks,
        "resources": resources,
        "assignments": assignments,
        "total_cost": total_cost,
    }
