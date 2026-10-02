# codeDoc/generate_diagrams.py
#
# Renders the physical PNG diagrams in this directory from hand-verified
# source facts (see class-inventory.md / class-hierarchy.md /
# application-classes.md / adk-composition.md for the evidence each shape
# and arrow here is based on). Pure matplotlib, no Graphviz/PlantUML
# binary required -- the same approach this codebase's own
# process_agents/common/uml_diagram_agent.py already uses for runtime
# design-document diagrams, applied here to the codebase's own structure
# instead of a generated document's content.
#
# Re-run after a structural change (a new class, a changed pipeline
# sub_agents list) to regenerate the PNGs:
#   cd samples/GCP/ProcessEngineering && .venv/bin/python codeDoc/generate_diagrams.py

import math
import os

import matplotlib.pyplot as plt
import matplotlib.patches as patches

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# NOTE ON COORDINATES: every diagram below uses ax.invert_yaxis(), so
# smaller data-y is higher on screen and larger data-y is lower. A box's
# (x, y) is always its VISUAL TOP-LEFT corner; its header band therefore
# spans y .. y+header_h, and its body spans y+header_h .. y+h -- the
# opposite of matplotlib's default (non-inverted) convention.

HEADER_FS = 9
BODY_FS = 7.4
LINE_H = 0.30          # body text line height, in data units
HEADER_LINE_H = 0.34
CHAR_W = 0.092          # approx monospace character width at BODY_FS, in data units


def _text_width(s: str) -> float:
    return len(s) * CHAR_W


def _box_size_for(header_lines, body_lines, min_w=2.2):
    header_h = HEADER_LINE_H * len(header_lines) + 0.22
    body_h = (LINE_H * len(body_lines) + 0.20) if body_lines else 0.0
    w = max(
        [min_w] + [_text_width(l) + 0.55 for l in header_lines]
        + [len(l) * CHAR_W * 0.82 + 0.4 for l in (body_lines or [])]
    )
    return w, header_h + body_h, header_h


# ======================================================================
# SHARED PRIMITIVES
# ======================================================================

def _box(ax, x, y, header_lines, body_lines=None, *, facecolor="white",
          header_color="#dbe8f9", w=None, h=None, header_h=None):
    """Box with visual TOP-LEFT corner at (x, y) (see coordinate note
    above): a shaded header band on top, optional monospace body text
    below it. Returns (x, y, w, h) for use with _relation()."""
    if w is None or h is None or header_h is None:
        w, h, header_h = _box_size_for(header_lines, body_lines)

    ax.add_patch(patches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.1, edgecolor="black", facecolor=facecolor, zorder=2,
    ))
    # Header band (top of the box, since this axis is y-inverted).
    ax.add_patch(patches.FancyBboxPatch(
        (x, y), w, header_h, boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.1, edgecolor="black", facecolor=header_color, zorder=3,
    ))
    if body_lines:
        # Square off the header band's bottom corners so it reads as one
        # box with a flat divider, not two stacked pills.
        ax.add_patch(patches.Rectangle(
            (x, y + header_h * 0.6), w, header_h * 0.4,
            linewidth=0, facecolor=header_color, zorder=3,
        ))
        ax.plot([x, x + w], [y + header_h, y + header_h], color="black", linewidth=1.1, zorder=4)

    for i, line in enumerate(header_lines):
        ax.text(
            x + w / 2, y + HEADER_LINE_H * (i + 0.5) + (header_h - HEADER_LINE_H * len(header_lines)) / 2,
            line, ha="center", va="center", fontsize=HEADER_FS, fontweight="bold", zorder=5,
        )
    if body_lines:
        for i, line in enumerate(body_lines):
            ax.text(
                x + 0.12, y + header_h + 0.12 + LINE_H * i, line,
                ha="left", va="top", fontsize=BODY_FS, family="monospace", zorder=5,
            )
    return (x, y, w, h)


