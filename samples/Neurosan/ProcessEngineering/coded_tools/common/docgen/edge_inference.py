"""Infers a process (or design-document) flow diagram's nodes/edges from
the normalized JSON on disk and renders it as a PNG. Ported near-verbatim
from the ADK sample's process_agents/common/edge_inference_agent.py --
pure networkx/matplotlib, no ADK dependency, no LLM call.

The design-document branch (_infer_edges_from_design_json) has no caller
in this port yet -- no design-document pipeline writes design_data.json
(see the project README's "Remaining work") -- but is ported anyway since
it's pure and self-contained, and detect_schema_type_from_disk's dispatch
already needs to know about both files to stay future-proof for when that
pipeline lands.
"""

import os
import json
import logging
import textwrap
from typing import List, Tuple, Any, Dict

import matplotlib as mpl
import matplotlib.pyplot as plt
import networkx as nx

from coded_tools.common import paths
from coded_tools.common.filenames import safe_filename_component
from coded_tools.common.process_json import (
    PROCESS_JSON_FILENAME,
    DESIGN_JSON_FILENAME,
    detect_schema_type_from_disk,
)

logger = logging.getLogger("ProcessArchitect.EdgeInference")


def _get_lane_colormap(n: int):
    """Returns an n-level discrete colormap ("Pastel1"), across old and new
    matplotlib versions."""
    n = max(int(n), 1)
    try:
        return mpl.colormaps["Pastel1"].resampled(n)
    except Exception:
        return plt.cm.get_cmap("Pastel1", n)


# ============================================================
#  JSON LOADING (GENERIC)
# ============================================================

def _load_process_json() -> dict | None:
    path = paths.output_path(PROCESS_JSON_FILENAME)
    try:
        if not os.path.exists(path):
            logger.error(f"Process JSON not found at {path}")
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load process JSON")
        return None


def _load_design_json() -> dict | None:
    path = paths.output_path(DESIGN_JSON_FILENAME)
    try:
        if not os.path.exists(path):
            logger.error(f"Design document JSON not found at {path}")
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load design document JSON")
        return None


# ============================================================
#  STEP ORDERING (GENERIC)
# ============================================================

def _order_steps(steps: list[dict]) -> list[dict]:
    """
    Priority: 1) step_number (numeric) 2) step_id 3) step 4) original order.
    """
    if not steps:
        return []

    if any("step_number" in s for s in steps):
        with_num = [s for s in steps if isinstance(s.get("step_number"), (int, float))]
        without_num = [s for s in steps if not isinstance(s.get("step_number"), (int, float))]
        with_num_sorted = sorted(with_num, key=lambda s: s["step_number"])
        return with_num_sorted + without_num

    def _parse_id(val: Any) -> float:
        try:
            return float(val)
        except Exception:
            return float("inf")

    if any("step_id" in s for s in steps):
        return sorted(steps, key=lambda s: _parse_id(s.get("step_id")))

    if any("step" in s for s in steps):
        with_step = [s for s in steps if isinstance(s.get("step"), (int, float))]
        without_step = [s for s in steps if not isinstance(s.get("step"), (int, float))]
        with_step_sorted = sorted(with_step, key=lambda s: s["step"])
        return with_step_sorted + without_step

    return steps


# ============================================================
#  SWIMLANE HELPERS
# ============================================================

def _get_lane(step: dict) -> str:
    lane = (
        step.get("lane")
        or step.get("responsible_party")
        or step.get("responsibleRole")
        or "Process"
    )
    if isinstance(lane, str) and lane.strip():
        return lane.strip()
    return "Process"


def _normalize_node_label(name: str) -> str:
    return name.strip()


# ============================================================
#  LABEL ENRICHMENT
# ============================================================

def _extract_step_metrics(step: dict) -> List[str]:
    """Extract up to 1 metric name from a step-level metrics structure."""
    metrics = step.get("metrics")
    if not metrics:
        return []

    names: List[str] = []
    if isinstance(metrics, dict):
        names = list(metrics.keys())
    elif isinstance(metrics, list):
        for m in metrics:
            if isinstance(m, str):
                names.append(m)
            elif isinstance(m, dict):
                n = m.get("name") or m.get("metric_name")
                if isinstance(n, str) and n.strip():
                    names.append(n.strip())

    seen = set()
    deduped = []
    for n in names:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped[:1]


