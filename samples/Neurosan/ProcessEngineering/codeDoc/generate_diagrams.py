# codeDoc/generate_diagrams.py
#
# Renders the physical PNG diagrams in this directory from hand-verified
# source facts (see class-inventory.md / class-hierarchy.md /
# application-classes.md / network-composition.md for the evidence each
# shape and arrow here is based on). Pure matplotlib, no Graphviz/PlantUML
# binary required -- the same approach this codebase's own
# coded_tools/common/docgen/uml_diagrams.py already uses for runtime
# design-document diagrams, applied here to the codebase's own structure
# instead of a generated document's content. The shared drawing primitives
# below are adapted from samples/GCP/ProcessEngineering/codeDoc/generate_diagrams.py
# (the ADK original's own equivalent script) -- they're generic matplotlib
# utility code with nothing ADK-specific in them.
#
# Re-run after a structural change (a new CodedTool class, a changed
# front-man tool list) to regenerate the PNGs:
#   cd samples/Neurosan/ProcessEngineering && uv run python codeDoc/generate_diagrams.py

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
    ]
    yy = y + 0.45
    for kind, desc in rows:
        x0, x1 = x, x + 0.7
        if kind == "inherit":
            ax.plot([x0, x1], [yy, yy], color="black", linewidth=1.1)
            _hollow_triangle(ax, (x1, yy), (1, 0), size=0.17)
        else:
            ax.plot([x0, x1], [yy, yy], color="black", linewidth=1.1)
            _filled_diamond(ax, (x0, yy), (-1, 0), size=0.14)
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
    fig, ax = plt.subplots(figsize=(20, 12.5))
    B = {}
    GAP = 0.8

    def add(key, x, y, header, body=None, external=False):
        box = _box(ax, x, y, header, body,
                    facecolor="#f0f0f0" if external else "white",
                    header_color="#cfcfcf" if external else "#dbe8f9")
        B[key] = box
        return box

    def row_after(prev_box, gap=GAP):
        return prev_box[0] + prev_box[2] + gap

    # Tier A -- the 29 near-identical CodedTool leaves, collapsed into one
    # cluster box per network area (see application-classes.md for why:
    # each one is a 1-method invoke()/async_invoke() wrapper around a
    # shared coded_tools/common/*.py function, individually declared --
    # not actually one shared class). Laid out left-to-right using each
    # box's own actual returned width, not hand-guessed x coordinates, so
    # wide label text can never overlap its neighbor.
    row_y = 2.6
    x = 0.3
    b = add("CloudarchTools", x, row_y, ["Cloudarch tools (7)"],
            ["ResetLoopStateCodedTool", "LoadIterationFeedbackCodedTool",
             "SaveIterationFeedbackCodedTool", "LoadDrawioCodedTool",
             "SaveDrawioStructuredCodedTool", "SimulateCloudarchArchitectureCodedTool",
             "LoadMasterProcessJsonCodedTool"])
    x = row_after(b)
    b = add("ProcessTools", x, row_y, ["Process tools (9)"],
            ["LoadMasterProcessJsonCodedTool", "LoadProcessTemplateCodedTool",
             "ValidateProcessJsonCodedTool", "PersistFinalJsonCodedTool",
             "GenerateProcessFlowDiagramCodedTool", "LoadProcessStepsCodedTool",
             "SaveSubprocessFlowCodedTool", "SimulateProcessPerformanceCodedTool",
             "PerformSensitivityAnalysisCodedTool", "GenerateProcessDocumentCodedTool"])
    x = row_after(b)
    b = add("DesignTools", x, row_y, ["Design tools (9)"],
            ["GenerateDesignFlowDiagramCodedTool", "LoadMasterDesignJsonCodedTool",
             "LoadDesignTemplateCodedTool", "LoadFullDesignContextCodedTool",
             "ValidateDesignJsonCodedTool", "PersistFinalDesignJsonCodedTool",
             "SimulateDesignArchitectureCodedTool", "PerformDesignSensitivityAnalysisCodedTool",
             "GenerateDesignDocumentCodedTool"])
    x = row_after(b)
    b = add("RequirementsSummaryTools", x, row_y, ["Requirements-summary tools (3)"],
            ["LoadDirectoryContextCodedTool", "SaveRequirementsSummaryCodedTool",
             "LoadRequirementsSummaryCodedTool"])
    x = row_after(b)
    add("LoopControlCodedTool", x, row_y, ["LoopControlCodedTool"],
        ["common/loop_control.py:76", "+invoke(args, sly_data)", "-_load_count()",
         "-_save_count(count)", "-_load_approval_state()"])

    row_right_edge = B["LoopControlCodedTool"][0] + B["LoopControlCodedTool"][2]
    row_tallest_bottom = max(B[k][1] + B[k][3] for k in
                              ("CloudarchTools", "ProcessTools", "DesignTools",
                               "RequirementsSummaryTools", "LoopControlCodedTool"))

    # External base, centered above the row, with enough clearance that
    # none of the five fan-in arrows below it overlap a cluster box.
    add("CodedTool", (row_right_edge - 4.5) / 2, 0.3,
        ["CodedTool", "(neuro_san.interfaces.coded_tool)"], external=True)
    for key in ("CloudarchTools", "ProcessTools", "DesignTools", "RequirementsSummaryTools", "LoopControlCodedTool"):
        _relation(ax, B[key], B["CodedTool"], "inherit", curve=0.0)

    # Tier B -- _Box, standalone, no base, no relations to anything else here.
    b_box_y = row_tallest_bottom + 1.2
    add("_Box", 0.3, b_box_y, ["_Box  (no base)"],
        ["cloudarch/cloudarch_layout_engine.py:157", "+id: str", "+x, y, w, h: float",
         "+zone_id: Optional[str]", "+row, order: int", "+stack: str",
         "+cx(), cy(), right(), bottom()"])
    ax.text(0.3, b_box_y - 0.25, "Standalone -- no base, no relations to the rest of the inventory",
             fontsize=7.6, style="italic", color="#555")

    # Tier B (continued) -- the cli.py composition story: MessageProcessor
    # base + LiveTraceMessageProcessor, and ChatSession's own composed
    # neuro-san client objects. Its own self-contained sub-row, well clear
    # of _Box and the tool-cluster row above.
    cli_row_y = b_box_y
    x = row_after(B["_Box"], gap=2.2)
    b = add("MessageProcessor", x, cli_row_y,
            ["MessageProcessor", "(neuro_san.message.processors, external)"], external=True)
    x = row_after(b)
    add("LiveTraceMessageProcessor", x, cli_row_y, ["LiveTraceMessageProcessor"],
        ["cli.py:164", "+process_message(", "  chat_message_dict,", "  message_type)"])
    _relation(ax, B["LiveTraceMessageProcessor"], B["MessageProcessor"], "inherit")

    compose_row_y = max(B["_Box"][1] + B["_Box"][3], B["LiveTraceMessageProcessor"][1] + B["LiveTraceMessageProcessor"][3]) + 1.2
    x = row_after(B["_Box"], gap=0.0)
    b = add("AgentSessionFactory", x, compose_row_y, ["AgentSessionFactory", "(neuro_san.client, external)"], external=True)
    x = row_after(b)
    add("StreamingInputProcessor", x, compose_row_y, ["StreamingInputProcessor", "(neuro_san.client, external)"], external=True)

    chat_session_y = compose_row_y + 1.9
    chat_x = B["AgentSessionFactory"][0]
    add("ChatSession", chat_x, chat_session_y, ["ChatSession  (no base)"],
        ["cli.py:233", "+agent_name: str", "+session", "+input_processor:",
         "   StreamingInputProcessor", "+sly_data: Optional[Dict]", "+chat_context: Optional[Dict]",
         "+__init__(agent_name)", "+send(text) -> str"])

    _relation(ax, B["ChatSession"], B["AgentSessionFactory"], "compose", "creates self.session", curve=-0.2)
    _relation(ax, B["ChatSession"], B["StreamingInputProcessor"], "compose", "self.input_processor", curve=0.2)
    _relation(ax, B["StreamingInputProcessor"], B["LiveTraceMessageProcessor"], "compose",
              "added via get_message_processor()\n.add_processor()", curve=-0.3)

    _legend(ax, row_right_edge - 4.3, 0.3)

    max_x = max(B[k][0] + B[k][2] for k in B)
    max_y = max(B[k][1] + B[k][3] for k in B)
    _finish(
        fig, ax, "class-diagram.png", (0, max_x + 0.5), (-0.3, max_y + 0.8),
        "ProcessEngineering (neuro-san port) -- application class diagram\n"
        "(33 project classes; 29 near-identical CodedTool leaves collapsed into 5 cluster boxes; "
        "external neuro-san bases shown in gray)",
    )


