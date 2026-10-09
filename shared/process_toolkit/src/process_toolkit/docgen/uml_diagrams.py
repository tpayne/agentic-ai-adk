"""Renders real diagram images for a design document's architecture/UML
diagram descriptors: pure matplotlib/networkx drawing, no external
PlantUML/Graphviz binary dependency.

A diagram descriptor by itself carries no drawable content -- it's just
bookkeeping about a diagram that was supposed to exist. The actual
nodes/edges to draw always live in whichever dict directly CONTAINS the
descriptor. generate_uml_diagram() takes that containing dict as `context`
and dispatches to whichever renderer below actually has something to draw
from, returning "" (not a fabricated image) if none of them do.
"""

import os
import math
import logging
import textwrap
from typing import Any, Dict, List, Optional

import matplotlib
# Callers may invoke this from a background thread (e.g. inside
# asyncio.to_thread) -- matplotlib's default interactive GUI backend
# requires the main thread and warns the moment pyplot is used from
# anywhere else. This module only ever calls fig.savefig(), never
# plt.show(), so the non-interactive "Agg" backend is strictly correct,
# not a workaround. Must be set before pyplot is imported (backend is
# selected at import time).
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patches as patches  # noqa: E402
import networkx as nx  # noqa: E402

from process_toolkit.filenames import safe_filename_component
from process_toolkit import paths

logger = logging.getLogger("ProcessArchitect.UMLDiagram")


def _out_path(diagram_descriptor: dict, context: Optional[dict] = None, output_dir: Optional[str] = None) -> str:
    output_dir = output_dir or paths.output_dir("uml_diagrams")
    # "name" is a real legacy fallback -- earlier design-agent output used
    # it instead of "title"/"diagram_id". Falling through to it here means
    # such a flow gets a real, descriptive filename instead of the bare
    # literal "diagram".
    stem = (
        diagram_descriptor.get("diagram_id")
        or diagram_descriptor.get("title")
        or diagram_descriptor.get("name")
        or "diagram"
    )
    # Still-generic stem (none of the above present) -- prefix the owning
    # component's name, if known, so two such descriptors (e.g. two
    # different components each with an untitled flow) don't collide on
    # the exact same "diagram.png" and silently overwrite one another.
    if stem == "diagram" and isinstance(context, dict):
        component = context.get("component_name")
        if isinstance(component, str) and component.strip():
            stem = f"{component.strip()}-diagram"
    safe = safe_filename_component(str(stem).lower())
    return os.path.join(output_dir, f"{safe}.png")


def _wrap(label: Any, width: int = 22) -> str:
    text = str(label)
    # break_long_words=False: a single overlong token (a method call like
    # "publishReconciliationEvent(ciId)" is common in sequence-diagram
    # messages) is kept whole on its own line rather than hard-split
    # mid-identifier, which reads as corrupted text (confirmed against a
    # rendered sequence diagram: "publishReconciliationEvent(ciId)" split
    # into "...Event(c" / "iId)" was visually indistinguishable from a
    # typo). It's allowed to overflow its nominal width slightly; that's
    # still more legible than a broken identifier.
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)) or text


# ------------------------------------------------------------
# HUB-AND-SPOKE -- one central node with unconnected peers around it
# (context diagrams: the system + its external systems; a component
# and its own interfaces/dependencies).
# ------------------------------------------------------------

