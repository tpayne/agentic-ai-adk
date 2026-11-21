"""Builds a PERT activity-on-node network diagram, in the same mxGraph/
draw.io XML format `process_toolkit.cloudarch.layout`'s own
`build_structured_drawio_xml` already produces (the same `<mxfile>/
<diagram>/<mxGraphModel>/<root>` shape, the same `<mxCell vertex="1">`/
`<mxCell edge="1">` conventions) -- deliberately a separate, much simpler
writer rather than calling into that module's zone/icon/edge-routing
machinery, which is purpose-built for architecture diagrams with zones and
icons; a PERT chart has neither. Reusing the OUTPUT FORMAT (so this file is
openable in a real draw.io client and the web client's existing
`parseDrawioXml`/`renderGraphDiagram` needs zero new code to display it)
without reusing the CODE is the same "duplicate rather than share"
discipline `docgen/vsdx_export.py`'s own `_compute_layout` already
documents for itself.

Pure function of an already-scheduled activity list -- no file I/O, no
knowledge of which schema (portfolio backlog vs proposal response) produced
it. The caller (`docgen.project_plan_export`) is responsible for flattening
the real task tree down to leaf (non-summary) activities in chronological
order and computing each one's own `gap_working_days_before` (the number of
working days of slack between the PREVIOUS activity's finish and this one's
start -- 0 when they're back-to-back) using its own holiday-aware
`_count_working_days`, so this module stays holiday-agnostic and trivially
unit-testable with plain synthetic dates.

Computes a genuine CPM backward pass over the chain (not a hardcoded
"everything is critical" shortcut): the LAST activity's own Early Finish
anchors Late Finish (float 0 by definition -- nothing follows it to create
slack against), and each earlier activity's Late Finish is set from the
ACTUAL gap before its successor, so float reflects real schedule slack, not
an assumption. Today's scheduler (`docgen.project_plan_export.
_schedule_subtree`) always produces a single serial chain with zero gaps --
so float will currently always be zero, and every activity will be
"critical" -- but this is computed honestly from the real gaps the caller
supplies, not hardcoded, so it would correctly show non-zero float and a
non-critical activity the moment any caller passes a
`gap_working_days_before` greater than zero.
"""

import datetime as _dt
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

_BOX_WIDTH = 200
_BOX_HEIGHT = 110
_BOX_GAP = 60
_ROW_Y = 90  # vertical offset below the header/legend banner
_HEADER_HEIGHT = 70
_PAGE_MARGIN = 20

_CRITICAL_STYLE = (
    "rounded=1;arcSize=6;fillColor=#FDEDEC;strokeColor=#C0392B;strokeWidth=2.5;"
    "html=1;whiteSpace=wrap;align=left;spacingLeft=10;spacingTop=6;verticalAlign=top;fontSize=11;"
)
_NONCRITICAL_STYLE = (
    "rounded=1;arcSize=6;fillColor=#FFFFFF;strokeColor=#9AA0A6;strokeWidth=1;"
    "html=1;whiteSpace=wrap;align=left;spacingLeft=10;spacingTop=6;verticalAlign=top;fontSize=11;"
)
_EDGE_STYLE = "rounded=0;html=1;startArrow=none;endArrow=classic;strokeColor=#5f6368;strokeWidth=1.6;"
_HEADER_STYLE = (
    "rounded=1;arcSize=4;fillColor=#FFFFFF;strokeColor=#4285F4;strokeWidth=1.5;"
    "html=1;whiteSpace=wrap;align=left;spacingLeft=16;verticalAlign=middle;fontSize=12;"
)


