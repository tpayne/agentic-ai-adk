# ADK Business Process Architect

This repo is for hosting a specialized multi-agent suite built on the Google Agent Development Kit (ADK). This system automates the lifecycle of business process engineering from defining the initial requirement analysis to designing a process based on those requirements, testing it to ensure compliance with best industry standards, running simulations of the process to identify potential bottlenecks, and then finally, creating a process document hosting the design.

**NOTE**
* This ADK sample should be regarded as PoC status only. The LLMs can sometimes fail with unpredictable results.
* The code used in this sample could also be better refined. There are currently safeguards and functions which could be optimised, removed or trimmed down in size.

## ⚙️ Features

The ADK pipeline offers the following key features:

- **Autonomous Multi-Agent Pipeline**: A high-velocity "Process Architect" workflow that transforms raw requirements into final artifacts without manual intervention. The **Analysis Agent** defines the scope, while the **Design/Compliance Loop** iteratively refines the logic to ensure alignment with governance standards. The **Normalizer Agent** then locks the data into JSON format for production use.
- **Zero-Loss Data Normalization**: Utilizes a specialized **JSON Normalizer Agent** as a data-sanitization gate. It converts free-form architectural designs into a stable, enriched document schema, preserving complex workflows (30+ steps) with complete integrity. This JSON drives document and artifact creation.
- **Self-Auditing Compliance Gate**: The **Compliance Agent** acts as an automated "Release Manager," triggering recursive revisions if regulatory or security gaps are found. The process advances to documentation only after achieving "COMPLIANCE APPROVED" status.
- **Self-Auditing Simulation Gate**: The **Simulation Agent** subjects the compliant process to rigorous Monte Carlo simulations to identify bottlenecks. It then optimizes the process or reports issues in the final documentation.
- **Automated High-Fidelity Artifacts**: 
    - **Process Diagrams**: Automatically generates level 1 and 2 workflow diagrams and embeds them in the process document.
    - **Process Document**: Produces a detailed Word document — adhering to ITIL and ISO standards — describing the requested business process and related information.

### 🚀 Autonomous Execution Flow

1.  **Requirement Extraction**: The Analysis Agent converts user intent into a machine-readable JSON Requirements Specification.
2.  **Iterative Refinement**: The Design and Compliance agents cycle automatically, refining the process until all operational and regulatory criteria are met. This also includes testing and optimizing the process for potential bottlenecks. 
3.  **Schema Stabilization**: The Normalizer Agent maps the finalized design to a strict documentation contract, saving the state to `process_data.json`.
4.  **Artifact Engineering**: The Documentation Agent reads the local state to render complex diagrams and the final professional specification.

---

## 🏗️ Repository Layout

The contents of this sample repo are as follows.

```text
.
├── Dockerfile
├── examples
│   ├── DataCentreMigration
│   │   ├── data_centre_migration_with_progress_tracking_and_escalation_flow.png
│   │   ├── Data_Centre_Migration_with_Progress_Tracking_and_Escalation.docx
│   │   └── process_data.json
│   └── EnergyProvider
│       ├── Business_Customer_Incident_Management.docx
│       └── process_data.json
├── process_agents
│   ├── __init__.py
│   ├── agent.py
│   ├── analysis_agent.py
│   ├── compliance_agent.py
│   ├── design_agent.py
│   ├── doc_generation_agent.py
│   ├── edge_inference_agent.py
│   ├── json_normalizer_agent.py
│   ├── json_review_agent.py
│   ├── json_writer_agent.py
│   ├── simulation_agent.py
│   ├── step_diagram_agent.py
│   ├── subprocess_driver_agent.py
│   ├── subprocess_generator_agent.py
│   └── subprocess_writer_agent.py
├── README.md
└── requirements.txt

```

---

## 🛠 Requirements

- **Google API Key**: An active Gemini API key (set as `GOOGLE_API_KEY` in your environment).
- **Python 3.12+**: A stable Python environment is recommended for consistent execution of the `docx` and `networkx` libraries.
- **Dependencies**: See `requirements.txt` for specific version constraints and required Python packages.

---

## Setup and Test Agent

To set up and test the agent, you can do the following.

This will allow the agent to run as a simple invocable script.

```bash
    rm -r .venv
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    export GOOGLE_API_KEY=<YourKey>
    .venv/bin/adk run process_agents
```

## Test Deployment Emulation using WebUI

To check that the agent is working correctly in the GCP ADK environment, you can use the web service.

```bash
    .venv/bin/python -m pip install --force-reinstall --no-cache-dir google-adk
    .venv/bin/adk web
```

---

## Docker Usage

A simple Docker image is provided that allows you to build and run the agent pipeline stand-alone.

You can use the following commands to build and then run the image.

**Build:**

```bash
docker build . -t adkprocesseng
```

**Interactive run:**

```bash
docker run -it --rm \          
    -v $(pwd)/output:/app/output \
    -e GOOGLE_API_KEY="${GOOGLE_API_KEY}" \
    adkprocesseng:latest
```

**Notes:**

- The ADK will install as part of the run, and you will be using the `adk run` interface.

---

## Sample Prompts

- "Create me an Enterprise Architecture and Business Enterprise Architecture SDLC process. I need to be able to track EA decisions, outcomes, progress, and escalate when required."
- "Design a detailed business process for managing inventory stock-outs in a retail environment."
- "Create an SDLC development and release process for a WebDev application and microservices using an Agile Scrum 2.0 base."

--- 

## Issues to keep in mind

- If you are using the free tier of Gemini to run this app, i.e. the `GOOGLE_API_KEY`, then you may well run into resource limits if you attempt to generate a "real" portfolio of 10+ stocks etc. Other operations requiring many tokens may also hit similar limits.
- As this sample code is presented for demo purposes only, NO WARRANTY OR OTHER GUARANTEES OF FUNCTIONALITY ARE PROVIDED. See [LICENSE](https://github.com/tpayne/agentic-ai-adk/blob/main/LICENSE) for more details.
- You must ALWAYS validate the process designed and ensure it complies to any required standards before using it. You can also modify the process JSON directly if you wish and then use `python` to run the diagramming agents and documentation agents directly. This will regenerate the artifacts as required.
- The exit loop logic needs tuning as sometimes it will not be invoked and burn needless tokens. This effects both the design agent loop and the JSON normalization loop. Sometimes it is caused by the size of the LLM payloads, sometimes by hallucinations and sometimes by LLMs not calling tools.
- If the LLM fails to call a tool, then you might need to rephrase the prompt or rerun the process. The document generation - including the diagrammer and Word document generator can be run manually if so required. See the Python code with "__main__" routines.
