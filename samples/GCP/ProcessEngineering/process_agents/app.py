from flask import Flask, render_template, jsonify
from process_agents.utils import load_full_process_context
import json

app = Flask(__name__)

def build_process_model():
    # load_full_process_context() already returns a dict, not JSON text.
    ctx = load_full_process_context()

    # If someone ever changes the loader to return JSON text, handle that too.
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except Exception:
            print("ERROR: load_full_process_context() returned invalid JSON text")
            ctx = {}

    master = ctx.get("master_process", {})
    subprocesses = ctx.get("subprocesses", [])

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
    return render_template("index.html")

@app.route("/api/process")
def api_process():
    return jsonify(build_process_model())

def main():
    app.run(debug=True, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()