# ======================================================================
# SEQUENCE DIAGRAMS
# Source: network-composition.md plus direct verification against each
# network's own front-man "instructions"/"tools" in registries/*.hocon
# (file noted per diagram below). Arrows show the ORDER a front-man's own
# instructions call its tools in, not literal Python method calls -- the
# actual caller in every case is the LLM itself, re-evaluating those
# instructions on every turn; there is no runtime object enforcing the
# sequence the way ADK's SequentialAgent/LoopAgent did (see the main
# README's "Why neuro-san needed a different design for the generate/
# review loop").
# ======================================================================

PART_HEADER_COLOR = "#dbe8f9"
LOOP_HEADER_COLOR = "#fef7e0"
TOOL_HEADER_COLOR = "#f3e8fd"

def _participant(ax, x, header_lines, body_lines=None, *, loop=False, tool=False):
    color = LOOP_HEADER_COLOR if loop else (TOOL_HEADER_COLOR if tool else PART_HEADER_COLOR)
    box = _box(ax, x, 0.0, header_lines, body_lines, header_color=color)
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
    participants: list of (key, header_lines, body_lines, kind) tuples,
      left to right, kind one of "agent"/"loop"/"tool".
    steps: list of (from_key, to_key, label) or (from_key, to_key, label,
      {"dashed": True}) tuples, top to bottom.
    loops: list of (from_key, to_key, label, (step_idx_lo, step_idx_hi))
      spans to bracket with a dashed loop frame.
    """
    fig, ax = plt.subplots(figsize=figsize)

    x = 0.3
    centers = {}
    boxes = {}
    for key, header, body, kind in participants:
        box, cx = _participant(ax, x, header, body, loop=(kind == "loop"), tool=(kind == "tool"))
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
    # Source: registries/cloudarch.hocon -- CloudArch_Pipeline's own
    # "instructions"/"tools": ["reset_loop_state", "CloudArch_Agent",
    # "CloudArch_Reviewer_Agent", "loop_control"].
    participants = [
        ("root", ["CloudArch_Pipeline"], ["registries/cloudarch.hocon", "front-man"], "agent"),
        ("reset", ["reset_loop_state"], ["ResetLoopStateCodedTool"], "tool"),
        ("gen", ["CloudArch_Agent"], ["generates/refines the", "drawio diagram"], "agent"),
        ("rev", ["CloudArch_Reviewer_Agent"], ["audits security/cost/", "resilience/observability"], "agent"),
        ("loopctl", ["loop_control"], ["LoopControlCodedTool"], "tool"),
    ]
    steps = [
        ("root", "reset", "reset stale approval/\niteration state", {"number": 1}),
        ("root", "gen", "generate/refine diagram\n(save_drawio_structured)", {"number": 2}),
        ("root", "rev", "audit current diagram\n(load_drawio + save_iteration_feedback)", {"number": 3}),
        ("root", "loopctl", "required={cloudarch_status:\nAPPROVED}, max_iterations=2", {"number": 4}),
        ("loopctl", "gen", "CONTINUE -> repeat 2-4", {"number": 5, "dashed": True}),
        ("loopctl", "root", "STOP (APPROVED or\nMAX_ITERATIONS) -> report", {"number": 6, "dashed": True}),
    ]
    generate_sequence_diagram(
        "sequence-cloudarch-pipeline.png",
        "CloudArch_Pipeline sequence",
        "registries/cloudarch.hocon -- front-man's own instructions; loop convention via loop_control, not a runtime LoopAgent",
        participants, steps,
        loops=[("gen", "loopctl", "loop  [until CLOUDARCH APPROVED, max 2x]", (1, 3))],
        figsize=(14, 8),
    )


def generate_process_create_sequence():
    # Source: registries/process.hocon -- Process_Pipeline's own
    # "instructions"/"tools".
    participants = [
        ("root", ["Process_Pipeline"], ["registries/process.hocon", "front-man"], "agent"),
        ("reset", ["reset_loop_state"], [], "tool"),
        ("analysis", ["Analysis_Agent"], ["extract requirements JSON"], "agent"),
        ("design", ["Design_Agent"], ["build/revise process JSON"], "agent"),
        ("compliance", ["Compliance_Agent"], ["audit regulatory/security"], "agent"),
        ("simulation", ["Simulation_Agent"], ["audit cycle-time/bottlenecks"], "agent"),
        ("loopctl", ["loop_control"], [], "tool"),
        ("subproc", ["Subprocess_Driver_Agent"], ["expand every top-level", "step (unconditional)"], "agent"),
        ("diagram", ["generate_process_", "flow_diagram"], [], "tool"),
        ("doc", ["generate_process_", "document"], [], "tool"),
    ]
    steps = [
        ("root", "reset", "reset stale state", {"number": 1}),
        ("root", "analysis", 'extract requirements\nfrom "inquiry"', {"number": 2}),
        ("root", "design", "build/revise process JSON", {"number": 3}),
        ("root", "compliance", "audit current design", {"number": 4}),
        ("root", "simulation", "audit current design", {"number": 5}),
        ("root", "loopctl", "required={compliance_status,\nsimulation_status: APPROVED}, max 2", {"number": 6}),
        ("loopctl", "design", "CONTINUE -> repeat 3-6", {"number": 7, "dashed": True}),
        ("loopctl", "subproc", "STOP -> expand steps\n(unconditional, either way)", {"number": 8, "dashed": True}),
        ("subproc", "diagram", "render flow diagram", {"number": 9}),
        ("diagram", "doc", "render ISO Word document", {"number": 10}),
    ]
    generate_sequence_diagram(
        "sequence-process-create.png",
        "Process_Pipeline sequence (process creation)",
        "registries/process.hocon -- front-man's own instructions; loop stage collapsed in the frame below",
        participants, steps,
        loops=[("design", "loopctl", "loop  [until APPROVED, max 2x]", (2, 5))],
        figsize=(19, 7.5),
    )


def generate_process_update_sequence():
    # Source: registries/process_update.hocon -- Process_Update_Pipeline's
    # own "instructions"/"tools". Previously ended with a plain-language
    # report, no subprocess regeneration, and no document regeneration at
    # all -- two real gaps found while drawing this diagram (see
    # codeDoc/README.md's own note on them), fixed to mirror the ADK
    # original's own Update_Design_Pipeline and this port's own `process`
    # create pipeline: re-expand subprocesses, then regenerate the flow
    # diagram and Word document, unconditionally once the loop stops,
    # either way.
    participants = [
        ("root", ["Process_Update_Pipeline"], ["registries/process_update.hocon", "front-man"], "agent"),
        ("reset", ["reset_loop_state"], [], "tool"),
        ("analyst", ["Process_Update_Analyst"], ["diff change request", "vs. existing baseline"], "agent"),
        ("design", ["Design_Agent"], ["apply delta to", "existing process JSON"], "agent"),
        ("compliance", ["Compliance_Agent"], [], "agent"),
        ("simulation", ["Simulation_Agent"], [], "agent"),
        ("loopctl", ["loop_control"], [], "tool"),
        ("subproc", ["Subprocess_Driver_Agent"], ["re-expand every top-level", "step (unconditional)"], "agent"),
        ("diagram", ["generate_process_", "flow_diagram"], [], "tool"),
        ("doc", ["generate_process_", "document"], [], "tool"),
    ]
    steps = [
        ("root", "reset", "reset stale state", {"number": 1}),
        ("root", "analyst", "diff change request\nvs. baseline", {"number": 2}),
        ("root", "design", "apply delta", {"number": 3}),
        ("root", "compliance", "audit updated design", {"number": 4}),
        ("root", "simulation", "audit updated design", {"number": 5}),
        ("root", "loopctl", "required={compliance_status,\nsimulation_status: APPROVED}, max 2", {"number": 6}),
        ("loopctl", "design", "CONTINUE -> repeat 3-6", {"number": 7, "dashed": True}),
        ("loopctl", "subproc", "STOP -> re-expand steps\n(unconditional, either way)", {"number": 8, "dashed": True}),
        ("subproc", "diagram", "regenerate flow diagram", {"number": 9}),
        ("diagram", "doc", "regenerate ISO Word document", {"number": 10}),
    ]
    generate_sequence_diagram(
        "sequence-process-update.png",
        "Process_Update_Pipeline sequence (process update)",
        "registries/process_update.hocon -- front-man's own instructions; loop stage collapsed in the frame below",
        participants, steps,
        loops=[("design", "loopctl", "loop  [until APPROVED, max 2x]", (2, 5))],
        figsize=(20, 7.5),
    )


def generate_design_doc_create_sequence():
    # Source: registries/design.hocon -- Design_Doc_Pipeline's own
    # "instructions"/"tools".
    participants = [
        ("root", ["Design_Doc_Pipeline"], ["registries/design.hocon", "front-man"], "agent"),
        ("reset", ["reset_loop_state"], [], "tool"),
        ("analysis", ["Design_Doc_Analysis", "_Agent"], ["extract architectural", "requirements JSON"], "agent"),
        ("design", ["Design_Doc_Agent"], ["build/revise HLD+LLD", "in one pass"], "agent"),
        ("compliance", ["Compliance_Agent"], [], "agent"),
        ("simulation", ["Simulation_Agent"], ["4-dimension design", "simulation gate"], "agent"),
        ("loopctl", ["loop_control"], [], "tool"),
        ("diagram", ["generate_design_", "flow_diagram"], [], "tool"),
        ("doc", ["generate_design_", "document"], [], "tool"),
    ]
    steps = [
        ("root", "reset", "reset stale state", {"number": 1}),
        ("root", "analysis", 'extract architectural\nrequirements from "inquiry"', {"number": 2}),
        ("root", "design", "build/revise HLD+LLD JSON", {"number": 3}),
        ("root", "compliance", "audit current design", {"number": 4}),
        ("root", "simulation", "audit current design", {"number": 5}),
        ("root", "loopctl", "required={compliance_status,\nsimulation_status: APPROVED}, max 2", {"number": 6}),
        ("loopctl", "design", "CONTINUE -> repeat 3-6", {"number": 7, "dashed": True}),
        ("loopctl", "diagram", "STOP -> render diagram\n(unconditional, either way)", {"number": 8, "dashed": True}),
        ("diagram", "doc", "render ISO Word document", {"number": 9}),
    ]
    generate_sequence_diagram(
        "sequence-design-doc-create.png",
        "Design_Doc_Pipeline sequence (HLD/LLD/Combined creation)",
        "registries/design.hocon -- front-man's own instructions; no subprocess stage (process-only concept); loop stage collapsed",
        participants, steps,
        loops=[("design", "loopctl", "loop  [until APPROVED, max 2x]", (2, 5))],
        figsize=(17.5, 8),
    )


def generate_design_doc_update_sequence():
    # Source: registries/design_update.hocon -- Design_Doc_Update_Pipeline's
    # own "instructions"/"tools" (same shape as design.hocon's, confirmed
    # to correctly include generate_design_flow_diagram/
    # generate_design_document -- unlike process_update.hocon's own gap,
    # noted on that diagram above).
    participants = [
        ("root", ["Design_Doc_Update", "_Pipeline"], ["registries/design_update.hocon", "front-man"], "agent"),
        ("reset", ["reset_loop_state"], [], "tool"),
        ("analyst", ["Design_Doc_Update", "_Analyst"], ["diff change request", "vs. existing baseline"], "agent"),
        ("design", ["Design_Doc_Agent"], ["apply delta to", "existing HLD+LLD JSON"], "agent"),
        ("compliance", ["Compliance_Agent"], [], "agent"),
        ("simulation", ["Simulation_Agent"], [], "agent"),
        ("loopctl", ["loop_control"], [], "tool"),
        ("diagram", ["generate_design_", "flow_diagram"], [], "tool"),
        ("doc", ["generate_design_", "document"], [], "tool"),
    ]
    steps = [
        ("root", "reset", "reset stale state", {"number": 1}),
        ("root", "analyst", "diff change request\nvs. baseline", {"number": 2}),
        ("root", "design", "apply delta", {"number": 3}),
        ("root", "compliance", "audit updated design", {"number": 4}),
        ("root", "simulation", "audit updated design", {"number": 5}),
        ("root", "loopctl", "required={compliance_status,\nsimulation_status: APPROVED}, max 2", {"number": 6}),
        ("loopctl", "design", "CONTINUE -> repeat 3-6", {"number": 7, "dashed": True}),
        ("loopctl", "diagram", "STOP -> regenerate diagram\n(unconditional, either way)", {"number": 8, "dashed": True}),
        ("diagram", "doc", "regenerate ISO Word document", {"number": 9}),
    ]
    generate_sequence_diagram(
        "sequence-design-doc-update.png",
        "Design_Doc_Update_Pipeline sequence (HLD/LLD/Combined update)",
        "registries/design_update.hocon -- front-man's own instructions; loop stage collapsed",
        participants, steps,
        loops=[("design", "loopctl", "loop  [until APPROVED, max 2x]", (2, 5))],
        figsize=(17.5, 8),
    )


if __name__ == "__main__":
    generate_class_diagram()
    generate_cloudarch_sequence()
    generate_process_create_sequence()
    generate_process_update_sequence()
    generate_design_doc_create_sequence()
    generate_design_doc_update_sequence()