def build_pert_cpm_drawio_xml(activities: List[Dict[str, Any]], title: str) -> str:
    """`activities`: chronologically ordered dicts, each {"uid", "name",
    "start": date, "finish": date, "duration_days": int,
    "gap_working_days_before": int} (the first activity's own
    `gap_working_days_before` is ignored -- there is nothing before it).
    Returns the XML text. Never raises on an empty `activities` list --
    an empty plan is a legitimate, if unusual, state, not an error this
    function should surface."""
    scored = _compute_cpm(activities)

    mxfile = ET.Element("mxfile", {"host": "Electron"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "pert_cpm", "name": (title or "PERT/CPM")[:40]})
    canvas_w = max(
        _PAGE_MARGIN * 2 + _BOX_WIDTH,
        _PAGE_MARGIN * 2 + (len(scored) * (_BOX_WIDTH + _BOX_GAP) - _BOX_GAP if scored else _BOX_WIDTH),
    )
    canvas_h = _PAGE_MARGIN * 2 + _ROW_Y + _BOX_HEIGHT
    graph_model = ET.SubElement(diagram, "mxGraphModel", {
        "dx": "1600", "dy": "900", "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": str(int(canvas_w)), "pageHeight": str(int(canvas_h)),
        "math": "0", "shadow": "0", "background": "#FFFFFF",
    })
    root = ET.SubElement(graph_model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    all_critical = all(a["critical"] for a in scored) if scored else True
    # No manual HTML-entity escaping anywhere in this function -- `value`
    # is an XML ATTRIBUTE, and ET.tostring's own attribute serialization
    # already escapes &/</>/" exactly once when it writes the file (the
    # same reasoning cloudarch/layout.py's own title_value/zone-label
    # construction already relies on -- confirmed directly: escaping here
    # too produced double-escaped text, e.g. "&amp;" becoming "&amp;amp;").
    display_title = title or "Project Plan"
    if not scored:
        legend_text = f"<b>{display_title} -- PERT / CPM Network</b><br/>No activities to schedule."
    elif all_critical:
        legend_text = (
            f"<b>{display_title} -- PERT / CPM Network</b><br/>"
            "<span style=\"font-size:10.5px;color:#5f6368\">This plan has no parallel work "
            "streams -- every activity runs strictly after the previous one, so the entire "
            "sequence IS the critical path (zero float throughout).</span>"
        )
    else:
        legend_text = (
            f"<b>{display_title} -- PERT / CPM Network</b><br/>"
            "<span style=\"font-size:10.5px;color:#5f6368\">Activities outlined in red are on "
            "the critical path (zero float); others have slack before they'd delay the plan.</span>"
        )
    header_cell = ET.SubElement(root, "mxCell", {
        "id": "pert_cpm_header", "value": legend_text, "vertex": "1", "parent": "1",
        "style": _HEADER_STYLE,
    })
    ET.SubElement(header_cell, "mxGeometry", {
        "x": str(_PAGE_MARGIN), "y": str(_PAGE_MARGIN),
        "width": str(int(canvas_w - 2 * _PAGE_MARGIN)), "height": str(_HEADER_HEIGHT),
        "as": "geometry",
    })

    for i, activity in enumerate(scored):
        cell_id = f"activity_{activity['uid']}"
        x = _PAGE_MARGIN + i * (_BOX_WIDTH + _BOX_GAP)
        y = _PAGE_MARGIN + _ROW_Y
        badge_color = "#C0392B" if activity["critical"] else "#5f6368"
        badge_text = "CRITICAL" if activity["critical"] else "HAS SLACK"
        value = (
            f"<b>{activity['name']}</b><br/>"
            f"<span style=\"font-size:10px\">{activity['start'].isoformat()} &#8594; "
            f"{activity['finish'].isoformat()}</span><br/>"
            f"<span style=\"font-size:10px\">Duration {activity['duration_days']}d &middot; "
            f"Float {activity['float_days']}d</span><br/>"
            f"<span style=\"font-size:10px;font-weight:700;color:{badge_color}\">{badge_text}</span>"
        )
        cell = ET.SubElement(root, "mxCell", {
            "id": cell_id, "value": value, "vertex": "1", "parent": "1",
            "style": _CRITICAL_STYLE if activity["critical"] else _NONCRITICAL_STYLE,
        })
        ET.SubElement(cell, "mxGeometry", {
            "x": str(x), "y": str(y), "width": str(_BOX_WIDTH), "height": str(_BOX_HEIGHT),
            "as": "geometry",
        })
        if i > 0:
            prev_id = f"activity_{scored[i - 1]['uid']}"
            edge_cell = ET.SubElement(root, "mxCell", {
                "id": f"edge_{i}", "value": "", "edge": "1", "parent": "1",
                "source": prev_id, "target": cell_id, "style": _EDGE_STYLE,
            })
            ET.SubElement(edge_cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode")


def _compute_cpm(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Genuine backward pass, not a hardcoded shortcut -- see module
    docstring. Returns a NEW list of dicts (does not mutate the input),
    each carrying everything the input had plus "late_start", "late_finish",
    "float_days", "critical"."""
    if not activities:
        return []
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
