"""
app.py

Flask application for serving process engineering models and APIs.

This app loads process context data, exposes it via a REST API, and serves a web UI.
"""

from flask import Flask, render_template, jsonify
from process_agents.utils import (
    load_full_process_context,
    getProperty
)

import json

import logging
logger = logging.getLogger("ProcessArchitect.Apps")

# Initialize Flask app with static folder mapped to root URL
app = Flask(
    __name__,
    static_folder='public',      # Folder for static files (e.g., JS, CSS)
    static_url_path=''           # Serve static files at root URL
)

def build_process_model():
    ctx = load_full_process_context()
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except Exception:
            ctx = {}

    master = ctx.get("master_process", {})
    subprocesses = ctx.get("subprocesses", [])

    # Index subprocesses by their parent step name
    subprocess_index = {
        sp.get("step_name"): sp.get("subprocess_flow", [])
        for sp in subprocesses if sp.get("step_name")
    }

    return {
        # Core Identity
        "process_name": master.get("process_name", "Unknown Process"),
        "version": master.get("version", "1.0"),
        "owner": master.get("owner", "N/A"),
        "domain": master.get("domain", "N/A"),
        
        # Global Metadata for Sidebar
        "assumptions": master.get("assumptions", []),
        "constraints": master.get("constraints", []),
        "goals": master.get("goals", []),
        "metrics": master.get("metrics", []),
        "infrastructure": master.get("infrastructure_requirements", []),
        "global_change_mgmt": master.get("change_management", []),
        "global_improvement": master.get("continuous_improvement", []),
        
        # Process Structure
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

# Version GET handler
@app.route("/version")
def version() -> Any:
    return jsonify({"version":"1.0"})

# Status GET probe handler
@app.route("/status")
def status() -> Any:
    return jsonify({"status":"live"})

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
    applicationName = getProperty("APP")
    logger.debug(f"Application {applicationName} running...")    

    app.run(debug=getProperty("debug"), 
            host=getProperty("host"), 
            port=getProperty("port"))

if __name__ == "__main__":
    main()