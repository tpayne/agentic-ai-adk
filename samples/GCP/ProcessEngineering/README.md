# ADK Business Process Architect

This sample hosts a specialized multi-agent suite built on the Google Agent Development Kit (ADK). The system automates the lifecycle of business process engineering from initial requirements through to generating professional process documentation and validated workflows.

Basically, this agent will take a raw prompt and design, test, and document a full end-to-end process based on that business process request.

In other words, this agent is used for automated process engineering - going from very rough requirements through to tested documentation. A handy tool for consultants.

--- 

## Status

This sample has been tested and is generally stable; however, it may occasionally produce overly verbose chat outputs.

Treat this ADK sample as a BETA. While current Large Language Models (LLMs) are increasingly reliable, you should always verify the tool's output to ensure it meets your specific requirements and remains stable.

---

## Known issues

The following are a list of known issues: -
- Diagram Layouts: Generated diagrams may occasionally be clipped or laid out sub-optimally. You can often improve the visualization by modifying the process JSON and regenerating the diagram.
- Agent "Chattiness": While agents are instructed to remain quiet, LLMs may occasionally disregard these constraints and output unnecessary JSON or tooling commentary. In most cases, these outputs can be safely ignored.

---

## Notes

- Treat this ADK sample as a BETA. Large language models can produce unpredictable results.
- The sample code could be refined. Some safeguards and helper functions can be optimized, removed, or reduced.
- This agent is only able to create processes and cannot hold general conversations or modify processes based on queries or test proposed process flows based on user input. If I have the time or need, I might add this functionality in the future. **This functionality is now mostly implemented, but not completely**
- If you are generating a new process from scratch, then it would be best to remove the `output/` sub-directory as it may contain old process files. 
- However, if you are looking to modify or query an existing process, then you MUST leave the `output/` sub-directory alone as this is used as input for the process queries and reviews. If you delete the directory is this case, then there will be no process definitions to read.
- Sometimes the root agent gets confused as to which agent to use to address a query. If you get this, you can change to prompt to something like **"using the Consulting Agent...."** and it will use the right one. Agents available are: -
    * Consulting Agent for general queries
    * Simulation Agent for running simulations
    * Scenario Testing Agent for running "what if" type queries

---

## ⚙️ Features

The ADK pipeline provides:

- **Autonomous Multi-Agent Pipeline**: A high-velocity "Process Architect" workflow that transforms raw requirements into final artifacts without manual intervention. The Analysis Agent converts natur[...]
- **Zero-Loss Data Normalization**: A JSON Normalizer Agent sanitizes and stabilizes free-form design outputs to a fixed, enriched document schema.
- **Self-Auditing Compliance Gate**: A Compliance Agent acts as an automated release manager, triggering recursive revisions if regulatory or security gaps are found and preventing progression until r[...]
- **Self-Auditing Simulation Gate**: A Simulation Agent runs Monte Carlo-style simulations to identify bottlenecks and suggests optimizations or reports unresolved issues.
- **Automated High-Fidelity Artifacts**:
  - Process diagrams (level 1 and 2) embedded in the process document.
  - A professional Word document describing the business process and related information, aligned to ITIL and ISO-style conventions.

---

### 🚀 Autonomous Execution Flow

1. **Requirement Extraction**: The Analysis Agent converts user intent into a machine-readable JSON Requirements Specification.
2. **Iterative Refinement**: Design and Compliance agents loop, refining the process until operational and regulatory criteria are satisfied. This cycle includes testing and optimization.
3. **Schema Stabilization**: The Normalizer Agent maps the finalized design to a stable documentation contract and saves the state to `process_data.json`.
4. **Artifact Engineering**: The Documentation Agent renders diagrams and generates the final specification (Word document) from the local state.

---

## 🏗️ Repository Layout