def _build_enriched_label(base_name: str, step: dict) -> str:
    lines = [base_name]

    duration = step.get("estimated_duration") or step.get("duration")
    if isinstance(duration, str) and duration.strip():
        lines.append(f"Duration: {duration.strip()}")

    metric_names = _extract_step_metrics(step)
    if metric_names:
        lines.append(f"Metric: {metric_names[0]}")

    return "\n".join(lines)


def _build_enriched_component_label(base_name: str, component: dict) -> str:
    lines = [base_name]

    owner = component.get("owner")
    if isinstance(owner, str) and owner.strip():
        lines.append(f"Owner: {owner.strip()}")

    tech_stack = component.get("technology_stack")
    if isinstance(tech_stack, list) and tech_stack:
        first = next((t for t in tech_stack if isinstance(t, str) and t.strip()), None)
        if first:
            lines.append(f"Tech: {first.strip()}")

    return "\n".join(lines)


# ============================================================
#  DEPENDENCY RESOLUTION (GENERIC)
# ============================================================

def _build_id_index(steps: list[dict]) -> Dict[str, dict]:
    index: Dict[str, dict] = {}
    for s in steps:
        if not isinstance(s, dict):
            continue

        if "step_number" in s:
            index[f"step_number:{s.get('step_number')}"] = s
        if "step_id" in s:
            index[f"step_id:{s.get('step_id')}"] = s
        if "step" in s:
            index[f"step:{s.get('step')}"] = s

        name = s.get("step_name") or s.get("name")
        if isinstance(name, str) and name.strip():
            index[f"step_name:{name.strip()}"] = s

    return index


def _resolve_dependency(dep: Any, index: Dict[str, dict]) -> dict | None:
    keys = [f"step_number:{dep}", f"step_id:{dep}", f"step:{dep}"]
    if isinstance(dep, str) and dep.strip():
        keys.append(f"step_name:{dep.strip()}")
    for k in keys:
        if k in index:
            return index[k]
    return None


# ============================================================
#  EDGE INFERENCE -- PROCESS SCHEMA (GENERIC + HARD FALLBACK)
# ============================================================

def _infer_edges_from_process_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str], Dict[str, str]]:
    """Infer, from process_data.json: process_name, edges (linear +
    branching), lane_map, label_map. ALWAYS returns at least one edge."""
    data = _load_process_json()
    if not data or not isinstance(data, dict):
        logger.warning("No valid process JSON; using fallback Start->End")
        return "process", [("Start", "End")], {"Start": "Process", "End": "Process"}, {"Start": "Start", "End": "End"}

    process_name = data.get("process_name") or "process"

    raw_steps = data.get("process_steps") or []
    if not isinstance(raw_steps, list):
        logger.warning("process_steps is not a list; using fallback Start->End")
        return process_name, [("Start", "End")], {"Start": "Process", "End": "Process"}, {"Start": "Start", "End": "End"}

    valid_steps: List[dict] = []
    for s in raw_steps:
        if isinstance(s, dict):
            name = s.get("step_name") or s.get("name")
            if isinstance(name, str) and name.strip():
                valid_steps.append(s)
        elif isinstance(s, str) and s.strip():
            valid_steps.append({"name": s.strip()})

    if not valid_steps:
        logger.warning("No valid steps inferred; using fallback Start->End")
        return process_name, [("Start", "End")], {"Start": "Process", "End": "Process"}, {"Start": "Start", "End": "End"}

    ordered_steps = _order_steps(valid_steps)

    node_labels: List[str] = []
    lane_map: Dict[str, str] = {}
    label_map: Dict[str, str] = {}
    for s in ordered_steps:
        raw_name = s.get("step_name") or s.get("name")
        if not isinstance(raw_name, str):
            continue
        base_label = _normalize_node_label(raw_name)
        if not base_label:
            continue
        if base_label not in node_labels:
            node_labels.append(base_label)
        lane_map[base_label] = _get_lane(s)
        label_map[base_label] = _build_enriched_label(base_label, s)

    edges: List[Tuple[str, str]] = []
    if len(node_labels) == 1:
        only = node_labels[0]
        edges = [("Start", only), (only, "End")]
        lane_map["Start"] = "Process"
        lane_map["End"] = "Process"
        label_map.setdefault("Start", "Start")
        label_map.setdefault("End", "End")
    else:
        for i in range(len(node_labels) - 1):
            edges.append((node_labels[i], node_labels[i + 1]))

    id_index = _build_id_index(ordered_steps)
    for s in ordered_steps:
        this_name = s.get("step_name") or s.get("name")
        if not isinstance(this_name, str) or not this_name.strip():
            continue
        this_label = _normalize_node_label(this_name)

        deps = s.get("dependencies") or []
        if not isinstance(deps, list):
            continue

        for dep in deps:
            pred = _resolve_dependency(dep, id_index)
            if not pred:
                continue
            pred_name = pred.get("step_name") or pred.get("name")
            if not isinstance(pred_name, str) or not pred_name.strip():
                continue
            pred_label = _normalize_node_label(pred_name)
            if pred_label != this_label:
                edge = (pred_label, this_label)
                if edge not in edges:
                    edges.append(edge)

    if not edges:
        logger.warning("No edges inferred; using fallback Start->End")
        edges = [("Start", "End")]
        lane_map["Start"] = "Process"
        lane_map["End"] = "Process"
        label_map.setdefault("Start", "Start")
        label_map.setdefault("End", "End")

    return process_name, edges, lane_map, label_map


