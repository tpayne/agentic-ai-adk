# process_agents/edge_inference_agent.py

from google.adk.agents import LlmAgent
import os
import re
import json
import traceback
import networkx as nx
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger("ProcessArchitect.EdgeInference")


# -----------------------------------
# Utility: Generate simple flowchart
# -----------------------------------

def generate_clean_diagram(process_name: str, edge_list_json: str) -> str:
    """
    Generates a simple flowchart using a list of strict 2-tuple pairs:
    e.g. [["Start", "Step 1"], ["Step 1", "End"]]

    EXPECTATION:
    - edge_list_json is a JSON-encoded list of [from, to] pairs, derived
      from the normalized JSON (e.g. from step order or phase sequence).
      The LLM agent is responsible for deciding the most meaningful flow.
    """
    try:
        logger.info("Generating process flow diagram...")
        os.makedirs("output", exist_ok=True)
        filename = f"output/{process_name.lower().replace(' ', '_')}_flow.png"

        clean_edges = re.sub(
            r'^```json\s*|```$',
            '',
            edge_list_json.strip(),
            flags=re.MULTILINE
        )

        try:
            edges_obj = json.loads(clean_edges)
        except Exception:
            traceback.print_exc()
            return "None"

        edges = []
        if isinstance(edges_obj, list):
            for item in edges_obj:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    edges.append((str(item[0]), str(item[1])))

        if not edges:
            return "None"

        G = nx.DiGraph()
        G.add_edges_from(edges)

        plt.figure(figsize=(10, 6))
        pos = nx.spring_layout(G)
        nx.draw(
            G,
            pos,
            with_labels=True,
            node_color='lightblue',
            edge_color='gray',
            node_size=2500,
            font_size=8,
        )
        try:
            plt.tight_layout()
        except Exception:
            pass
        plt.savefig(filename)
        plt.close()
        return filename
    except Exception:
        traceback.print_exc()
        return "None"

# -----------------------------------
# Edge Inference Agent
# -----------------------------------
edge_inference_agent = LlmAgent(
    name="Edge_Inference_Agent",
    model="gemini-2.0-flash-001",
    description="Infers flowchart edges from normalized process JSON and generates a diagram.",
    instruction=(
        "You are a Process Flow Inference Specialist.\n\n"
        "CONTEXT:\n"
        "- The normalized, enriched process JSON has already been saved to "
        "  output/process_data.json by a previous agent.\n"
        "- Your task is to infer a clear, ordered flow for the process and generate "
        "  a diagram using the generate_clean_diagram tool.\n\n"
        "DATA CONTRACT:\n"
        "- Assume output/process_data.json contains a JSON object with at least:\n"
        "    {\n"
        "      \"process_name\": string,\n"
        "      \"process_steps\": [\n"
        "         {\n"
        "           \"step_number\": number (optional),\n"
        "           \"step_name\": string,\n"
        "           ...\n"
        "         },\n"
        "         ...\n"
        "      ]\n"
        "    }\n"
        "- You MUST infer a list of directed edges representing the primary flow.\n"
        "- Start with a simple linear flow in order of step_number or list order:\n"
        "    [ [\"Step A\", \"Step B\"], [\"Step B\", \"Step C\"], ... ]\n"
        "- If step_number is missing, use the list index order.\n"
        "- Use the most human-readable step_name values as node labels.\n\n"
        "TOOL CALL CONTRACT:\n"
        "- You MUST call generate_clean_diagram exactly once.\n"
        "- The first argument MUST be process_name.\n"
        "- The second argument MUST be a JSON string representing the edge list:\n"
        "    [ [\"Node 1\", \"Node 2\"], [\"Node 2\", \"Node 3\"], ... ]\n"
        "- Do NOT include markdown fences in the JSON string.\n\n"
        "INTERACTION RULES:\n"
        "- Do NOT ask the user any questions.\n"
        "- Do NOT output natural language.\n"
        "- Your ONLY action is to infer the edges and call generate_clean_diagram.\n"
        "- After the tool call, STOP.\n"
    ),
    tools=[generate_clean_diagram],
)