def _box_edge_point(box, toward):
    """Point on `box`'s perimeter closest to `toward`, so connector lines
    touch a box's edge rather than passing through its center."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    tx, ty = toward
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return (cx, y)
    scale_candidates = []
    if dx != 0:
        scale_candidates.append((w / 2) / abs(dx))
    if dy != 0:
        scale_candidates.append((h / 2) / abs(dy))
    s = min(scale_candidates)
    return (cx + dx * s, cy + dy * s)


def _hollow_triangle(ax, tip, direction, size=0.22, color="black"):
    angle = math.atan2(direction[1], direction[0])
    back = (tip[0] - size * 1.7 * math.cos(angle), tip[1] - size * 1.7 * math.sin(angle))
    perp = (-math.sin(angle), math.cos(angle))
    p2 = (back[0] + perp[0] * size * 0.65, back[1] + perp[1] * size * 0.65)
    p3 = (back[0] - perp[0] * size * 0.65, back[1] - perp[1] * size * 0.65)
    ax.add_patch(patches.Polygon([tip, p2, p3], closed=True, facecolor="white",
                                   edgecolor=color, linewidth=1.3, zorder=6))
    return back


def _filled_diamond(ax, tip, direction, size=0.15, color="black"):
    angle = math.atan2(direction[1], direction[0])
    ux, uy = math.cos(angle), math.sin(angle)
    px, py = -uy, ux
    back = (tip[0] - ux * size * 2.1, tip[1] - uy * size * 2.1)
    mid = (tip[0] - ux * size * 1.05, tip[1] - uy * size * 1.05)
    left = (mid[0] + px * size * 0.85, mid[1] + py * size * 0.85)
    right = (mid[0] - px * size * 0.85, mid[1] - py * size * 0.85)
    ax.add_patch(patches.Polygon([tip, left, back, right], closed=True, facecolor=color,
                                   edgecolor=color, linewidth=1.0, zorder=6))
    return back


def _relation(ax, src_box, dst_box, kind, label=None, curve=0.0):
    """kind: "inherit" (solid, hollow triangle at dst/base), "compose"
    (solid, filled diamond at src/owner), or "depends" (dashed, open
    arrow at dst)."""
    src_c = (src_box[0] + src_box[2] / 2, src_box[1] + src_box[3] / 2)
    dst_c = (dst_box[0] + dst_box[2] / 2, dst_box[1] + dst_box[3] / 2)
    p_src = _box_edge_point(src_box, dst_c)
    p_dst = _box_edge_point(dst_box, src_c)

    direction = (p_dst[0] - p_src[0], p_dst[1] - p_src[1])
    norm = math.hypot(*direction) or 1
    direction = (direction[0] / norm, direction[1] / norm)

    if kind == "inherit":
        line_end = _hollow_triangle(ax, p_dst, direction)
        line_start = p_src
    elif kind == "compose":
        line_start = _filled_diamond(ax, p_src, direction)
        line_end = p_dst
    else:
        line_start, line_end = p_src, p_dst

    linestyle = (0, (4, 3)) if kind == "depends" else "-"

    if curve == 0.0:
        ax.plot([line_start[0], line_end[0]], [line_start[1], line_end[1]],
                 color="black", linewidth=1.1, linestyle=linestyle, zorder=1)
        lx = (line_start[0] + line_end[0]) / 2
        ly = (line_start[1] + line_end[1]) / 2
    else:
        conn = f"arc3,rad={curve}"
        ax.annotate("", xy=line_end, xytext=line_start,
                     arrowprops=dict(arrowstyle="-", color="black", linewidth=1.1,
                                      linestyle=linestyle, connectionstyle=conn, shrinkA=0, shrinkB=0),
                     zorder=1)
        lx = (line_start[0] + line_end[0]) / 2 + curve * (line_end[1] - line_start[1]) * 0.5
        ly = (line_start[1] + line_end[1]) / 2 - curve * (line_end[0] - line_start[0]) * 0.5

    if kind == "depends":
        ax.annotate("", xy=line_end, xytext=(line_end[0] - (line_end[0] - line_start[0]) * 0.06,
                                               line_end[1] - (line_end[1] - line_start[1]) * 0.06),
                     arrowprops=dict(arrowstyle="-|>", color="black", linewidth=1.1), zorder=6)

    if label:
        ax.text(lx, ly, label, fontsize=6.6, ha="center", va="center",
                 bbox=dict(facecolor="white", edgecolor="#999", alpha=0.95, pad=1.5), zorder=7)


def _legend(ax, x, y, title="Relationship key"):
    ax.text(x, y, title, fontsize=9, fontweight="bold", ha="left", va="top")
    rows = [
        ("inherit", "solid + hollow triangle -> base class (declared base)"),
        ("compose", "solid + filled diamond at owner (construction / typed field)"),
        ("depends", "dashed + open arrow (configuration / runtime dependency)"),
    ]
    yy = y + 0.45
    for kind, desc in rows:
        x0, x1 = x, x + 0.7
        if kind == "inherit":
            ax.plot([x0, x1], [yy, yy], color="black", linewidth=1.1)
            _hollow_triangle(ax, (x1, yy), (1, 0), size=0.17)
        elif kind == "compose":
            ax.plot([x0, x1], [yy, yy], color="black", linewidth=1.1)
            _filled_diamond(ax, (x0, yy), (-1, 0), size=0.14)
        else:
            ax.plot([x0, x1], [yy, yy], color="black", linewidth=1.1, linestyle=(0, (4, 3)))
            ax.annotate("", xy=(x1, yy), xytext=(x1 - 0.1, yy),
                         arrowprops=dict(arrowstyle="-|>", color="black", linewidth=1.1))
        ax.text(x1 + 0.25, yy, desc, fontsize=7.6, ha="left", va="center")
        yy += 0.5


def _finish(fig, ax, out_name, xlim, ylim, title):
    ax.axis("off")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.invert_yaxis()
    fig.suptitle(title, fontsize=13)
    out = os.path.join(OUT_DIR, out_name)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


# ======================================================================
# DIAGRAM 1: APPLICATION CLASS DIAGRAM
# Source: codeDoc/application-classes.md.
# ======================================================================

def generate_class_diagram():
    fig, ax = plt.subplots(figsize=(20, 15.5))
    B = {}

    def add(key, x, y, header, body=None, external=False):
        B[key] = _box(ax, x, y, header, body,
                       facecolor="#f0f0f0" if external else "white",
                       header_color="#cfcfcf" if external else "#dbe8f9")

    # Tier A -- external bases (inheritance targets)
    add("ADK_LlmAgent", 0.3, 0.3, ["LlmAgent", "(google.adk.agents)"], external=True)
    add("ADK_Agent", 4.0, 0.3, ["Agent", "(google.adk.agents, alias of LlmAgent)"], external=True)
    add("ADK_BaseAgent", 9.0, 0.3, ["BaseAgent", "(google.adk.agents)"], external=True)
    add("Pydantic_BaseModel", 14.0, 0.3, ["BaseModel", "(pydantic)"], external=True)
    add("Requests_HTTPAdapter", 17.3, 0.3, ["HTTPAdapter", "(requests.adapters)"], external=True)

    # Tier B -- application classes with a direct declared base
    add("DefaultLlmAgent", 0.3, 2.6, ["DefaultLlmAgent"],
        ["common/agent_wrappers.py:434", "+__init__(name, model,", " instruction, sub_agents)"])
    add("DefaultAgent", 4.0, 2.6, ["DefaultAgent"],
        ["common/agent_wrappers.py:531", "+__init__(name, model,", " instruction, sub_agents)"])
    add("DocCreationAgent", 7.7, 2.6, ["DocCreationAgent"],
        ["common/doc_creation_agent.py:48", "+pipeline: Optional[SequentialAgent]",
         "+__init__(name)", "+_run_async_impl(ctx)"])
    add("SubprocessDriverAgent", 12.1, 2.6, ["SubprocessDriverAgent"],
        ["process/subprocess_driver_agent.py:30", "+per_step_pipeline: SequentialAgent",
         "+_load_process_steps()", "+_run_async_impl(ctx)"])
    add("SubprocessWriterAgent", 16.6, 2.6, ["SubprocessWriterAgent"],
        ["process/subprocess_writer_agent.py:24", "+__init__(name)", "+_run_async_impl(ctx)"])
    add("JitterAdapter", 20.3, 2.6, ["JitterAdapter"],
        ["common/grounding_agent.py:126", "+sleep(sleep_time)"])

    _relation(ax, B["DefaultLlmAgent"], B["ADK_LlmAgent"], "inherit")
    _relation(ax, B["DefaultAgent"], B["ADK_Agent"], "inherit")
    _relation(ax, B["DocCreationAgent"], B["ADK_BaseAgent"], "inherit", curve=-0.12)
    _relation(ax, B["SubprocessDriverAgent"], B["ADK_BaseAgent"], "inherit")
    _relation(ax, B["SubprocessWriterAgent"], B["ADK_BaseAgent"], "inherit", curve=0.18)
    _relation(ax, B["JitterAdapter"], B["Requests_HTTPAdapter"], "inherit", curve=-0.2)

    # Tier C -- ADK_SequentialAgent: built by DocCreationAgent /
    # SubprocessDriverAgent, and itself contains fresh DefaultLlmAgent /
    # SubprocessWriterAgent instances.
    add("ADK_SequentialAgent", 9.6, 5.6, ["SequentialAgent", "(google.adk.agents)"], external=True)
    _relation(ax, B["DocCreationAgent"], B["ADK_SequentialAgent"], "compose",
              "builds & stores pipeline", curve=0.15)
    _relation(ax, B["SubprocessDriverAgent"], B["ADK_SequentialAgent"], "compose",
              "per_step_pipeline", curve=-0.15)
    _relation(ax, B["ADK_SequentialAgent"], B["DefaultLlmAgent"], "compose",
              "edge-inference / doc-gen /\nsubprocess-generator instances", curve=0.35)
    _relation(ax, B["ADK_SequentialAgent"], B["SubprocessWriterAgent"], "compose",
              "subprocess writer instance", curve=-0.3)

    # Tier D -- pydantic schema cluster
    add("SubprocessFlow", 4.6, 9.0, ["SubprocessFlow"],
        ["process/subprocess_generator_agent.py:67", "+step_name: str",
         "+subprocess_flow: List[SubprocessStep]"])
    add("SubprocessStep", 9.6, 9.0, ["SubprocessStep"],
        ["process/subprocess_generator_agent.py:31", "+substep_name, description: str",
         "+responsible_party: str", "+inputs, outputs: List[str]",
         "+dependencies: List[str]", "+step_risks_and_controls:",
         "   List[StepRiskControl]", "+change_management:",
         "   List[ChangeManagement]", "+continuous_improvement:",
         "   List[ContinuousImprovement]"])

    _relation(ax, B["Pydantic_BaseModel"], B["SubprocessFlow"], "inherit", curve=-0.3)
    _relation(ax, B["Pydantic_BaseModel"], B["SubprocessStep"], "inherit", curve=-0.15)
    _relation(ax, B["DefaultLlmAgent"], B["SubprocessFlow"], "depends", "output_schema", curve=-0.35)
    _relation(ax, B["SubprocessFlow"], B["SubprocessStep"], "compose", "subprocess_flow  0..*")

    # Tier E -- SubprocessStep's own composed value objects
    add("StepRiskControl", 4.0, 14.3, ["StepRiskControl"],
        ["subprocess_generator_agent.py:19", "+risk: str", "+control: str"])
    add("ChangeManagement", 8.0, 14.3, ["ChangeManagement"],
        ["subprocess_generator_agent.py:23", "+change_request_process: str", "+versioning_rules: str"])
    add("ContinuousImprovement", 12.6, 14.3, ["ContinuousImprovement"],
        ["subprocess_generator_agent.py:27", "+review_frequency: str", "+improvement_inputs: List[str]"])

    _relation(ax, B["Pydantic_BaseModel"], B["StepRiskControl"], "inherit", curve=-0.45)
    _relation(ax, B["Pydantic_BaseModel"], B["ChangeManagement"], "inherit", curve=-0.35)
    _relation(ax, B["Pydantic_BaseModel"], B["ContinuousImprovement"], "inherit", curve=-0.25)
    _relation(ax, B["SubprocessStep"], B["StepRiskControl"], "compose", "0..*")
    _relation(ax, B["SubprocessStep"], B["ChangeManagement"], "compose", "0..*")
    _relation(ax, B["SubprocessStep"], B["ContinuousImprovement"], "compose", "0..*")

    # Standalone classes -- no declared base, no relationship to anything
    # else in the inventory.
    add("_Box", 17.3, 9.0, ["_Box  (no base)"],
        ["cloudarch/cloudarch_layout_agent.py:149", "+id: str", "+x, y, w, h: float",
         "+zone_id: Optional[str]", "+row, order: int", "+stack: str",
         "+cx(), cy(), right(), bottom()"])
    add("CleanedStdout", 17.3, 12.4, ["CleanedStdout  (no base)"],
        ["common/utils.py:3395", "+file", "+__init__(path)", "+write(text)", "+flush()"])
    ax.text(17.3, 8.55, "Standalone -- no base, no relations to the rest of the inventory",
             fontsize=7.6, style="italic", color="#555")

    _legend(ax, 0.3, 17.0)

    _finish(
        fig, ax, "class-diagram.png", (0, 23.6), (-0.3, 18.6),
        "ProcessEngineering -- application class diagram\n"
        "(13 project classes; external ADK/Pydantic/requests bases shown in gray)",
    )


# ======================================================================
# SEQUENCE DIAGRAMS
# Source: adk-composition.md plus direct verification against each
# pipeline module's sub_agents=[...] assembly (file:line noted per
# diagram below). Arrows show EXECUTION ORDER through the parent
# SequentialAgent/LoopAgent's sub_agents list, not literal Python method
# calls between siblings -- the actual caller in every case is the ADK
# orchestrator object (SequentialAgent/LoopAgent), which is omitted as
# its own lifeline for readability since it never does anything but
# dispatch to the next child in order.
# ======================================================================

PART_HEADER_COLOR = "#dbe8f9"
LOOP_HEADER_COLOR = "#fef7e0"

def _participant(ax, x, header_lines, body_lines=None, *, loop=False):
    box = _box(ax, x, 0.0, header_lines, body_lines,
               header_color=LOOP_HEADER_COLOR if loop else PART_HEADER_COLOR)
    bx, by, bw, bh = box
    cx = bx + bw / 2
    return box, cx


def _draw_lifeline(ax, cx, top_h, bottom_y):
    ax.plot([cx, cx], [top_h, bottom_y], color="gray", linestyle="--", linewidth=1, zorder=0)


def _message(ax, x0, x1, y, label, *, dashed=False, number=None):
    style = (0, (4, 3)) if dashed else "-"
    if x0 == x1:
        # Self-call loop.
        w = 0.5
        ax.plot([x0, x0 + w, x0 + w], [y, y, y + 0.3], color="black", linewidth=1.2, linestyle=style, zorder=2)
        ax.annotate("", xy=(x0, y + 0.3), xytext=(x0 + 0.08, y + 0.3),
                     arrowprops=dict(arrowstyle="-|>", color="black", linewidth=1.2), zorder=2)
        lx, ha = x0 + w + 0.15, "left"
        ly = y + 0.1
    else:
        ax.annotate("", xy=(x1, y), xytext=(x0, y),
                     arrowprops=dict(arrowstyle="-|>", color="black", linewidth=1.2, linestyle=style), zorder=2)
        lx, ha = (x0 + x1) / 2, "center"
        ly = y - 0.08
    text = f"{number}. {label}" if number is not None else label
    ax.text(lx, ly, text, fontsize=7.6, ha=ha, va="bottom",
             bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=1.5), zorder=3)


def _loop_frame(ax, x0, x1, y0, y1, label):
    pad = 0.35
    ax.add_patch(patches.Rectangle(
        (x0 - pad, y0 - 0.3), (x1 - x0) + 2 * pad, (y1 - y0) + 0.6,
        linewidth=1.2, edgecolor="#b36b00", facecolor="none", linestyle=(0, (5, 3)), zorder=0,
    ))
    tab_w = min(3.0, _text_width(label) + 0.5)
    ax.add_patch(patches.Polygon(
        [(x0 - pad, y0 - 0.3), (x0 - pad + tab_w, y0 - 0.3), (x0 - pad + tab_w, y0 - 0.0),
         (x0 - pad + tab_w - 0.18, y0 + 0.2), (x0 - pad, y0 + 0.2)],
        closed=True, facecolor="#fef7e0", edgecolor="#b36b00", linewidth=1.2, zorder=1,
    ))
    ax.text(x0 - pad + 0.1, y0 - 0.05, label, fontsize=7.2, fontweight="bold",
             ha="left", va="top", color="#7a4a00", zorder=2)


def generate_sequence_diagram(out_name, title, subtitle, participants, steps, loops=(), figsize=(16, 7)):
    """
    participants: list of (key, header_lines, body_lines, is_loop) tuples,
      left to right.
    steps: list of (from_key, to_key, label) or (from_key, to_key, label,
      {"dashed": True}) tuples, top to bottom.
    loops: list of (from_key, to_key, label, (step_idx_lo, step_idx_hi))
      spans to bracket with a dashed UML loop frame -- from_key/to_key
      give the x-extent, the explicit step index range gives the
      y-extent (0-indexed into `steps`, inclusive), so the frame brackets
      exactly the repeating messages and not the one-time entry/exit
      arrows around them.
    """
    fig, ax = plt.subplots(figsize=figsize)

    x = 0.3
    centers = {}
    boxes = {}
    for key, header, body, is_loop in participants:
        box, cx = _participant(ax, x, header, body, loop=is_loop)
        centers[key] = cx
        boxes[key] = box
        x = box[0] + box[2] + 0.9

    header_bottom = max(b[1] + b[3] for b in boxes.values())
    step_gap = 0.85
    y0 = header_bottom + 0.8
    step_ys = {}
    y = y0
    for i, step in enumerate(steps):
        step_ys[i] = y
        y += step_gap
    bottom = y + 0.3

    for key, cx in centers.items():
        _draw_lifeline(ax, cx, header_bottom, bottom)

    for i, step in enumerate(steps):
        from_key, to_key, label = step[0], step[1], step[2]
        opts = step[3] if len(step) > 3 else {}
        _message(ax, centers[from_key], centers[to_key], step_ys[i], label,
                  dashed=opts.get("dashed", False), number=opts.get("number"))

    for from_key, to_key, label, step_range in loops:
        idx_lo, idx_hi = step_range
        xs = [centers[from_key], centers[to_key]]
        _loop_frame(ax, min(xs), max(xs), step_ys[idx_lo] - 0.65, step_ys[idx_hi], label)

    full_title = title + ("\n" + subtitle if subtitle else "")
    _finish(fig, ax, out_name, (-0.3, x - 0.2), (-0.3, bottom + 0.3), full_title)


def generate_cloudarch_sequence():
    # Source: process_agents/cloudarch/cloudarch_pipeline_agent.py:101-114
    # (cloudarch_review_loop = LoopAgent(sub_agents=[cloudarch_agent,
    # cloudarch_reviewer_agent, stop_controller_agent_instance],
    # max_iterations=SAFE_LOOP_ITERS)).
    participants = [
        ("root", ["Root Orchestrator"], ["common/agent.py", "root_agent"], False),
        ("gen", ["CloudArch_Agent"], ["cloudarch/cloudarch_agent.py", "generates/refines the", "drawio diagram"], False),
        ("rev", ["CloudArch_Reviewer_Agent"], ["cloudarch/cloudarch_reviewer_agent.py", "audits security/cost/", "resilience/observability"], False),
        ("stop", ["Stop_Controller", "(CloudArch clone)"], ["common/utils_agent.py", "checks cloudarch_status", "in approval.json"], False),
    ]
    steps = [
        ("root", "gen", "route: \"generate cloud architecture\"", {"number": 1}),
        ("gen", "gen", "save_drawio_structured() /\nsave_drawio()", {"number": 2}),
        ("gen", "rev", "hand off saved diagram", {"number": 3}),
        ("rev", "rev", "load_drawio() + audit", {"number": 4}),
        ("rev", "stop", "save_iteration_feedback\n(cloudarch_status)", {"number": 5}),
        ("stop", "stop", "stop_if_ready()", {"number": 6}),
        ("stop", "gen", "REVISION REQUIRED -> repeat", {"number": 7, "dashed": True}),
        ("stop", "root", "CLOUDARCH APPROVED\n(or max iterations) -> exit loop", {"number": 8, "dashed": True}),
    ]
    generate_sequence_diagram(
        "sequence-cloudarch-pipeline.png",
        "CloudArch_Pipeline sequence",
        "cloudarch/cloudarch_pipeline_agent.py -- LoopAgent over generator / reviewer / stop controller",
        participants, steps,
        loops=[("gen", "stop", "loop  [until CLOUDARCH APPROVED, max 2x (loopIterations)]", (1, 6))],
        figsize=(13, 8.5),
    )


def _collapsed_review_loop(key, title, lines, max_iters_note="x2 max (loopIterations)"):
    return (key, [title], lines + [max_iters_note], True)


def generate_process_create_sequence():
    # Source: process_agents/process/create_process_agent.py:94-174.
    participants = [
        ("root", ["Root Orchestrator"], ["common/agent.py"], False),
        ("mute", ["Mute_Agent"], ["common/utils_agent.py", "redirect stdout to log file"], False),
        ("analysis", ["Analysis_Agent"], ["process/analysis_agent.py", "extract requirements JSON"], False),
        _collapsed_review_loop("review", "Design_Compliance_Loop", [
            "process/create_process_agent.py:116",
            "Design -> Compliance -> Design",
            "-> Simulation -> Design",
            "-> [Grounding -> Design] -> Stop",
        ]),
        _collapsed_review_loop("norm", "JSON_Normalization_Retry_Loop", [
            "create_process_agent.py:148",
            "JSON_Normalizer -> JSON_Review",
            "-> Stop",
        ]),
        ("subproc", ["SubprocessDriverAgent"], ["process/subprocess_driver_agent.py", "per process step:", "Generator -> Writer"], False),
        ("doc", ["DocCreationAgent"], ["common/doc_creation_agent.py", "Edge_Inference ->", "Doc_Generation"], False),
        ("unmute", ["Unmute_Agent"], ["common/utils_agent.py", "restore real stdout"], False),
    ]
    steps = [
        ("root", "mute", 'route: "create a process"', {"number": 1}),
        ("mute", "analysis", "console muted", {"number": 2}),
        ("analysis", "review", "requirements JSON ready", {"number": 3}),
        ("review", "norm", "process JSON approved", {"number": 4}),
        ("norm", "subproc", "process JSON normalized\n& persisted", {"number": 5}),
        ("subproc", "doc", "per-step subprocesses\npersisted", {"number": 6}),
        ("doc", "unmute", "documents generated", {"number": 7}),
        ("unmute", "root", "pipeline complete", {"number": 8, "dashed": True}),
    ]
    generate_sequence_diagram(
        "sequence-process-create.png",
        "Full_Design_Pipeline sequence (process creation)",
        "process/create_process_agent.py -- SequentialAgent; loop stages collapsed (see their own module for full agent-level detail)",
        participants, steps, figsize=(19, 7.5),
    )


def generate_process_update_sequence():
    # Source: process_agents/process/update_process_agent.py:174-259.
    participants = [
        ("root", ["Root Orchestrator"], ["common/agent.py"], False),
        ("mute", ["Mute_Agent"], ["common/utils_agent.py"], False),
        ("analysis", ["Process_Update_Analyst"], ["process/update_process_agent.py:62", "diff requested change vs", "existing baseline"], False),
        _collapsed_review_loop("review", "Update_Compliance_Loop", [
            "update_process_agent.py:212",
            "Design -> Compliance -> Design",
            "-> Simulation -> Design",
            "-> [Grounding -> Design] -> Stop",
        ]),
        _collapsed_review_loop("norm", "Update_Normalization_Loop", [
            "update_process_agent.py:234",
            "JSON_Normalizer -> JSON_Review",
            "-> Stop",
        ]),
        ("subproc", ["SubprocessDriverAgent", "(Update instance)"], ["subprocess_driver_agent.py", "per changed step:", "Generator -> Writer"], False),
        ("doc", ["DocCreationAgent"], ["common/doc_creation_agent.py", "Edge_Inference ->", "Doc_Generation"], False),
        ("unmute", ["Unmute_Agent"], ["common/utils_agent.py"], False),
    ]
    steps = [
        ("root", "mute", 'route: "update the process"', {"number": 1}),
        ("mute", "analysis", "console muted", {"number": 2}),
        ("analysis", "review", "change delta identified", {"number": 3}),
        ("review", "norm", "updated process JSON\napproved", {"number": 4}),
        ("norm", "subproc", "process JSON normalized\n& persisted", {"number": 5}),
        ("subproc", "doc", "per-step subprocesses\nregenerated", {"number": 6}),
        ("doc", "unmute", "documents regenerated", {"number": 7}),
        ("unmute", "root", "pipeline complete", {"number": 8, "dashed": True}),
    ]
    generate_sequence_diagram(
        "sequence-process-update.png",
        "Update_Design_Pipeline sequence (process update)",
        "process/update_process_agent.py -- SequentialAgent; loop stages collapsed",
        participants, steps, figsize=(19, 7.5),
    )


def generate_design_doc_create_sequence():
    # Source: process_agents/design/design_doc_create_agent.py:166-263.
    participants = [
        ("root", ["Root Orchestrator"], ["common/agent.py"], False),
        ("mute", ["Mute_DesignDoc_Create"], ["common/utils_agent.py clone"], False),
        ("analysis", ["Design_Doc_Analysis", "_Agent"], ["design/design_doc_analysis_agent.py", "extract architectural", "requirements JSON"], False),
        _collapsed_review_loop("review", "Design_Doc_Compliance_Loop", [
            "design_doc_create_agent.py:191",
            "HLD -> LLD -> Compliance",
            "-> Refine -> Simulation",
            "-> Refine -> [Grounding",
            "-> Refine] -> Stop",
        ]),
        _collapsed_review_loop("norm", "Design_Doc_JSON", [
            "_Normalization_Loop",
            "design_doc_create_agent.py:238",
            "JSON_Normalizer -> JSON_Review",
            "-> Stop",
        ]),
        ("doc", ["DocCreationAgent"], ["common/doc_creation_agent.py", "Edge_Inference ->", "Doc_Generation"], False),
        ("unmute", ["Unmute_DesignDoc_Create"], ["common/utils_agent.py clone"], False),
    ]
    steps = [
        ("root", "mute", 'route: "create a design document"', {"number": 1}),
        ("mute", "analysis", "console muted", {"number": 2}),
        ("analysis", "review", "architectural\nrequirements JSON ready", {"number": 3}),
        ("review", "norm", "HLD/LLD JSON approved", {"number": 4}),
        ("norm", "doc", "design JSON normalized\n& persisted", {"number": 5}),
        ("doc", "unmute", "documents generated", {"number": 6}),
        ("unmute", "root", "pipeline complete", {"number": 7, "dashed": True}),
    ]
    generate_sequence_diagram(
        "sequence-design-doc-create.png",
        "Full_Design_Doc_Pipeline sequence (HLD/LLD creation)",
        "design/design_doc_create_agent.py -- SequentialAgent; no subprocess stage (process-only concept); loop stages collapsed",
        participants, steps, figsize=(17.5, 8),
    )


def generate_design_doc_update_sequence():
    # Source: process_agents/design/design_doc_update_agent.py (same
    # shape as design_doc_create_agent.py; see that module's section
    # markers at the line numbers noted below).
    participants = [
        ("root", ["Root Orchestrator"], ["common/agent.py"], False),
        ("mute", ["Mute_DesignDoc_Update"], ["common/utils_agent.py clone"], False),
        ("analysis", ["Design_Doc_Update", "_Analyst"], ["design_doc_update_agent.py:67", "diff requested change vs", "existing baseline"], False),
        _collapsed_review_loop("review", "Design_Doc_Update", [
            "_Compliance_Loop",
            "design_doc_update_agent.py:245",
            "HLD -> LLD -> Compliance",
            "-> Refine -> Simulation",
            "-> Refine -> [Grounding",
            "-> Refine] -> Stop",
        ]),
        _collapsed_review_loop("norm", "Design_Doc_Update", [
            "_Normalization_Loop",
            "design_doc_update_agent.py:270",
            "JSON_Normalizer -> JSON_Review",
            "-> Stop",
        ]),
        ("doc", ["DocCreationAgent"], ["common/doc_creation_agent.py", "Edge_Inference ->", "Doc_Generation"], False),
        ("unmute", ["Unmute_DesignDoc_Update"], ["common/utils_agent.py clone"], False),
    ]
    steps = [
        ("root", "mute", 'route: "update the design document"', {"number": 1}),
        ("mute", "analysis", "console muted", {"number": 2}),
        ("analysis", "review", "change delta identified", {"number": 3}),
        ("review", "norm", "updated HLD/LLD JSON\napproved", {"number": 4}),
        ("norm", "doc", "design JSON normalized\n& persisted", {"number": 5}),
        ("doc", "unmute", "documents regenerated", {"number": 6}),
        ("unmute", "root", "pipeline complete", {"number": 7, "dashed": True}),
    ]
    generate_sequence_diagram(
        "sequence-design-doc-update.png",
        "Update_Design_Doc_Pipeline sequence (HLD/LLD update)",
        "design/design_doc_update_agent.py -- SequentialAgent; no subprocess stage; loop stages collapsed",
        participants, steps, figsize=(17.5, 8),
    )


if __name__ == "__main__":
    generate_class_diagram()
    generate_cloudarch_sequence()
    generate_process_create_sequence()
    generate_process_update_sequence()
    generate_design_doc_create_sequence()
    generate_design_doc_update_sequence()
