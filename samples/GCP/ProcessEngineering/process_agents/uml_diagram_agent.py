# process_agents/uml_diagram_agent.py
#
# Renders real diagram images for the design document's architecture/
# UML diagram descriptors (design_document_schema.json's "title"/
# "diagram_id"/"description"/"file_reference"/"notation_standard"/
# "diagram_type" records), the same way step_diagram_agent.py renders
# real process-step diagrams: pure matplotlib/networkx drawing, no
# external PlantUML/Graphviz binary dependency, so nothing new needs
# installing in the runtime environment.
#
# A diagram descriptor by itself carries no drawable content -- it's
# just bookkeeping about a diagram that was supposed to exist. The
# actual nodes/edges to draw always live in whichever dict directly
# CONTAINS the descriptor (a view with "elements", a class_design with
# "classes", system_context with "external_systems", a
# deployment_topology with "environments", a component with its own
# "interfaces"/"dependencies", or high_level_design with
# "integration_points"). generate_uml_diagram() takes that containing
# dict as `context` and dispatches to whichever renderer below actually
# has something to draw from, returning "" (not a fabricated image) if
# none of them do.

import os
import math
import logging
import textwrap
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import networkx as nx

from .utils import safe_filename_component

logger = logging.getLogger("ProcessArchitect.UMLDiagram")

OUTPUT_DIR = "output/uml_diagrams"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _out_path(diagram_descriptor: dict) -> str:
    stem = diagram_descriptor.get("diagram_id") or diagram_descriptor.get("title") or "diagram"
    safe = safe_filename_component(str(stem).lower())
    return os.path.join(OUTPUT_DIR, f"{safe}.png")


def _wrap(label: Any, width: int = 22) -> str:
    text = str(label)
    return "\n".join(textwrap.wrap(text, width=width)) or text


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
# DISPATCH
# ------------------------------------------------------------

def generate_uml_diagram(
    diagram_descriptor: dict, context: dict, system_name: Optional[str] = None
) -> str:
    """
    Generates and saves a real diagram image for `diagram_descriptor`,
    using whatever structural data is actually available in `context`
    (the dict directly containing this descriptor). Tries, in order,
    the most specific/richest data available:

      1. classes            -> UML class diagram
      2. integration_points -> labeled source/target edge graph
      3. external_systems   -> hub-and-spoke around `system_name`
      4. environments       -> node grid (deployment topology)
      5. elements           -> node grid (a view's flat element list)
      6. component_name +
         interfaces/dependencies -> hub-and-spoke around the component

    Returns the saved PNG path, or "" if `context` holds none of the
    above -- callers should fall back to an honest "not yet generated"
    note rather than presenting a placeholder as a real diagram.
    """
    try:
        if not isinstance(diagram_descriptor, dict) or not isinstance(context, dict):
            return ""

        dtype = str(diagram_descriptor.get("diagram_type") or "").strip().lower()
        title = diagram_descriptor.get("title") or "Diagram"
        out_path = _out_path(diagram_descriptor)

        if dtype == "class" and context.get("classes"):
            result = _draw_class_diagram(out_path, title, context["classes"])
            if result:
                return result

        integration_points = context.get("integration_points")
        if integration_points:
            edges = [
                {
                    "source": ip.get("source"),
                    "target": ip.get("target"),
                    "label": ip.get("protocol") or ip.get("integration_pattern"),
                }
                for ip in integration_points if isinstance(ip, dict)
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
            spokes = [
                {"label": es.get("name"), "edge_label": es.get("interface_type")}
                for es in external_systems if isinstance(es, dict)
            ]
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

        logger.debug(f"No drawable structural data found for diagram '{title}' (type={dtype}).")
        return ""

    except Exception:
        logger.exception(f"Failed to generate UML diagram for '{diagram_descriptor.get('title')}'")
        return ""