```
.
├── CODE_OF_CONDUCT.md
├── CONTRIBUTORS.md
├── Dockerfile
├── examples
│   ├── AgileSAFE
│   │   ├── iteration_feedback.json
│   │   ├── process_data.json
│   │   ├── safe_sdlc_process_flow.png
│   │   ├── SAFe_SDLC_Process.docx
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── Innovation_and_Planning_(IP)_Iteration.png
│   │   │   ├── Inspect_and_Adapt.png
│   │   │   ├── Iteration_Execution.png
│   │   │   ├── PI_Planning.png
│   │   │   ├── Pre-PI_Planning.png
│   │   │   ├── Release.png
│   │   │   └── System_Demos.png
│   │   └── subprocesses
│   │       ├── Innovation_and_Planning_(IP)_Iteration.json
│   │       ├── Inspect_and_Adapt.json
│   │       ├── Iteration_Execution.json
│   │       ├── PI_Planning.json
│   │       ├── Pre-PI_Planning.json
│   │       ├── Release.json
│   │       └── System_Demos.json
│   ├── AgileSCRUM
│   │   ├── agile_sdlc_using_scrum_flow.png
│   │   ├── Agile_SDLC_using_Scrum.docx
│   │   ├── process_data.json
│   │   ├── process_flow.png
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── Backlog_Refinement.png
│   │   │   ├── Daily_Scrum.png
│   │   │   ├── Product_Backlog_Creation.png
│   │   │   ├── Sprint_Planning.png
│   │   │   ├── Sprint_Retrospective.png
│   │   │   └── Sprint_Review.png
│   │   └── subprocesses
│   │       ├── Backlog_Refinement.json
│   │       ├── Daily_Scrum.json
│   │       ├── Product_Backlog_Creation.json
│   │       ├── Sprint_Planning.json
│   │       ├── Sprint_Retrospective.json
│   │       └── Sprint_Review.json
│   ├── DataCentreMigration
│   │   ├── data_centre_migration_with_progress_tracking_and_escalation_flow.png
│   │   ├── Data_Centre_Migration_with_Progress_Tracking_and_Escalation.docx
│   │   └── process_data.json
│   ├── DataGovern
│   │   ├── data_governance_and_management_process_for_ai_flow.png
│   │   ├── Data_Governance_and_Management_Process_for_AI.docx
│   │   ├── iteration_feedback.json
│   │   ├── process_data.json
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── Define_Data_Governance_Policies.png
│   │   │   ├── Enforce_Security_Protocols.png
│   │   │   ├── Identify_Data_Owners.png
│   │   │   ├── Implement_Data_Quality_Checks.png
│   │   │   └── Monitor_Data_Usage.png
│   │   └── subprocesses
│   │       ├── Define_Data_Governance_Policies.json
│   │       ├── Enforce_Security_Protocols.json
│   │       ├── Identify_Data_Owners.json
│   │       ├── Implement_Data_Quality_Checks.json
│   │       └── Monitor_Data_Usage.json
│   ├── EnergyProvider
│   │   ├── Business_Customer_Incident_Management.docx
│   │   └── process_data.json
│   ├── GodRole
│   │   ├── iteration_feedback.json
│   │   ├── process_data.json
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── Atmospheric_and_Hydrological_Development.png
│   │   │   ├── Autonomous_Operation.png
│   │   │   ├── Biodiversity_Expansion.png
│   │   │   ├── Conceptualization_and_Planning.png
│   │   │   ├── Ecosystem_Creation.png
│   │   │   ├── Geological_Formation.png
│   │   │   ├── Intelligent_Life_Development.png
│   │   │   └── World_Stabilization.png
│   │   ├── subprocesses
│   │   │   ├── Atmospheric_and_Hydrological_Development.json
│   │   │   ├── Autonomous_Operation.json
│   │   │   ├── Biodiversity_Expansion.json
│   │   │   ├── Conceptualization_and_Planning.json
│   │   │   ├── Ecosystem_Creation.json
│   │   │   ├── Geological_Formation.json
│   │   │   ├── Intelligent_Life_Development.json
│   │   │   └── World_Stabilization.json
│   │   ├── world_creation_flow.png
│   │   └── World_Creation.docx
│   ├── HRAI
│   │   ├── genai_augmented_hr_process_flow.png
│   │   ├── GenAI_Augmented_HR_Process.docx
│   │   ├── iteration_feedback.json
│   │   ├── process_data.json
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── CV_Review.png
│   │   │   ├── Employee_Grievances.png
│   │   │   ├── Employee_Reviews.png
│   │   │   ├── HR_Reporting.png
│   │   │   ├── Job_Specification_Creation.png
│   │   │   ├── Onboarding.png
│   │   │   └── Training_and_Development.png
│   │   └── subprocesses
│   │       ├── CV_Review.json
│   │       ├── Employee_Grievances.json
│   │       ├── Employee_Reviews.json
│   │       ├── HR_Reporting.json
│   │       ├── Job_Specification_Creation.json
│   │       ├── Onboarding.json
│   │       └── Training_and_Development.json
│   ├── LiveRuns
│   │   ├── sample_consultSimulation_agents.md
│   │   └── sample_pharma_queries.md
│   ├── PharmaDrugDev
│   │   ├── drug_development_value_chain_flow.png
│   │   ├── Drug_Development_Value_Chain.docx
│   │   ├── iteration_feedback.json
│   │   ├── process_data.json
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── Clinical_Development.png
│   │   │   ├── Commercialization.png
│   │   │   ├── Discovery_and_Pre-Clinical.png
│   │   │   ├── Manufacturing.png
│   │   │   └── Regulatory_Approval.png
│   │   └── subprocesses
│   │       ├── Clinical_Development.json
│   │       ├── Commercialization.json
│   │       ├── Discovery_and_Pre-Clinical.json
│   │       ├── Manufacturing.json
│   │       └── Regulatory_Approval.json
│   ├── SaaS
│   │   ├── iteration_feedback.json
│   │   ├── process_data.json
│   │   ├── saas_l0_value_chain_flow.png
│   │   ├── SaaS_L0_Value_Chain.docx
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── Corporate_Functions.png
│   │   │   ├── Customer_Success.png
│   │   │   ├── Go-To-Market.png
│   │   │   ├── Product_Strategy.png
│   │   │   ├── SDLC.png
│   │   │   └── Strategic_Management.png
│   │   └── subprocesses
│   │       ├── Corporate_Functions.json
│   │       ├── Customer_Success.json
│   │       ├── Go-To-Market.json
│   │       ├── Product_Strategy.json
│   │       ├── SDLC.json
│   │       └── Strategic_Management.json
│   ├── StockInventory
│   │   ├── inventory_stock-out_handling_process_flow.png
│   │   ├── Inventory_Stock-out_Handling_Process.docx
│   │   ├── process_data.json
│   │   ├── simulation_results.json
│   │   ├── step_diagrams
│   │   │   ├── Immediate_Action.png
│   │   │   ├── Inventory_Replenishment.png
│   │   │   ├── Order_Fulfillment.png
│   │   │   ├── Order_Placement.png
│   │   │   ├── Preventive_Measures.png
│   │   │   ├── Root_Cause_Analysis.png
│   │   │   ├── Stock-out_Identification.png
│   │   │   └── Verification_and_Documentation.png
│   │   └── subprocesses
│   │       ├── Backorder_Management.json
│   │       ├── Data_Security_Audit.json
│   │       ├── Emergency_Order__if_necessary_.json
│   │       ├── Immediate_Action.json
│   │       ├── Inventory_Replenishment.json
│   │       ├── Order_Fulfillment.json
│   │       ├── Order_Placement.json
│   │       ├── Preventive_Measures.json
│   │       ├── Restocking.json
│   │       ├── Review_and_Prevention.json
│   │       ├── Root_Cause_Analysis.json
│   │       ├── Stock-out_Identification.json
│   │       └── Verification_and_Documentation.json
│   └── TOGAF
│       ├── approval.json
│       ├── iteration_feedback.json
│       ├── logs
│       │   ├── pipeline_20260209_212641.log
│       │   ├── runtime_errors.log
│       │   └── runtime_outputs.log
│       ├── process_data.json
│       ├── simulation_results.json
│       ├── step_diagrams
│       │   ├── 1._Architecture_Vision.png
│       │   ├── 2._Business_Architecture.png
│       │   ├── 3._Information_Systems_Architecture.png
│       │   ├── 4._Technology_Architecture.png
│       │   ├── 5._Opportunities_&_Solutions.png
│       │   ├── 6._Migration_Planning.png
│       │   ├── 7._Implementation_Governance.png
│       │   ├── 8._Architecture_Change_Management.png
│       │   └── 9._Architecture_Monitoring.png
│       ├── subprocesses
│       │   ├── 1._Architecture_Vision.json
│       │   ├── 2._Business_Architecture.json
│       │   ├── 3._Information_Systems_Architecture.json
│       │   ├── 4._Technology_Architecture.json
│       │   ├── 5._Opportunities_&_Solutions.json
│       │   ├── 6._Migration_Planning.json
│       │   ├── 7._Implementation_Governance.json
│       │   ├── 8._Architecture_Change_Management.json
│       │   └── 9._Architecture_Monitoring.json
│       ├── togaf_enterprise_architecture_management_flow.png
│       └── TOGAF_Enterprise_Architecture_Management.docx
├── images
│   ├── image001.png
│   ├── image002.png
│   ├── image003.png
│   └── image004.png
├── instructions
│   ├── agent.txt
│   ├── analysis_agent.txt
│   ├── compliance_agent.txt
│   ├── consultant_agent.txt
│   ├── design_agent.txt
│   ├── doc_generation_agent.txt
│   ├── edge_inference_agent.txt
│   ├── grounding_agent.txt
│   ├── json_normalizer_agent.txt
│   ├── json_review_agent.txt
│   ├── json_writer_agent.txt
│   ├── scenario_tester_agent.txt
│   ├── simulation_agent.txt
│   ├── simulation_query_agent.txt
│   ├── stop_controller_agent.txt
│   ├── subprocess_generator_agent.txt
│   └── update_analysis_agent.txt
├── process_agents
│   ├── __init__.py
│   ├── __pycache__
│   │   ├── __init__.cpython-314.pyc
│   │   ├── agent_registry.cpython-314.pyc
│   │   ├── agent_wrappers.cpython-314.pyc
│   │   ├── agent.cpython-314.pyc
│   │   ├── analysis_agent.cpython-314.pyc
│   │   ├── app.cpython-314.pyc
│   │   ├── compliance_agent.cpython-314.pyc
│   │   ├── consultant_agent.cpython-314.pyc
│   │   ├── create_process_agent.cpython-314.pyc
│   │   ├── design_agent.cpython-314.pyc
│   │   ├── doc_creation_agent.cpython-314.pyc
│   │   ├── doc_generation_agent.cpython-314.pyc
│   │   ├── edge_inference_agent.cpython-314.pyc
│   │   ├── grounding_agent.cpython-314.pyc
│   │   ├── json_normalizer_agent.cpython-314.pyc
│   │   ├── json_review_agent.cpython-314.pyc
│   │   ├── json_writer_agent.cpython-314.pyc
│   │   ├── scenario_agent.cpython-314.pyc
│   │   ├── simulation_agent.cpython-314.pyc
│   │   ├── step_diagram_agent.cpython-314.pyc
│   │   ├── subprocess_driver_agent.cpython-314.pyc
│   │   ├── subprocess_generator_agent.cpython-314.pyc
│   │   ├── subprocess_writer_agent.cpython-314.pyc
│   │   ├── update_process_agent.cpython-314.pyc
│   │   ├── utils_agent.cpython-314.pyc
│   │   └── utils.cpython-314.pyc
│   ├── agent_registry.py
│   ├── agent_wrappers.py
│   ├── agent.py
│   ├── analysis_agent.py
│   ├── app.py
│   ├── compliance_agent.py
│   ├── consultant_agent.py
│   ├── create_process_agent.py
│   ├── data
│   │   └── openapi.yaml
│   ├── design_agent.py
│   ├── doc_creation_agent.py
│   ├── doc_generation_agent.py
│   ├── edge_inference_agent.py
│   ├── grounding_agent.py
│   ├── helpers
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   ├── doc_content.cpython-314.pyc
│   │   │   ├── doc_governance.cpython-314.pyc
│   │   │   ├── doc_structure.cpython-314.pyc
│   │   │   └── doc_technical.cpython-314.pyc
│   │   ├── doc_content.py
│   │   ├── doc_governance.py
│   │   ├── doc_structure.py
│   │   ├── doc_technical.py
│   │   └── themes
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-314.pyc
│   │       │   └── loader.cpython-314.pyc
│   │       ├── corporate_standard.json
│   │       └── loader.py
│   ├── json_normalizer_agent.py
│   ├── json_review_agent.py
│   ├── json_writer_agent.py
│   ├── public
│   │   ├── script.js
│   │   └── style.css
│   ├── scenario_agent.py
│   ├── simulation_agent.py
│   ├── step_diagram_agent.py
│   ├── subprocess_driver_agent.py
│   ├── subprocess_generator_agent.py
│   ├── subprocess_writer_agent.py
│   ├── templates
│   │   └── index.html
│   ├── update_process_agent.py
│   ├── utils_agent.py
│   └── utils.py
├── properties
│   └── agentapp.properties
├── README.md
└── requirements.txt

```

