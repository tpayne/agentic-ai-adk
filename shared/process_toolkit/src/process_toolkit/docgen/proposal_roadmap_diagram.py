"""Renders a polished, deterministic delivery-roadmap diagram from
proposal_response.json's own "implementation_plan" field (list of
{"phase", "timing", "deliverable", "acceptance_criteria"}) -- one phase
card per entry, left to right in the agent's own given (sequential)
order, connected by directional arrows.

Mirrors proposal_architecture_diagram.py's own visual language (header
banner, numbered cards, restrained enterprise palette) but with a
simple single-row layout instead of BFS-layered depth, since phases are
already explicitly ordered rather than forming a graph.

Self-contained and called directly by generation.py's own document-build
step (via proposal_response_sections.py's own Mobilisation & Phased
Roadmap renderer), same reasoning proposal_architecture_diagram.py
already documents for why this isn't routed through the pipeline's own
edge_inference stage.
"""

import logging
from typing import Any, Dict, List

import matplotlib as mpl
# Must be set before pyplot is imported -- same reasoning as
# proposal_architecture_diagram.py's own identical line.
mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle

from process_toolkit import paths
from process_toolkit.docgen.diagram_style import add_fitted_text, fit_title
from process_toolkit.filenames import safe_filename_component

logger = logging.getLogger("ProcessArchitect.ProposalRoadmapDiagram")


def generate_proposal_roadmap_diagram(plan: List[Dict[str, Any]], process_name: str) -> str:
    """Renders the diagram and saves it to output/<process_name>_roadmap.png.
    Returns the saved path.

    Raises ValueError if `plan` has no usable (phase-named) entries -- the
    caller's own responsibility to skip calling this at all when
    "implementation_plan" is empty, same no-fabrication convention every
    other diagram/section renderer in this project follows."""
    valid = [p for p in (plan or []) if isinstance(p, dict) and p.get("phase")]
    if not valid:
        raise ValueError("No usable implementation_plan entries to render.")

    card_width, card_height = 2.75, 2.2
    x_spacing = 3.2
    positions = [(i * x_spacing, 0.0) for i in range(len(valid))]

    x_min, x_max = positions[0][0], positions[-1][0]
    left, right = x_min - card_width / 2 - 1.1, x_max + card_width / 2 + 1.1
    if right - left < 8.5:
        extra_padding = (8.5 - (right - left)) / 2
        left -= extra_padding
        right += extra_padding
    # Single row (all cards at y=0) -- mirror the architecture diagram's
    # own margin formula exactly (half-card + banner + a small gap on
    # top, half-card + a small gap on the bottom), not a generic re-guess,
    # so this doesn't end up with a tall band of dead space below the
    # cards the way a naive y_min/y_max-style margin would for a single
    # row.
    bottom, top = -card_height / 2 - 0.35, card_height / 2 + 1.45
    plot_width, plot_height = right - left, top - bottom

    fig_width = min(13.0, max(8.5, plot_width * 0.72))
    fig_height = fig_width * plot_height / plot_width
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor="#F4F7FB")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_facecolor("#F4F7FB")
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.set_aspect("equal", adjustable="box")

    # Header block -- same banner convention as the architecture diagram.
    ax.add_patch(FancyBboxPatch(
        (left, top - 1.25), plot_width, 1.25,
        boxstyle="round,pad=0.02,rounding_size=0.16",
        facecolor="#14243A", edgecolor="none", zorder=1,
    ))
    ax.text(
        left + 0.35, top - 0.47, "DELIVERY ROADMAP",
        color="#77D6C1", fontsize=9, fontweight="bold", va="center",
        ha="left", zorder=2,
    )
    title = str(process_name)
    fit_title(
        ax, title, left + 0.35, top - 0.91, plot_width - 4.5,
        color="white", fontweight="bold", ha="left", zorder=2,
    )
    ax.text(
        right - 0.3, top - 0.72, f"{len(valid):02d} PHASES",
        color="#D3DFEC", fontsize=8, fontweight="bold", va="center",
        ha="right", zorder=2,
    )

    node_boxes = []
    for x, y in positions:
        box = FancyBboxPatch(
            (x - card_width / 2, y - card_height / 2),
            card_width, card_height,
            boxstyle="round,pad=0.04,rounding_size=0.13",
            facecolor="white", edgecolor="#D8E1EC", linewidth=1.0,
            zorder=3,
        )
        ax.add_patch(box)
        node_boxes.append(box)

    for i in range(len(valid) - 1):
        edge = FancyArrowPatch(
            positions[i], positions[i + 1],
            patchA=node_boxes[i], patchB=node_boxes[i + 1],
            arrowstyle="-|>", mutation_scale=13,
            color="#7C91AA", linewidth=1.55, alpha=0.9,
            shrinkA=4, shrinkB=4, zorder=2,
        )
        ax.add_patch(edge)

    palette = ["#2878B8", "#7258B5", "#178C83", "#D08034"]
    for index, (phase, (x, y)) in enumerate(zip(valid, positions), start=1):
        color = palette[(index - 1) % len(palette)]
        ax.add_patch(Circle(
            (x - card_width / 2 + 0.24, y + 0.72), 0.14,
            facecolor=color, edgecolor="none", zorder=4,
        ))
        ax.text(
            x - card_width / 2 + 0.24, y + 0.72, f"{index:02d}",
            color="white", fontsize=6.5, fontweight="bold",
            ha="center", va="center", zorder=5,
        )
        add_fitted_text(
            ax, str(phase.get("phase", "")), x - card_width / 2 + 0.48, y + 0.72,
            card_width - 0.68, 0.5, fontsize=9, min_fontsize=6.5,
            color="#1C2D43", fontweight="bold", ha="left", zorder=5,
        )
        timing = str(phase.get("timing", "")).strip()
        if timing:
            add_fitted_text(
                ax, timing, x - card_width / 2 + 0.22, y + 0.18,
                card_width - 0.44, 0.34, fontsize=7.5, min_fontsize=5.5,
                color=color, fontweight="bold", ha="left", zorder=5,
            )
        deliverable = str(phase.get("deliverable", "")).strip()
        if deliverable:
            add_fitted_text(
                ax, deliverable, x - card_width / 2 + 0.22, y - 0.28,
                card_width - 0.44, 0.78, fontsize=7.1, min_fontsize=5.2,
                color="#64758A", ha="left", va="top", linespacing=1.15, zorder=5,
            )
        ax.add_patch(FancyBboxPatch(
            (x - card_width / 2 + 0.22, y - card_height / 2 + 0.06),
            0.38, 0.045,
            boxstyle="round,pad=0.01,rounding_size=0.02",
            facecolor=color, edgecolor="none", zorder=5,
        ))

    ax.axis("off")

    out_path = paths.output_path(f"{safe_filename_component(process_name.lower())}_roadmap.png")

    plt.savefig(out_path, dpi=220, facecolor="#F4F7FB")
    plt.close(fig)

    return out_path