# ============================================================
#  EDGE INFERENCE -- DESIGN DOCUMENT SCHEMA (GENERIC + HARD FALLBACK)
# ============================================================

def _infer_edges_from_design_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str], Dict[str, str]]:
    """Infer, from design_data.json: doc_name, edges (integration_points +
    component dependencies + sequence flows), lane_map, label_map. ALWAYS
    returns at least one edge."""
    data = _load_design_json()
    if not data or not isinstance(data, dict):
        logger.warning("No valid design document JSON; using fallback Start->End")
        return "design", [("Start", "End")], {"Start": "Component", "End": "Component"}, {"Start": "Start", "End": "End"}

    metadata = data.get("document_metadata") or {}
    doc_name = None
    if isinstance(metadata, dict):
        doc_name = metadata.get("title") or metadata.get("system_name")
    doc_name = doc_name or "design"

    hld = data.get("high_level_design") or {}
    lld = data.get("low_level_design") or {}

    raw_components = []
    integration_points = []
    if isinstance(hld, dict) and isinstance(hld.get("components"), list) and hld.get("components"):
        raw_components = hld.get("components")
        if isinstance(hld.get("integration_points"), list):
            integration_points = hld.get("integration_points")
    elif isinstance(lld, dict) and isinstance(lld.get("components"), list):
        raw_components = lld.get("components")

    if not isinstance(raw_components, list):
        raw_components = []

    valid_components: List[dict] = []
    for c in raw_components:
        if isinstance(c, dict):
            name = c.get("component_name")
            if isinstance(name, str) and name.strip():
                valid_components.append(c)
        elif isinstance(c, str) and c.strip():
            valid_components.append({"component_name": c.strip()})

    if not valid_components:
        logger.warning("No valid design components inferred; using fallback Start->End")
        return doc_name, [("Start", "End")], {"Start": "Component", "End": "Component"}, {"Start": "Start", "End": "End"}

    node_names: List[str] = []
    lane_map: Dict[str, str] = {}
    label_map: Dict[str, str] = {}
    for c in valid_components:
        raw_name = c.get("component_name")
        if not isinstance(raw_name, str):
            continue
        base_name = _normalize_node_label(raw_name)
        if not base_name:
            continue
        if base_name not in node_names:
            node_names.append(base_name)
        owner = c.get("owner")
        lane_map[base_name] = owner.strip() if isinstance(owner, str) and owner.strip() else "Component"
        label_map[base_name] = _build_enriched_component_label(base_name, c)

    edges: List[Tuple[str, str]] = []

    if isinstance(integration_points, list):
        for ip in integration_points:
            if not isinstance(ip, dict):
                continue
            source = ip.get("source")
            target = ip.get("target")
            if not (isinstance(source, str) and source.strip() and isinstance(target, str) and target.strip()):
                continue
            source_label = _normalize_node_label(source)
            target_label = _normalize_node_label(target)
            if source_label in node_names and target_label in node_names and source_label != target_label:
                edge = (source_label, target_label)
                if edge not in edges:
                    edges.append(edge)

    for c in valid_components:
        this_name = c.get("component_name")
        if not isinstance(this_name, str) or not this_name.strip():
            continue
        this_label = _normalize_node_label(this_name)

        deps = c.get("dependencies") or []
        if not isinstance(deps, list):
            continue

        for dep in deps:
            if not isinstance(dep, str) or not dep.strip():
                continue
            dep_label = _normalize_node_label(dep)
            if dep_label in node_names and dep_label != this_label:
                edge = (dep_label, this_label)
                if edge not in edges:
                    edges.append(edge)

    if not edges:
        sequence_flows = lld.get("detailed_sequence_flows") if isinstance(lld, dict) else None
        if isinstance(sequence_flows, list):
            for flow in sequence_flows:
                if not isinstance(flow, dict):
                    continue
                steps = flow.get("steps")
                if not isinstance(steps, list):
                    continue
                ordered_steps = sorted(
                    (s for s in steps if isinstance(s, dict)),
                    key=lambda s: s.get("step_number") if isinstance(s.get("step_number"), (int, float)) else 0,
                )
                for step in ordered_steps:
                    source = step.get("from_participant")
                    target = step.get("to_participant")
                    if not (isinstance(source, str) and source.strip() and isinstance(target, str) and target.strip()):
                        continue
                    source_label = _normalize_node_label(source)
                    target_label = _normalize_node_label(target)
                    if source_label in node_names and target_label in node_names and source_label != target_label:
                        edge = (source_label, target_label)
                        if edge not in edges:
                            edges.append(edge)

    if not edges:
        if len(node_names) == 1:
            only = node_names[0]
            edges = [("Start", only), (only, "End")]
            lane_map["Start"] = "Component"
            lane_map["End"] = "Component"
            label_map.setdefault("Start", "Start")
            label_map.setdefault("End", "End")
        else:
            logger.warning(
                "No integration_points/dependencies/sequence_flows inferred between %d "
                "components; falling back to declaration-order chain", len(node_names)
            )
            for i in range(len(node_names) - 1):
                edges.append((node_names[i], node_names[i + 1]))

    if not edges:
        logger.warning("No edges inferred; using fallback Start->End")
        edges = [("Start", "End")]
        lane_map["Start"] = "Component"
        lane_map["End"] = "Component"
        label_map.setdefault("Start", "Start")
        label_map.setdefault("End", "End")

    return doc_name, edges, lane_map, label_map