---

## 🛠 Requirements

- **Google API Key**: An active Gemini API key (set as `GOOGLE_API_KEY` in your environment).
- **Python 3.12+**.
- **Dependencies**: See `requirements.txt`. Note: some packages (e.g., graphviz, python-docx) may require system packages (graphviz binary, LibreOffice for advanced doc conversions, etc.) — document[...]

---

## Setup and Run Locally

Suggested local setup (non-destructive):

```bash
# create a venv (do not delete an existing venv unless you mean to)
rm -fr .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# set your API key (consider using a .env or secrets manager in production)
export GOOGLE_API_KEY="<YourKey>"

# run the pipeline
.venv/bin/adk run process_agents
```

Notes:
- Avoid running `rm -r .venv` unless you are sure you want to remove the virtual environment.
- Consider storing secrets in a secure location or using a .env file and a tool like direnv.

## Test Deployment Emulation using WebUI

To run the web UI locally (emulates the GCP ADK environment):

```bash
.venv/bin/python -m pip install --force-reinstall --no-cache-dir google-adk
.venv/bin/adk web
```

## Using the Agent Locally

To run the agent application via python, you can do...

```bash
python -m process_agents.agent
```

For example...

```bash
python -m process_agents.agent
- Starting Process Architect Orchestrator in local chat mode...

Process Architect Orchestrator (local mode)
Type 'exit' to quit.

[user]: create an End-to-End AI Governance process that includes (RAI + Risk Management + Operating Models + Change Management)      
- Starting process pipeline at 2026-02-10 13:05:12. This will take some time...
- Finished process pipeline at 2026-02-10 13:17:19...

[ArchitectBot]: Successfully generated a professional ISO-formatted Word document: output/End-to-End_AI_Governance_Process.docx
[user]: exit
Exiting Process Architect Orchestrator.
```

