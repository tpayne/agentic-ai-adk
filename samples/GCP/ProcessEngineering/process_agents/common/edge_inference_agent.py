# process_agents/edge_inference_agent.py
#
# Triggers swimlane/architecture diagram generation for either a business
# process or an architectural design document. Logic lives in
# process_toolkit.docgen.edge_inference (shared with the neuro-san port) --
# this file is just the ADK agent wrapper + CLI test harness.

import json
import os
import sys

from process_toolkit.docgen.edge_inference import _infer_edges_from_json, generate_clean_diagram

from .agent_wrappers import ProcessAgent

edge_inference_agent = ProcessAgent(
    name="Edge_Inference_Agent",
    description="Triggers swimlane/architecture diagram generation for either a business process or an architectural design document, based only on the normalized JSON already on disk.",
    instruction_file="common/edge_inference_agent.txt",
    tools=[generate_clean_diagram],
)

# ============================================================
# __main__ TEST HARNESS (DIRECT EXECUTION WITHOUT LLM)
# ============================================================
if __name__ == "__main__":

    print("\n=== Edge Inference Agent – Direct Test Harness ===")
    if len(sys.argv) < 3:
        print("Usage: python edge_inference_agent.py <process|design> <path_to_json>")
        print("Example: python edge_inference_agent.py process sample.json")
        print("Example: python edge_inference_agent.py design sample_design.json")
        sys.exit(1)

    schema_arg = sys.argv[1].strip().lower()
    json_path = sys.argv[2]
    if schema_arg not in ("process", "design"):
        print(f"ERROR: First argument must be 'process' or 'design', got: {schema_arg}")
        sys.exit(1)
    if not os.path.exists(json_path):
        print(f"ERROR: File not found: {json_path}")
        sys.exit(1)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {e}")
        sys.exit(1)

    os.makedirs("output", exist_ok=True)
    target_path = "output/design_data.json" if schema_arg == "design" else "output/process_data.json"
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Loaded JSON and wrote to {target_path}")

    name, edges, lane_map, label_map = _infer_edges_from_json()
    print("\nInferred name:", name)
    print("Inferred edges:")
    for e in edges:
        print(" ", e)

    print("\nGenerating diagram...")
    result = generate_clean_diagram()
    print("\nDiagram saved to:", result)
    print("=== Done ===\n")
