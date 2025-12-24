# ADK Business Process Architect

A specialized multi-agent suite built on the Google Agent Development Kit (ADK). This system automates the lifecycle of business process engineering—from initial requirement analysis and logical design to compliance auditing and professional document generation.

## ⚙️ Features

- **Autonomous Multi-Agent Pipeline**: A high-velocity "Process Architect" pipeline that moves from raw requirements to final artifacts without requiring manual intervention. The **Analysis Agent** sets the scope, the **Design/Compliance Loop** iteratively refines the logic, and the **Normalizer** locks the data for production.
- **Zero-Loss Data Normalization**: Features a specialized **JSON Normalizer Agent** that acts as a data-sanitization gate. It transforms free-form architectural designs into a stabilized, enriched document schema, ensuring that complex workflows (30+ steps) are preserved with 100% integrity.
- **Self-Auditing Compliance Gate**: The **Compliance Agent** acts as an automated "Release Manager." It forces the Design Agent into a recursive revision loop if regulatory or security gaps are detected, only releasing the process to the documentation stage once "COMPLIANCE APPROVED" is achieved.
- **Automated High-Fidelity Artifacts**: 
  - **Process Diagrams**: Dynamically infers workflow sequences from normalized data to generate high-resolution PNG flowcharts via **NetworkX**.
  - **Engineering Specifications**: Generates professional `.docx` files using a logic-driven rendering engine. Includes **Automated Table of Contents**, **Stakeholder Matrix Tables**, and structured **Appendix** sections for deep-dive technical data.

### 🚀 Autonomous Execution Flow

1.  **Requirement Extraction**: The Analysis Agent converts user intent into a machine-readable JSON Requirements Specification.
2.  **Iterative Refinement**: The Design and Compliance agents cycle automatically, refining the process until all operational and regulatory criteria are met.
3.  **Schema Stabilization**: The Normalizer Agent maps the finalized design to a strict documentation contract, saving the state to `process_data.json`.
4.  **Artifact Engineering**: The Documentation Agent reads the local state to render complex diagrams and the final professional specification.

---

## 🏗️ Repository Layout

```text
├── Dockerfile
├── output
│   ├── agile_scrum_sdlc_for_web_development_flow.png
│   ├── agile_scrum_sdlc_for_web_development_specification.docx
│   ├── inventory_stock-out_management_flow.png
│   ├── Inventory_Stock-Out_Management.docx
│   └── process_data.json
├── process_agents
│   ├── __init__.py
│   ├── __pycache__
│   │   ├── __init__.cpython-314.pyc
│   │   ├── agent.cpython-314.pyc
│   │   ├── analysis_agent.cpython-314.pyc
│   │   ├── compliance_agent.cpython-314.pyc
│   │   ├── design_agent.cpython-314.pyc
│   │   ├── doc_gen_agent.cpython-314.pyc
│   │   ├── doc_generation_agent.cpython-314.pyc
│   │   └── json_normalizer_agent.cpython-314.pyc
│   ├── agent.py
│   ├── analysis_agent.py
│   ├── compliance_agent.py
│   ├── design_agent.py
│   ├── doc_generation_agent.py
│   └── json_normalizer_agent.py
├── README.md
└── requirements.txt
```

---

## 🛠 Requirements

- **Graphviz**: Required for advanced layout and alternative diagram generation formats.
    - **macOS**: `brew install graphviz`
    - **Linux**: `sudo apt install graphviz`
- **Google API Key**: An active Gemini API key (set as `GOOGLE_API_KEY` in your environment).
- **Python 3.12+**: A stable Python environment is recommended for consistent execution of the `docx` and `networkx` libraries.
- **Dependencies**: See `requirements.txt` for specific version constraints, including `python-docx`, `networkx`, and `matplotlib`.

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

- None

---

## 🔄 The Workflow Pattern

The system follows a high-precision, four-stage autonomous pipeline designed to move from unstructured intent to professional documentation without human intervention.

- **Analyze**: The **Analysis Agent** performs a deep scan of raw descriptions to identify the industry sector, core stakeholders, and success metrics, outputting a machine-readable Requirements Specification.
- **Design & Refine**: The **Design Agent** architects a logical, step-by-step workflow. This is immediately passed to the **Compliance Agent** for a recursive audit. If regulatory gaps or security risks are detected, the system triggers an automatic redesign loop (up to 5 iterations) until a "COMPLIANCE APPROVED" state is reached.
- **Normalize**: Once the design is locked, the **JSON Normalizer Agent** sanitizes and enriches the data. It maps free-form architectural ideas into a strict, document-ready schema, ensuring that complex details—such as toolchains, metrics, and extended steps—are preserved for the final artifact.
- **Publish**: The **Document Generation Agent** executes the final build. It reads the local state and uses a specialized rendering engine to:
    - **Render** a high-resolution PNG flowchart using NetworkX logic.
    - **Compile** a professional Business Specification (`.docx`) featuring a dynamic Table of Contents, stakeholder matrix, and recursive formatting that ensures zero data loss.

---

## Sample Prompts

- "Create me an Enterprise Archotecture and Business enterprise architecture SDLC process. I need to be able to track EA decisions, outcomes, progress and escalate when required."
- "Design a detailed business process for managing inventory stock-outs in a retail environment."
- "Create an SDLC development and release process for a WebDev application and microservices using an Agile Scrum 2.0 base"

--- 

## Issues to keep in mind

- If you are using the free tier of Gemini to run this app, i.e. the `GOOGLE_API_KEY`, then you may well run into resource limits if you attempt to generate a "real" portfolio of 10+ stocks etc. Other operations requiring many tokens may also hit similar limits.
- As this sample code is presented for demo purposes only, NO WARRANTY OR OTHER GUARANTEES OF FUNCATIONALITY ARE PROVIDED. See [LICENSE](https://github.com/tpayne/agentic-ai-adk/blob/main/LICENSE) for more details.