Then run your commands as appropriately.
---

## Docker Usage

Build:

```bash
docker build . -t adkprocesseng
```

Interactive run (persist output to local output/ directory):

```bash
docker run -it --rm \
  -v "$(pwd)/output:/app/output" \
  -e GOOGLE_API_KEY="${GOOGLE_API_KEY}" \
  adkprocesseng:latest
```

Notes:
- The ADK CLI is installed during container startup and used via `adk run`.
- Ensure your host `output` folder is writable by the container user.

---

## Sample Prompts

The following are sample prompts you can use to...
- Creating new processes
- Update existing processes
- Investigate existing processes
- Reviewing "what-if" scenarios on existing processes
- Running simualtions on process flows to detect issues, bottlenecks or optimisation issues

### Creating Processes
- "Create an Enterprise Architecture and Business Enterprise Architecture SDLC process to track EA decisions, outcomes, and progress, with escalation flows."
- "Design a detailed business process for handling inventory stock-outs in a retail environment."
- "Create an SDLC and release process for a WebDev application with microservices using an Agile Scrum base."
- "As an enterprise architect, I want you to create a detailed enterprise level TOGAF process document that will allow me to manage the enterprise architecture for any different integrated products that created by different teams, working on different cadences and I need to makesure that all the teams are coordinated with there dependencies and features are supporting each other and have to be approved from an architectural level before being implemented"
- "Please create me a data governance and management process strategy for managing corporate data that will be used in AI strategies"
- "Please compose an HR process that utilizes generative artificial intelligence (GenAI) to augment tasks such as curriculum vitae (CV) review, job specification creation, employee reviews, employee grievance processes and ALL other standard HR process. Implement robust safeguards to ensure that human intervention is utilized when necessary, and prevent GenAI from adversely affecting processes or reputation by being excessively employed in areas where human expertise is required. Additionally, ensure that all training data or AI-generated results adhere to privacy and ethical usage regulations."
- "Please create me an SDLC process for developing products at the Enterprise/Program-level using the latest Agile SAFe framework. I want the process to include - Program level management, release train management, ERM program release planning, big room planning, deployment management of releases, processes for handling dependencies be groups, configuration management procedures, processes for interacting with the System Team and anything else I might have missed that is relevant to SAFe."
- "Act as COO/Architect. Design a SaaS L0 Value Chain with 6 phases: 1. Strategic Management, 2. Product Strategy, 3. Go-To-Market, 4. SDLC, 5. Customer Success, 6. Corporate Functions (HR/Finance/Security). For each phase, provide: Professional description paragraph, Primary Stakeholders, Inputs/Outputs (artifacts), and 3-5 Sub-processes. Flow: Strategy -> Product -> Engineering -> Sales. Ensure active voice and format for mapping to JSON keys: process_name, stakeholders, process_steps, and process_owner."
- "Act as a Pharma COO and Architect to design an end-to-end Level 0 Value Chain for a drug development company, covering the lifecycle from Discovery and Pre-Clinical testing through Clinical Development, Regulatory approval, Manufacturing, and Commercial market access."
- "You are a god. you want to create a world in 1 month and you need to put together a detailed process on how you are going to create that world, with its natural processes, ecosystems and balanced life forms. Ensure the process descriptions are detailed and cover the main activities that you need to do in other to create a via and self-sustaining world. The ultimate goal you have is at the end of the month you have a world which will work without you monitoring it and which will ultimately give rise to intelligent life."
- "I am an enterprise director working to promote the sales of AI and agentic systems into our consulting clients. I need to introduce a standard for responding to RFPs that promote the use responsible use of GenAI and Agentic systems in clients that express the need for them. I need a process that can support this for clients that have projects where AI is of use. Although I do not want to push AI into situations where it would not be a good fit."
- "Create a process flow for Frodo Baggins to save Middleearth from the One Ring and Sauron"
- “Act as a Pharma COO and Enterprise Architect. Produce a Level 0 Value Stream Map for the end‑to‑end drug development lifecycle. Your output must be a single, linear Level 0 value stream covering the flow of value from:
Discovery → Pre‑Clinical → Clinical Development → Regulatory Submission & Approval → Manufacturing → Commercial Launch & Market Access. Present the value stream as 6–10 top‑level value stages. Do not include Level 1 or Level 2 detail. Focus on the flow of value, not organisational functions or capabilities.”
- “Generate a clear, human‑centred process that uses modern AI capabilities to improve efficiency, decision‑making, and accessibility for the widest range of people. The process should emphasize responsible use of AI, scalability, and meaningful real‑world benefit across diverse users.”
- "I am an enterprise architect working for the Ministry of Justice (UK) and I need to introduce an AI standard framework for data governance and quality that all projects need to adhere to. Create a process that projects need to follow to manage AI and data quality and governance - including security and data classification."

