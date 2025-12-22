# ADK Business Process Architect

A specialized multi-agent suite built on the Google Agent Development Kit (ADK). This system automates the lifecycle of business process engineering—from initial requirement analysis and logical design to compliance auditing and professional document generation.

## ⚙️ Features

- **Multi-Agent Orchestration**: A lead "Process Architect" manages a specialized team for analysis, design, compliance, and documentation.
- **Human-in-the-Loop (HITL)**: Integrated feedback loop that pauses execution to allow users to refine or approve processes before final artifacts are created.
- **Compliance Guardrails**: Automatic auditing against sector-specific best practices (e.g., GDPR for Finance, HIPAA for Healthcare).
- **Automated Artifacts**: 
  - **Process Diagrams**: Generates high-resolution PNG flowcharts using Graphviz.
  - **Business Specifications**: Generates formatted `.docx` files containing the process logic and embedded diagrams.

---

## 🏗️ Repository Layout

```text
├── Dockerfile              # Container definition with Graphviz dependencies
├── requirements.txt        # Python dependencies (adk, docx, graphviz)
├── process_agents/
│   ├── __init__.py         # Package entry point (exports root_agent)
│   ├── agent.py            # Root Agent: Process Architect & HITL Orchestrator
│   ├── analysis_agent.py   # Specialist: Requirement extraction & Sector ID
│   ├── design_agent.py     # Specialist: Workflow logic & step definition
│   ├── compliance_agent.py # Auditor: Best practice & regulatory checks
│   └── doc_gen_agent.py    # Draftsman: Word & Diagram file generation
└── output/                 # Destination for generated .docx and .png files
```

---

## Requirements

Graphviz: Required for diagram generation.

macOS: brew install graphviz

Linux: sudo apt install graphviz

Google API Key: An active Gemini API key.

Python 3.12+: Stable Python environment recommended (avoid 3.14-dev for production).

See `requirements.txt` for version constraints used in your environment.

---

## Setup and Test Agent

To setup and test the agent, you can do the following.

This will allow the agent to run as a simple invocable script and not use a REST API to drive it.

```bash
    rm -r .venv
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    export GOOGLE_API_KEY=<YourKey>
```

## Test Deployment Emulation

To check that the agent is working correctly in the GCP ADK environment, you can use the web service.

```bash
    .venv/bin/python -m pip install --force-reinstall --no-cache-dir google-adk
    .venv/bin/adk web
```


---

## Docker Usage

**Build:**

```bash
docker build . -t adkprocesseng
```

**Interactive run:**

```bash
docker run -it --rm \
  -v $(pwd)/output:/app/output \
  -e GOOGLE_API_KEY="your_api_key" \
  process-architect "Design a customer refund process for an e-commerce platform." \
  adkprocesseng:latest
```

**Notes:**

- The Docker image runs the module `finance_agents.agent` as the container ENTRYPOINT. Arguments passed to `docker run` are forwarded to the module.

---

## The Workflow Pattern

* Analyze: Takes raw descriptions and identifies the industry sector and key actors.
* Design: Converts the analysis into a logical, step-by-step workflow.
* Review: The Compliance Agent audits the design. If errors are found, it sends it back for redesign.
* Feedback: The system pauses and asks: "Does this design meet your requirements?"
* Publish: Once approved, the system renders a PNG diagram and compiles a professional Business Specification document in the output/ folder.

---

## Sample Prompts

- "Analyze our current hiring process and suggest a more efficient, GDPR-compliant version for the HR sector."
- "Design a detailed business process for managing inventory stock-outs in a retail environment."

--- 

## Issues to keep in mind

- If you are using the free tier of Gemini to run this app, i.e. the `GOOGLE_API_KEY`, then you may well run into resource limits if you attempt to generate a "real" portfolio of 10+ stocks etc. Other operations requiring many tokens may also hit similar limits.
- As this sample code is presented for demo purposes only, NO WARRANTY OR OTHER GUARANTEES OF FUNCATIONALITY ARE PROVIDED. See [LICENSE](https://github.com/tpayne/agentic-ai-adk/blob/main/LICENSE) for more details.
