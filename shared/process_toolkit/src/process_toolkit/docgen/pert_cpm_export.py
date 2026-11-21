"""Renders a PERT activity-on-node network diagram as a real PNG image --
same rendering stack and visual language as this module's own sibling
diagram generators (`proposal_roadmap_diagram.py`'s single-row, left-to-
right card timeline with directional arrows is the closest match: a header
banner, one card per activity, `matplotlib`'s `Agg` backend, saved via
`plt.savefig`). Deliberately NOT mxGraph/draw.io XML -- that format has no
real use here (no third-party draw.io client benefit, and the web client
would have had to invent a new renderer for it) when this codebase already
has a proven, in-use PNG pipeline for exactly this kind of diagram
(`docgen/uml_diagrams.py`, `docgen/step_diagrams.py`,
`docgen/proposal_architecture_diagram.py` all follow the same pattern).

Pure function of an already-scheduled activity list -- no knowledge of
which schema (portfolio backlog vs proposal response) produced it; the
caller (`docgen.project_plan_export`) owns flattening the real task tree
down to leaf (non-summary) activities in chronological order and computing
each one's own `gap_working_days_before` (the number of working days of
slack between the PREVIOUS activity's finish and this one's start -- 0 when
they're back-to-back) using its own holiday-aware `_count_working_days`, so
this module stays holiday-agnostic and trivially unit-testable with plain
synthetic dates. `generate_pert_cpm_diagram` DOES own its own file I/O
(unlike a pure XML-string builder would) -- it takes `filename` and saves
directly via `paths.output_path`, the same shape as
`generate_proposal_roadmap_diagram`'s own `out_path = paths.output_path(...);
plt.savefig(out_path, ...); return out_path`.

Computes a genuine CPM backward pass over the chain (not a hardcoded
"everything is critical" shortcut): the LAST activity's own Early Finish
anchors Late Finish (float 0 by definition -- nothing follows it to create
slack against), and each earlier activity's Late Finish/float is set from
the ACTUAL gap before its successor PLUS whatever float that successor
already has (a delay absorbed by shared downstream slack, not just the
immediate gap). Today's scheduler (`docgen.project_plan_export.
_schedule_subtree`) always produces a single serial chain with zero gaps --
so float will currently always be zero, and every activity will be
"critical" -- but this is computed honestly from the real gaps the caller
supplies, not hardcoded, so it would correctly show non-zero float and a
non-critical activity the moment any caller passes a
`gap_working_days_before` greater than zero.
"""

import datetime as _dt
from typing import Any, Dict, List

import matplotlib as mpl
# Must be set before pyplot is imported -- same reasoning as
# proposal_roadmap_diagram.py's/edge_inference.py's own identical line
# (thread-safety: this can run inside asyncio.to_thread, and Agg is the
# only backend safe to use with no display/event loop of its own).
mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle  # noqa: E402

from process_toolkit import paths
from process_toolkit.docgen.diagram_style import add_fitted_text, fit_title

_CARD_WIDTH, _CARD_HEIGHT = 2.9, 2.3
_X_SPACING = 3.35

_CRITICAL_COLOR = "#C0392B"
_SLACK_COLOR = "#5C6B7A"