### Reviewing or Querying Existing Processes
- "Tell me what happens when a security audit is triggered?"
- "What roles are needed for a sprint planning session?"
- "Who is responsible for the escalation process being closed?"
- "Describe the overall process flow"
- "Using the Consulting Agent, review the process and let me know of any issues areas relative to SAFe 4.0 standards."

### Running What-If Scenarios on Existing Processes
- "What would happen if a security audit failed?"
- "What would be the impact on a delivery if releases did not happen on time?"
- "I need to look at the security reviews on the process - where do they need to be added?"

### Applying Updates to Existing Processes & Regenerating the Documentation
- "Update the process to add security reviews at key stages"
- "Add a code review process to the development steps"
- "Modify the process to add test quality review steps prior to releases being done"

### Running Simulations
- "Dry-run the process and identify any issues"

### Adhoc Commands
- "Regenerate the sub-processes"
- "Recreate the process document"

---

## Running the document generator manually

To run the document generator manually, you must: -
1. Ensure `process_data.json` is present in the `output/` directory.
2. Run the following code snippet:

```python
python -m process_agents.edge_inference_agent output/process_data.json 
python -m process_agents.doc_generation_agent output/process_data.json
```

This will regenerate the documents without deleting any process files.

---

## Tuning Instructions

To modify the instructions used for the LLMs, see the `instructions` directory and
edit the relevant `.txt` file as appropriate.

