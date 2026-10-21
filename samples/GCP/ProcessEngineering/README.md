# ADK Business Process Architect

Give it a rough, plain-language brief and this multi-agent suite (built on the Google Agent
Development Kit) will design, test, and document a full end-to-end business process — or a full
architectural design document (HLD/LLD/Combined) — producing a professional, ISO-aligned Word
document plus diagrams. A handy tool for consultants and architects alike.

It's based on Google ADK but uses `LiteLlm` under the hood, so you can point it at Gemini, Claude,
or other model providers — see [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md) for how.

## What it does

- Turns a plain-language brief into a fully designed, reviewed, and documented **business process**.
- Does the same for **architecture design documents** (High-Level, Low-Level, or Combined design).
- Generates and refines **cloud architecture diagrams** (AWS/Azure/GCP) from a design document, including natural-language edits ("add a WAF in front of the load balancer").
- Answers questions, runs **"what-if" scenarios**, and **simulates** resilience/scalability/security/latency against an existing process, design, or diagram.
- Runs an **adversarial attack-path simulation** against a cloud architecture diagram, and estimates its **monthly cost** with optimization suggestions.
- **Imports** an already-existing process/design document from a folder of files, or **summarizes requirements** from a pile of documents before you've decided what to build.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GOOGLE_API_KEY="<YourKey>"   # or ANTHROPIC_API_KEY, etc. -- see TECHNICAL_NOTES.md

python -m process_agents.agent
```

```
python -m process_agents.agent
[user]: create a simple 3-step vendor onboarding process
- Starting process pipeline. This will take some time...
[ArchitectBot]: Successfully generated a professional ISO-formatted Word document: output/Vendor_Onboarding.docx
[user]: exit
```

It can also run **detached as a REST API** (`-d` flag) or in **Docker** — see
[TECHNICAL_NOTES.md § Running as a Web Service](TECHNICAL_NOTES.md#running-as-a-web-service-rest-api)
and [§ Docker Usage](TECHNICAL_NOTES.md#docker-usage). A ready-made browser chat UI that talks to
either this or the neuro-san port is at
[`samples/WebClient/ProcessEngineering`](../../WebClient/ProcessEngineering/README.md).

## Example prompts

- "Create an SDLC and release process for a WebDev application with microservices using an Agile Scrum base."
- "What roles are needed for a sprint planning session?"
- "What would happen if a security audit failed?"
- "Create a High-Level Design document for a payments microservices platform on AWS, including security architecture and scalability targets."
- "Generate a cloud architecture diagram for the current design document."
- "Run a simulation on the design to check for resilience, scalability, security, and latency issues."
- "Read the files in ./vendor-docs and create a process for onboarding new vendors."

Many more, covering every capability above, are in
[TECHNICAL_NOTES.md § Sample Prompts](TECHNICAL_NOTES.md#sample-prompts).

## Status

**BETA.** Tested and generally stable, but LLM output can be unpredictable — always verify a
generated process/design before relying on it. This sample is for demo purposes; NO WARRANTY OR
GUARANTEE OF FUNCTIONALITY IS PROVIDED — see [LICENSE](https://github.com/tpayne/agentic-ai-adk/blob/main/LICENSE).

For the full feature list, repository layout, configuration options, complete REST API reference,
compliance mappings, agent inventory, and known issues, see **[TECHNICAL_NOTES.md](TECHNICAL_NOTES.md)**.
