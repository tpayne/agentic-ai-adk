"""
app.py

Flask application for serving process engineering models and APIs.

This app loads process context data, exposes it via a REST API, and serves a web UI.
"""

from flask import Flask, render_template, jsonify
from process_agents.utils import load_full_process_context
import json

# Initialize Flask app with static folder mapped to root URL
app = Flask(
    __name__,
    static_folder='public',      # Folder for static files (e.g., JS, CSS)
    static_url_path=''           # Serve static files at root URL
)

def build_process_model():
    """
    Loads the full process context and constructs a model dictionary
    for use in the API response.

    Returns:
        dict: Process model containing process name, stakeholders,
              level 1 steps, and a subprocess index.
    """
    ctx = load_full_process_context()
    # If context is a JSON string, parse it
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except Exception:
            ctx = {}

    master = ctx.get("master_process", {})
    subprocesses = ctx.get("subprocesses", [])

    # Build an index mapping step names to their subprocess flows
    subprocess_index = {
        sp.get("step_name"): sp.get("subprocess_flow", [])
        for sp in subprocesses
        if sp.get("step_name")
    }

    return {
        "process_name": master.get("process_name", "Unknown Process"),
        "stakeholders": master.get("stakeholders", []),
        "level1_steps": master.get("process_steps", []),
        "subprocess_index": subprocess_index,
    }

@app.route("/")
def index():
    """
    Serves the main HTML page.
    """
    return render_template("index.html")

@app.route("/api/process")
def api_process():
    """
    API endpoint that returns the process model as JSON.
    """
    return jsonify(build_process_model())

def main():
    """
    Entry point for running the Flask app.
    Uses 0.0.0.0 for container/remote visibility.
    """
    app.run(debug=True, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()