---

## Theming Support

The document generator includes optional support for applying branded themes to the final Word output. Themes allow users to customise fonts, colours, heading sizes, and footer text without modifying the core rendering logic.

### Overview

The theming system is optional. If a theme is specified in the project property file, the generator loads and applies it. If no theme is specified, the generator uses the default global styling. This ensures predictable output by default while allowing users to introduce their own branding if required.

### Enabling a Theme

In the project property file `properties/agentapp.properties` add...

```bash
    theme=corporate_standard
```

If the "theme" property is omitted or empty, theming is skipped.

### Theme File Format

Themes are defined as JSON files stored in the "themes/" directory. Each theme must follow this structure:

```json
    {
      "name": "Human-readable theme name",
      "fonts": {
        "heading": "Font family for headings",
        "body": "Font family for normal text"
      },
      "colors": {
        "primary": "HEX colour for H1–H2 or null",
        "secondary": "HEX colour for H3 or null",
        "accent": "Optional accent colour or null"
      },
      "heading_sizes": {
        "h1": 22,
        "h2": 18,
        "h3": 16,
        "h4": 14,
        "h5": 12
      },
      "body_size": 11,
      "footer_text": "Optional footer text or null"
    }
```

A theme may also include a "__doc__" block for inline documentation. This is ignored by the loader.