def _draw_hub_and_spoke(out_path: str, title: str, hub_label: str, spokes: List[Dict[str, Any]]) -> str:
    spokes = [s for s in spokes if s.get("label")]
    if not spokes:
        return ""

    G = nx.DiGraph()
    G.add_node(hub_label)
    for s in spokes:
        G.add_edge(hub_label, s["label"])

    ring = nx.circular_layout(G.subgraph([s["label"] for s in spokes]))
    pos = {k: (x * 2.6, y * 2.6) for k, (x, y) in ring.items()}
    pos[hub_label] = (0.0, 0.0)

    fig, ax = plt.subplots(figsize=(11, 9))
    ax.axis("off")

    nx.draw_networkx_edges(G, pos, edge_color="gray", arrows=False, ax=ax)

    node_colors = ["#dbe8f9" if n == hub_label else "#f5f5f5" for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=4200, edgecolors="black", ax=ax)

    for n, (x, y) in pos.items():
        ax.text(x, y, _wrap(n, 20), ha="center", va="center", fontsize=9)

    for s in spokes:
        if s.get("edge_label"):
            x0, y0 = pos[hub_label]
            x1, y1 = pos[s["label"]]
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            ax.text(
                mx, my, _wrap(s["edge_label"], 18), fontsize=7, ha="center", va="center",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.85),
            )

    fig.suptitle(_wrap(title, 60), fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ------------------------------------------------------------
# NODE GRID -- a flat set of boxes with no known relationships between
# them (view "elements" lists, deployment "environments"). Deliberately
# draws no edges: there is no relationship data to draw them from, and
# guessing connections would fabricate exactly the kind of thing this
# module exists to avoid.
# ------------------------------------------------------------

def _draw_node_grid(out_path: str, title: str, nodes: List[Dict[str, Any]]) -> str:
    nodes = [n for n in nodes if n.get("label")]
    if not nodes:
        return ""

    n = len(nodes)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)

    fig, ax = plt.subplots(figsize=(min(4 * cols, 16), min(3.2 * rows, 12)))
    ax.axis("off")
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.invert_yaxis()

    for i, node in enumerate(nodes):
        col, row = i % cols, i // cols
        x, y = col + 0.5, row + 0.5
        box = patches.FancyBboxPatch(
            (col + 0.08, row + 0.12), 0.84, 0.76,
            boxstyle="round,pad=0.02", linewidth=1, edgecolor="black", facecolor="#f5f5f5",
        )
        ax.add_patch(box)
        ax.text(x, y - 0.1, _wrap(node["label"], 24), ha="center", va="center", fontsize=9, fontweight="bold")
        if node.get("sublabel"):
            ax.text(x, y + 0.24, _wrap(node["sublabel"], 30), ha="center", va="center", fontsize=6.8, color="#444")

    fig.suptitle(_wrap(title, 60), fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ------------------------------------------------------------
# EDGE GRAPH -- real source -> target relationships (high_level_design
# "integration_points": genuine labeled edges, unlike the node-only
# shapes above).
# ------------------------------------------------------------

def _draw_edge_graph(out_path: str, title: str, edges: List[Dict[str, Any]]) -> str:
    edges = [e for e in edges if e.get("source") and e.get("target")]
    if not edges:
        return ""

    G = nx.DiGraph()
    for e in edges:
        G.add_edge(e["source"], e["target"])

    pos = nx.spring_layout(G, seed=7, k=1.6)

    fig, ax = plt.subplots(figsize=(12, 9))
    ax.axis("off")

    nx.draw_networkx_edges(G, pos, edge_color="gray", arrows=True, arrowstyle="-|>", arrowsize=14, ax=ax)
    nx.draw_networkx_nodes(G, pos, node_color="#f5f5f5", node_size=4500, edgecolors="black", ax=ax)

    for n, (x, y) in pos.items():
        ax.text(x, y, _wrap(n, 22), ha="center", va="center", fontsize=8)

    for e in edges:
        if e.get("label") and e["source"] in pos and e["target"] in pos:
            x0, y0 = pos[e["source"]]
            x1, y1 = pos[e["target"]]
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            ax.text(
                mx, my, _wrap(e["label"], 18), fontsize=6.5, ha="center", va="center",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.85),
            )

    fig.suptitle(_wrap(title, 60), fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ------------------------------------------------------------
# UML CLASS DIAGRAM -- standard 3-compartment class boxes (name /
# attributes / methods). No association lines: the source data records
# each class's own members but not relationships between classes, so
# this doesn't invent connections that aren't actually known.
# ------------------------------------------------------------

def _draw_class_diagram(out_path: str, title: str, classes: List[Dict[str, Any]]) -> str:
    classes = [c for c in classes if isinstance(c, dict) and c.get("class_name")]
    if not classes:
        return ""

    n = len(classes)
    cols = max(1, min(3, math.ceil(math.sqrt(n))))
    rows = math.ceil(n / cols)

    box_w, box_h = 3.6, 3.4
    fig, ax = plt.subplots(figsize=(box_w * cols + 1, box_h * rows + 1))
    ax.axis("off")
    ax.set_xlim(0, cols * box_w)
    ax.set_ylim(0, rows * box_h)
    ax.invert_yaxis()

    for i, cls in enumerate(classes):
        col, row = i % cols, i // cols
        x0, y0 = col * box_w + 0.2, row * box_h + 0.2
        w, h = box_w - 0.4, box_h - 0.4

        name = str(cls["class_name"]).rsplit(".", 1)[-1]  # drop long package prefixes
        attrs = cls.get("attributes") or []
        methods = cls.get("methods") or []

        name_h = 0.55
        attrs_h = h * 0.4
        methods_h = h - name_h - attrs_h

        ax.add_patch(patches.Rectangle((x0, y0), w, h, edgecolor="black", facecolor="white", linewidth=1.2))
        ax.add_patch(patches.Rectangle((x0, y0), w, name_h, edgecolor="black", facecolor="#dbe8f9", linewidth=1))
        ax.text(
            x0 + w / 2, y0 + name_h / 2, _wrap(name, 26), ha="center", va="center",
            fontsize=8.5, fontweight="bold",
        )

        ax.plot([x0, x0 + w], [y0 + name_h + attrs_h] * 2, color="black", linewidth=1)

        attr_text = "\n".join(_wrap(a, 30) for a in attrs[:8])
        ax.text(x0 + 0.08, y0 + name_h + 0.08, attr_text, ha="left", va="top", fontsize=6.3, family="monospace")

        method_text = "\n".join(_wrap(m, 30) for m in methods[:8])
        ax.text(
            x0 + 0.08, y0 + name_h + attrs_h + 0.08, method_text,
            ha="left", va="top", fontsize=6.3, family="monospace",
        )

    fig.suptitle(_wrap(title, 60), fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ------------------------------------------------------------
# UML SEQUENCE DIAGRAM -- lifelines + ordered call/return arrows. Unlike
# every renderer above, the drawable content (participants/steps) lives
# on the descriptor itself, not in a separate `context` dict -- a
# sequence descriptor is self-contained by design, since each one
# describes its own distinct interaction, not a shared structural view.
# ------------------------------------------------------------

def _draw_sequence_diagram(
    out_path: str, title: str, participants: List[str], steps: List[Dict[str, Any]]
) -> str:
    participants = [p for p in (participants or []) if p]
    steps = [
        s for s in (steps or [])
        if isinstance(s, dict) and s.get("from_participant") and s.get("to_participant") and s.get("message")
    ]
    if not participants or not steps:
        return ""

    # Any participant referenced by a step but not declared up front is
    # appended in first-seen order, rather than silently dropping that
    # step's arrow.
    for s in steps:
        for key in ("from_participant", "to_participant"):
            p = s[key]
            if p not in participants:
                participants.append(p)

    x_positions = {p: i * 2.4 for i, p in enumerate(participants)}
    step_gap = 0.9
    lifeline_top = 0.55
    lifeline_bottom = lifeline_top + step_gap * (len(steps) + 1)

    fig_w = max(6.0, len(participants) * 2.4 + 1.5)
    fig_h = max(4.0, lifeline_bottom + 1.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    ax.set_xlim(-1.3, x_positions[participants[-1]] + 1.3)
    ax.set_ylim(0, lifeline_bottom + 0.6)
    ax.invert_yaxis()

    for p in participants:
        x = x_positions[p]
        box = patches.FancyBboxPatch(
            (x - 0.95, -0.3), 1.9, 0.6, boxstyle="round,pad=0.02",
            linewidth=1, edgecolor="black", facecolor="#dbe8f9",
        )
        ax.add_patch(box)
        ax.text(x, 0.0, _wrap(p, 20), ha="center", va="center", fontsize=8.5, fontweight="bold")
        ax.plot([x, x], [0.3, lifeline_bottom], color="gray", linestyle="--", linewidth=1, zorder=0)

    y = lifeline_top + step_gap
    for step in sorted(steps, key=lambda s: s.get("step_number") or 0):
        x0 = x_positions.get(step["from_participant"])
        x1 = x_positions.get(step["to_participant"])
        if x0 is None or x1 is None:
            y += step_gap
            continue

        linestyle = "dashed" if step.get("is_return") else "solid"
        message = _wrap(step["message"], 28)
        if step.get("is_async"):
            message = f"{message}\n(async)"

        if x0 == x1:
            # Self-call: a small square loop back onto the same lifeline.
            loop_w = 0.55
            ax.plot(
                [x0, x0 + loop_w, x0 + loop_w, x0 + 0.06],
                [y, y, y + 0.32, y + 0.32],
                color="black", linestyle=linestyle, linewidth=1.2,
            )
            ax.annotate(
                "", xy=(x0, y + 0.32), xytext=(x0 + 0.1, y + 0.32),
                arrowprops=dict(arrowstyle="-|>", color="black", linewidth=1.2),
            )
            label_x, label_ha = x0 + loop_w + 0.12, "left"
        else:
            ax.annotate(
                "", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="-|>", color="black", linewidth=1.2, linestyle=linestyle),
            )
            label_x, label_ha = (x0 + x1) / 2, "center"

        ax.text(
            label_x, y - 0.1, message, fontsize=7, ha=label_ha, va="bottom",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85),
        )
        if step.get("notes"):
            ax.text(
                label_x, y + 0.22, _wrap(step["notes"], 30), fontsize=6, ha=label_ha, va="top",
                color="#555", style="italic",
            )

        y += step_gap

    fig.suptitle(_wrap(title, 60), fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ------------------------------------------------------------
# DISPATCH
# ------------------------------------------------------------

def generate_uml_diagram(
    diagram_descriptor: dict, context: dict, system_name: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> str:
    """
    Generates and saves a real diagram image for `diagram_descriptor`,
    using whatever structural data is actually available in `context`
    (the dict directly containing this descriptor). Tries, in order,
    the most specific/richest data available:

      0. participants/steps -> UML sequence diagram (self-contained on
         the descriptor itself, checked before anything in `context`)
      1. classes            -> UML class diagram
      2. integration_points -> labeled source/target edge graph
      3. external_systems   -> hub-and-spoke around `system_name`
      4. environments       -> node grid (deployment topology)
      5. elements           -> node grid (a view's flat element list)
      6. component_name +
         interfaces/dependencies -> hub-and-spoke around the component

    Returns the saved PNG path, or "" if neither `diagram_descriptor`
    nor `context` holds any of the above -- callers should fall back to
    an honest "not yet generated" note rather than presenting a
    placeholder as a real diagram.

    `output_dir` defaults to the relative path "output/uml_diagrams" if
    not given; pass an absolute path to control exactly where images are
    written (e.g. a caller-resolved, possibly test-isolated output root).
    """
    try:
        if not isinstance(diagram_descriptor, dict) or not isinstance(context, dict):
            return ""

        dtype = str(diagram_descriptor.get("diagram_type") or "").strip().lower()
        # "name" is the same legacy fallback _out_path falls through to --
        # an untitled-but-named flow (real generated data uses "name"
        # instead of "title") should get a real heading in the document,
        # not the generic "Diagram" every such flow would otherwise share.
        title = diagram_descriptor.get("title") or diagram_descriptor.get("name") or "Diagram"
        out_path = _out_path(diagram_descriptor, context, output_dir)

        # NOTE: none of the branches below gate on `dtype` matching the
        # data they draw from. `diagram_type` is an LLM-authored enum
        # field on the descriptor and isn't reliably consistent with the
        # descriptor's actual containing structure (confirmed against a
        # real generated document where a class_design.diagram entry,
        # sitting directly above a real, non-empty "classes" list, was
        # tagged diagram_type="context" instead of "class"). Every
        # branch here dispatches on the SHAPE of the data actually
        # present instead -- `dtype` is only used in the final debug log
        # line, never to gate whether a real diagram gets drawn.
        participants = diagram_descriptor.get("participants")
        steps = diagram_descriptor.get("steps")
        if isinstance(steps, list) and steps and not participants and all(
            isinstance(step, str) for step in steps
        ):
            # Earlier design-agent outputs represented sequence flows as
            # plain prose. Preserve those steps as ordered self-messages
            # on the owning component rather than dropping the UML image.
            participant = str(context.get("component_name") or system_name or "Process")
            participants = [participant]
            steps = [
                {
                    "step_number": index,
                    "from_participant": participant,
                    "to_participant": participant,
                    "message": step,
                }
                for index, step in enumerate(steps, start=1)
            ]

        if participants and steps:
            result = _draw_sequence_diagram(out_path, title, participants, steps)
            if result:
                return result

        if context.get("classes"):
            result = _draw_class_diagram(out_path, title, context["classes"])
            if result:
                return result

        integration_points = context.get("integration_points")
        if integration_points:
            # "source"/"target" are the schema-correct keys; "source_
            # component"/"target_component" is accepted as a fallback --
            # the design agent has been observed inventing that synonym
            # by analogy with component_name.
            edges = [
                {
                    "source": ip.get("source") or ip.get("source_component"),
                    "target": ip.get("target") or ip.get("target_component"),
                    "label": ip.get("protocol") or ip.get("integration_pattern"),
                }
                for ip in integration_points if isinstance(ip, dict)
            ]
            result = _draw_edge_graph(out_path, title, edges)
            if result:
                return result

        # Components with their own declared dependencies (no separate
        # integration_points edges needed) -- e.g. a Container/Component
        # (C4 Level 2/3) view whose context dict holds
        # high_level_design.components[] directly rather than a
        # standalone integration_points list. Each component becomes a
        # node; each real "depends on" relationship it names becomes an
        # edge, exactly like integration_points above, just sourced from
        # a different real field.
        components = context.get("components")
        if isinstance(components, list) and any(
            isinstance(c, dict) and c.get("component_name") and c.get("dependencies") for c in components
        ):
            edges = [
                {"source": c["component_name"], "target": dep, "label": None}
                for c in components if isinstance(c, dict) and c.get("component_name")
                for dep in (c.get("dependencies") or [])
                if isinstance(dep, str)
            ]
            result = _draw_edge_graph(out_path, title, edges)
            if result:
                return result

        external_systems = context.get("external_systems")
        if external_systems:
            hub = (
                system_name
                or context.get("component_name")
                or context.get("system_name")
                or "This System"
            )
            # "name" is the schema's required field for an external
            # system, but schema validation only checks top-level shape,
            # not this deep -- an entry missing it (still possible in
            # practice) used to just drop out of `spokes` silently in
            # _draw_hub_and_spoke, and if EVERY entry was missing it, the
            # whole diagram failed with an opaque "no drawable data"
            # rather than drawing the (still real, still useful)
            # description-based fallback. Confirmed against a real
            # generated document: a context diagram fell back to "[Context
            # not yet generated for this document.]" even though its
            # System Context section had a populated External Systems
            # table one section earlier in the same document.
            spokes = []
            for idx, es in enumerate(external_systems):
                if not isinstance(es, dict):
                    continue
                description = es.get("description")
                if description and len(description) > 40:
                    description = description[:37] + "..."
                label = es.get("name") or description or f"External System {idx + 1}"
                spokes.append({"label": label, "edge_label": es.get("interface_type")})
            result = _draw_hub_and_spoke(out_path, title, hub, spokes)
            if result:
                return result

        environments = context.get("environments")
        if environments:
            nodes = [
                {"label": env.get("name"), "sublabel": env.get("infrastructure")}
                for env in environments if isinstance(env, dict)
            ]
            result = _draw_node_grid(out_path, title, nodes)
            if result:
                return result

        elements = context.get("elements")
        if elements and all(isinstance(e, str) for e in elements):
            nodes = [{"label": e, "sublabel": None} for e in elements]
            result = _draw_node_grid(out_path, title, nodes)
            if result:
                return result

        if context.get("component_name") and (context.get("interfaces") or context.get("dependencies")):
            hub = context["component_name"]
            spokes = [{"label": x, "edge_label": None} for x in (context.get("interfaces") or [])]
            spokes += [{"label": x, "edge_label": "depends on"} for x in (context.get("dependencies") or [])]
            result = _draw_hub_and_spoke(out_path, title, hub, spokes)
            if result:
                return result

        # Every branch above either found nothing at all, or found a
        # candidate key but it produced zero usable nodes/spokes once
        # filtered (e.g. "external_systems" present but every entry
        # missing both a name and a description). Logging which keys
        # were actually present -- even though they didn't pan out --
        # turns a dead-end "no data found" into an actionable "this key
        # had data, but not enough of it" the next time a diagram
        # silently falls back to the placeholder note.
        candidate_keys = (
            "classes", "integration_points", "components", "external_systems",
            "environments", "elements", "component_name", "interfaces", "dependencies",
        )
        present = [k for k in candidate_keys if context.get(k)]
        logger.debug(
            f"No drawable structural data found for diagram '{title}' (type={dtype}). "
            f"Context keys present but insufficient: {present or 'none'}."
        )
        return ""

    except Exception:
        logger.exception(f"Failed to generate UML diagram for '{diagram_descriptor.get('title')}'")
        return ""