# ============================================================
#  EDGE INFERENCE -- DISPATCHER (BOTH SCHEMAS)
# ============================================================

def _infer_edges_from_json() -> Tuple[str | None, List[Tuple[str, str]], Dict[str, str], Dict[str, str]]:
    """Schema-aware dispatcher: picks between the process-schema and
    design-document-schema edge inference logic based on which normalized
    JSON file is actually on disk (detect_schema_type_from_disk)."""
    if detect_schema_type_from_disk() == "design":
        return _infer_edges_from_design_json()
    return _infer_edges_from_process_json()


# ============================================================
#  DIAGRAM GENERATION (ALWAYS PRODUCES SOMETHING, BOTH SCHEMAS)
# ============================================================

def generate_clean_diagram() -> str:
    """
    Generates a refined flow diagram as a PNG, for EITHER a business
    process (BPMN-style swimlane diagram) or an architectural design
    document (component/integration diagram), depending on which
    normalized JSON file is present in output/. Saved to
    output/<name>_flow.png. Returns a message indicating success/failure.
    """
    logger.debug("Generating flow diagram...")

    try:
        is_design = detect_schema_type_from_disk() == "design"

        result = _infer_edges_from_json()
        if not result:
            if is_design:
                return "ERROR: Could not infer edges. Ensure output/design_data.json exists."
            return "ERROR: Could not infer edges. Ensure output/process_data.json exists."

        inferred_name, inferred_edges, lane_map, label_map = result
        default_title = "System Architecture" if is_design else "Process Architecture"
        final_name = (inferred_name or default_title).strip()
        edges = inferred_edges or []

        G = nx.DiGraph()
        G.add_edges_from(edges)

        default_lane = "Component" if is_design else "Process"
        for n in G.nodes():
            lane_map.setdefault(n, default_lane)
            label_map.setdefault(n, n)

        start_nodes = [n for n, d in G.in_degree() if d == 0]
        end_nodes = [n for n, d in G.out_degree() if d == 0]

        x_spacing, y_spacing = 5.0, -4.0
        nodes = list(G.nodes())
        lanes = sorted(list(set(lane_map.get(n, default_lane) for n in nodes)))
        lane_y_indices = {lane: idx for idx, lane in enumerate(lanes)}

        lane_positions = {lane: [] for lane in lanes}
        for n in nodes:
            lane = lane_map.get(n, default_lane)
            lane_positions[lane].append(n)

        pos = {}
        for lane, items in lane_positions.items():
            y = lane_y_indices[lane] * y_spacing
            for i, n in enumerate(items):
                x = i * x_spacing
                pos[n] = (x, y)

        fig, ax = plt.subplots(figsize=(18, 10))

        lane_colors = _get_lane_colormap(len(lanes))
        for i, lane in enumerate(lanes):
            y_coord = lane_y_indices[lane] * y_spacing
            ax.axhspan(y_coord - 1.8, y_coord + 1.8, color=lane_colors(i), alpha=0.10)
            ax.text(-3.0, y_coord, lane.upper(), va='center', ha='right',
                    fontsize=11, fontweight='bold', color="#555555")

        nx.draw_networkx_edges(
            G, pos, ax=ax, edge_color="#7f8c8d", arrows=True,
            arrowstyle='-|>', arrowsize=20, width=1.5,
            connectionstyle="arc3,rad=0.1", min_source_margin=30, min_target_margin=30
        )

        for node in nodes:
            x, y = pos[node]
            label = label_map.get(node, node)
            wrapped_text = "\n".join(textwrap.wrap(label, width=28))

            if node in start_nodes:
                fill_color, line_color, text_weight = "#15B615", "#006400", "bold"
            elif node in end_nodes:
                fill_color, line_color, text_weight = "#FF0000", "#8B0000", "bold"
            else:
                fill_color, line_color, text_weight = "#D5E8F7", "#2980B9", "medium"

            ax.plot(x, y, marker='o', markersize=62,
                    markeredgecolor=line_color, markerfacecolor=fill_color,
                    linestyle='None')

            ax.text(
                x, y, wrapped_text,
                ha="center", va="center",
                fontsize=9, fontweight=text_weight,
                bbox=dict(
                    facecolor="white", edgecolor=line_color,
                    boxstyle="round,pad=0.5", linewidth=1.5,
                )
            )

        if pos:
            x_vals, y_vals = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
            ax.set_xlim(min(x_vals) - 5.5, max(x_vals) + 5.5)
            ax.set_ylim(min(y_vals) - 3.5, max(y_vals) + 3.5)

        plt.title(f"{default_title}: {final_name}", fontsize=15, pad=30, fontweight='bold')
        plt.axis("off")

        default_out_filename = "design_flow.png" if is_design else "process_flow.png"
        out_filename = default_out_filename
        if final_name:
            out_filename = f"{safe_filename_component(final_name.lower())}_flow.png"
        out_path = paths.output_path(out_filename)

        fig.tight_layout()
        plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

        return f"Diagram successfully generated at {out_path}"

    except Exception as e:
        logger.error(f"Failed to generate diagram: {e}")
        return f"Diagram generation failed: {str(e)}"