### What a Theme Can Change

Themes can modify:
- heading fonts and sizes
- body font and size
- heading colours (if provided)
- footer text for the first section

### What a Theme Cannot Change

To preserve layout stability, themes do not modify:
- margins
- line spacing
- paragraph spacing
- page layout
- section behaviour
- table formatting beyond font and size

### Fallback Behaviour

If a theme is referenced but cannot be loaded (missing file, invalid JSON, etc.):
- the generator logs the issue
- theming is skipped
- the document is produced using default styling

This ensures the generator always produces a valid output.

---

## Process Viewer

I added a *simple* process viewer for the process JSON. You can invoke it using...

```bash
python -m process_agents.app
open localhost:8080
```

This will launch a simple web server that will let you view the JSON process flow in a browser.

![Example 1](./images/image001.png)


![Example 2](./images/image002.png)


![Example 3](./images/image003.png)


![Example 4](./images/image004.png)

![Example 5](./images/image005.png)

![Example 6](./images/image006.png)

---

### ISO Compliance Mapping

The following table outlines the alignment of the process JSON generated with international ISO standards.

| ISO Standard | Description | Compliance Level | JSON Evidence / Logic |
| :--- | :--- | :--- | :--- |
| **ISO 9001:2015** | Quality Management Systems (QMS) | **High** | Integrated PDCA cycle via `metrics`, `continuous_improvement`, and `risks_and_controls`. |
| **ISO 15378:2017** | QMS for Medicinal Products & GxP | **High** | Explicit inclusion of `governance_requirements` (GMP, GLP, GCP) and rigorous `change_management`. |
| **ISO 31000:2018** | Risk Management Guidelines | **Medium-High** | Detailed `risks_and_controls` and `critical_failure_factors` mapping to risk identification. |
| **ISO 13485:2016** | Medical Devices Quality Management | **Medium** | Alignment of `design_control` phases and `system_requirements` (LIMS/CTMS). |
| **ISO 14001:2015** | Environmental Management | **Low** | Core structure exists, but requires specific environmental impact and waste metrics. |
| **ISO/IEC 27001** | Information Security Management | **Low** | Requires further detail on digital access controls and data encryption protocols. |