def generate_pert_cpm_diagram(activities: List[Dict[str, Any]], title: str, filename: str) -> str:
    """`activities`: chronologically ordered dicts, each {"uid", "name",
    "start": date, "finish": date, "duration_days": int,
    "gap_working_days_before": int} (the first activity's own
    `gap_working_days_before` is ignored -- there is nothing before it).
    Renders the diagram and saves it to output/<filename>. Returns the
    saved path.

    Raises ValueError if `activities` is empty -- same no-fabrication
    convention proposal_roadmap_diagram.py's own generate_proposal_
    roadmap_diagram already follows for an empty plan; the caller's own
    responsibility not to call this with nothing to render."""
    if not activities:
        raise ValueError("No activities to render a PERT/CPM diagram from.")
    scored = _compute_cpm(activities)
    all_critical = all(a["critical"] for a in scored)

    positions = [(i * _X_SPACING, 0.0) for i in range(len(scored))]
    x_min, x_max = positions[0][0], positions[-1][0]
    left, right = x_min - _CARD_WIDTH / 2 - 1.1, x_max + _CARD_WIDTH / 2 + 1.1
    if right - left < 9.0:
        extra_padding = (9.0 - (right - left)) / 2
        left -= extra_padding
        right += extra_padding
    # Single row (all cards at y=0) -- banner tall enough for title + the
    # legend line explaining the critical-path styling, same margin-formula
    # discipline proposal_roadmap_diagram.py's own header block uses.
    bottom, top = -_CARD_HEIGHT / 2 - 0.35, _CARD_HEIGHT / 2 + 1.85
    plot_width, plot_height = right - left, top - bottom

    fig_width = min(14.0, max(9.0, plot_width * 0.72))
    fig_height = fig_width * plot_height / plot_width
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor="#F4F7FB")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_facecolor("#F4F7FB")
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect("equal", adjustable="box")

    # Header banner.
    ax.add_patch(FancyBboxPatch(
        (left, top - 1.65), plot_width, 1.65,
        boxstyle="round,pad=0.02,rounding_size=0.16",
        facecolor="#14243A", edgecolor="none", zorder=1,
    ))
    ax.text(
        left + 0.35, top - 0.47, "PERT / CPM NETWORK",
        color="#77D6C1", fontsize=9, fontweight="bold", va="center",
        ha="left", zorder=2,
    )
    fit_title(
        ax, str(title or "Project Plan"), left + 0.35, top - 0.91, plot_width - 4.5,
        color="white", fontweight="bold", ha="left", zorder=2,
    )
    ax.text(
        right - 0.3, top - 0.72, f"{len(scored):02d} ACTIVITIES",
        color="#D3DFEC", fontsize=8, fontweight="bold", va="center",
        ha="right", zorder=2,
    )
    if all_critical:
        legend = (
            "No parallel work streams in this plan -- every activity runs strictly after the "
            "previous one, so the entire sequence IS the critical path (zero float throughout)."
        )
    else:
        legend = (
            "Red-bordered activities are on the critical path (zero float); gray-bordered "
            "activities have slack before they would delay the plan."
        )
    add_fitted_text(
        ax, legend, left + 0.35, top - 1.32, plot_width - 0.7, 0.38,
        fontsize=8.5, min_fontsize=6.5, color="#A9BBCF", ha="left", zorder=2,
    )

    node_boxes = []
    for index, (activity, (x, y)) in enumerate(zip(scored, positions)):
        color = _CRITICAL_COLOR if activity["critical"] else _SLACK_COLOR
        box = FancyBboxPatch(
            (x - _CARD_WIDTH / 2, y - _CARD_HEIGHT / 2),
            _CARD_WIDTH, _CARD_HEIGHT,
            boxstyle="round,pad=0.04,rounding_size=0.13",
            facecolor="white", edgecolor=color,
            linewidth=2.2 if activity["critical"] else 1.1,
            zorder=3,
        )
        ax.add_patch(box)
        node_boxes.append(box)

        ax.add_patch(Circle(
            (x - _CARD_WIDTH / 2 + 0.24, y + 0.78), 0.14,
            facecolor=color, edgecolor="none", zorder=4,
        ))
        ax.text(
            x - _CARD_WIDTH / 2 + 0.24, y + 0.78, f"{index + 1:02d}",
            color="white", fontsize=6.5, fontweight="bold",
            ha="center", va="center", zorder=5,
        )
        add_fitted_text(
            ax, activity["name"], x - _CARD_WIDTH / 2 + 0.48, y + 0.78,
            _CARD_WIDTH - 0.72, 0.5, fontsize=9, min_fontsize=6.5,
            color="#1C2D43", fontweight="bold", ha="left", zorder=5,
        )
        add_fitted_text(
            ax, f"{activity['start'].isoformat()} → {activity['finish'].isoformat()}",
            x - _CARD_WIDTH / 2 + 0.22, y + 0.24,
            _CARD_WIDTH - 0.44, 0.3, fontsize=7.5, min_fontsize=5.5,
            color="#64758A", ha="left", zorder=5,
        )
        add_fitted_text(
            ax, f"Duration {activity['duration_days']}d  ·  Float {activity['float_days']}d",
            x - _CARD_WIDTH / 2 + 0.22, y - 0.08,
            _CARD_WIDTH - 0.44, 0.3, fontsize=7.5, min_fontsize=5.5,
            color="#64758A", ha="left", zorder=5,
        )
        ax.add_patch(FancyBboxPatch(
            (x - _CARD_WIDTH / 2 + 0.22, y - _CARD_HEIGHT / 2 + 0.16),
            1.3, 0.34,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            facecolor=color, edgecolor="none", zorder=4,
        ))
        ax.text(
            x - _CARD_WIDTH / 2 + 0.22 + 0.65, y - _CARD_HEIGHT / 2 + 0.33,
            "CRITICAL" if activity["critical"] else "HAS SLACK",
            color="white", fontsize=7, fontweight="bold",
            ha="center", va="center", zorder=5,
        )

    for i in range(len(scored) - 1):
        ax.add_patch(FancyArrowPatch(
            positions[i], positions[i + 1],
            patchA=node_boxes[i], patchB=node_boxes[i + 1],
            arrowstyle="-|>", mutation_scale=13,
            color="#7C91AA", linewidth=1.55, alpha=0.9,
            shrinkA=4, shrinkB=4, zorder=2,
        ))

    ax.axis("off")

    out_path = paths.output_path(filename)
    plt.savefig(out_path, dpi=220, facecolor="#F4F7FB")
    plt.close(fig)
    return out_path


def _compute_cpm(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Genuine backward pass, not a hardcoded shortcut -- see module
    docstring. Returns a NEW list of dicts (does not mutate the input),
    each carrying everything the input had plus "late_start", "late_finish",
    "float_days", "critical"."""
    scored = [dict(a) for a in activities]
    # Forward times (ES/EF) are already the given start/finish -- this
    # module trusts the caller's own schedule rather than recomputing it.
    scored[-1]["late_finish"] = scored[-1]["finish"]
    scored[-1]["float_days"] = 0
    for i in range(len(scored) - 2, -1, -1):
        # Activity i's own float is the gap BEFORE its successor PLUS
        # whatever float the successor itself already has -- delaying i by
        # up to that gap doesn't move the successor's own start at all, and
        # once it would, i is really just borrowing the successor's own
        # already-available slack instead. Dropping the "+ successor's
        # float" term (an earlier version of this function did) silently
        # understates float for every activity before a gap, not just the
        # one immediately next to it.
        gap = scored[i + 1].get("gap_working_days_before", 0)
        scored[i]["float_days"] = gap + scored[i + 1]["float_days"]
        scored[i]["late_finish"] = scored[i]["finish"] + _dt.timedelta(days=scored[i]["float_days"])
    for activity in scored:
        duration = max(activity["duration_days"], 1)
        activity["late_start"] = activity["late_finish"] - _dt.timedelta(days=duration - 1)
        activity["critical"] = activity["float_days"] == 0
    return scored