### Primary Compliance Pillars

1. **Quality (ISO 9001):** The process architecture enforces a "Risk-Based Thinking" approach. By defining `process_owners` and `success_criteria` for every stage, the design ensures accountability and measurable performance.
2. **Regulatory (ISO 15378):** As a pharmaceutical-specific standard, compliance is demonstrated through the mandatory **Change Control** procedures and the enforcement of GxP standards across the Discovery-to-Commercialization lifecycle.
3. **Risk (ISO 31000):** The design moves beyond simple identification by pairing every identified `risk` with a specific `control` mechanism, creating a resilient operational framework.

---

## Contributing

Thank you for your interest in improving this sample! To make contributing simple and consistent, please follow these guidelines.

Please see [CONTRIBUTORS.md](CONTRIBUTORS.md) for more info as the following is just a summary.

- Setup
  - Fork the repository and work on a feature branch named with a clear prefix, e.g. `feat/`, `fix/`, `docs/`, `chore/` (example: `feat/process-diagram-layout`).
- Code style
  - Follow PEP 8 and general Python best practices.
  - If you use automatic formatting, prefer tools like `black` and `isort`.
  - Run linters (e.g., `flake8`) if present in your workflow.
- Tests
  - Add or update tests for your changes where appropriate. Run tests with `pytest` (or the test runner used in this repo).
  - Verify that any automated checks (CI) pass before requesting review.
- Documentation
  - Update relevant README files, examples, and instruction text for changes that affect usage or setup.
  - If you change behavior or add new sample outputs, include updated example files under `examples/` where appropriate.
- Commit messages
  - Use clear, descriptive commit messages. Consider using the Conventional Commits format: `type(scope): short description` (e.g., `fix(doc): clarify setup instructions`).
- Pull requests
  - Open a pull request against the `main` branch.
  - In the PR description include: a summary of the change, why it’s needed, any migration or compatibility notes, and links to related issues.
  - Mark the PR as draft if it’s a work-in-progress.
  - Request a review from the maintainers and respond to requested changes.
- Small edits
  - For small typos or docs-only fixes you may use the GitHub web UI to edit a file and propose a PR directly from the browser.
- Licensing and contribution terms
  - By submitting a PR you agree that your contribution will be licensed under this repository’s license (see the LICENSE file).
  - If a Contributor License Agreement (CLA) or other process is required later, maintainers will add instructions.
- CI and checks
  - Ensure all CI checks pass; maintainers may require changes or additional tests if checks fail.
- Need help?
  - Open an issue describing the change you want to make or tag maintainers in the PR for guidance. For larger changes, early discussion via an issue saves time.

We appreciate contributions of any size — thanks for helping improve this sample.

---

## Known issues and caveats

- If you use a free tier Gemini key you may encounter resource limits when generating large artifacts or portfolios.
- This sample is for demo purposes only; NO WARRANTY OR GUARANTEE OF FUNCTIONALITY IS PROVIDED. See [LICENSE](https://github.com/tpayne/agentic-ai-adk/blob/main/LICENSE).
- Always validate the generated process for compliance before production use. You can modify the JSON directly and re-run the local pipeline.
- The exit/loop logic may need tuning — sometimes loops do not exit properly which can consume tokens.
- If the LLM fails to call a tool, rephrase the prompt or rerun the process. Document generation (diagramming and Word export) can be run manually if needed.
- The diagrams generated can sometimes be clipped or overlapped. To fix this you might need to modify the process or step process JSON to reduce the size of the labels or instruct the LLMs to make the step names more concise.

---
