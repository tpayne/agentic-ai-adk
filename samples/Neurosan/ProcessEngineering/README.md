# Business Process Architect (neuro-san)

A multi-agent suite, built on [Cognizant's neuro-san](https://github.com/cognizant-ai-lab/neuro-san)
framework, that automates the lifecycle of business process engineering from initial requirements
through to generating professional process documentation and validated workflows. It also supports
an equivalent lifecycle for architectural design documentation (High-Level Design, Low-Level
Design, or Combined), covering the same create/query/what-if/simulate/update pattern.

Give it a raw prompt and it will design, test, and document a full end-to-end process — or a full
architectural design document — based on that request: automated process engineering and automated
solution/architecture documentation, going from rough requirements through to tested, ISO-formatted
documentation. A handy tool for consultants and architects alike.

This project is built on neuro-san's declarative HOCON agent networks and Python `CodedTool`s, so
any LLM provider neuro-san supports can be used (Gemini, Anthropic, OpenAI, Bedrock, Azure OpenAI,
...) — set the model in `config/llm_config.hocon`. The pipeline summarization middleware has its
own OpenAI model setting in that file (LangChain constructs it separately from neuro-san's
`llm_config`); when changing providers, update that middleware model and provide its matching API
key as well. The shared config sets OpenAI
`use_responses_api` to `true`, allowing reasoning models such as `gpt-6-luna` to retain reasoning
while making the function/tool calls these networks require. For Azure OpenAI deployments where
Responses API is unavailable, set it to `false` in the shared config.

---

## Status

**Complete.** All seventeen agent networks below are wired and verified end-to-end (structurally and
functionally — see [Verification](#verification)):

| Network | Front-man agent | What it does |
|---|---|---|
| `requirements_summary` | `Requirements_Summary_Agent` | Reads a directory of source files, extracts a structured, traceable requirements register, saves it for later reuse. |
| `requirements_consultant` | `Requirements_Consultant_Agent` | Answers questions about a previously-saved requirements summary. |
| `cloudarch` | `CloudArch_Pipeline` | Generates/refines a cloud architecture diagram (drawio/mxGraph XML) via a deterministic layout engine, audited by a reviewer agent in a generate→review→revise loop. |
| `cloudarch_consultant` | `CloudArch_Consultant_Agent` | Answers questions about an existing cloud architecture diagram. |
| `cloudarch_simulation_query` | `CloudArch_Simulation_Query_Agent` | Runs a resilience/scalability/latency simulation over an existing diagram and explains findings in business language. |
| `cloudarch_finops` | `CloudArch_FinOps_Agent` | Estimates diagram costs and optimization opportunities; uses live provider price catalogs for resources with explicit SKUs and monthly usage details when accessible, and keeps the existing heuristic estimate otherwise. |
| `process` | `Process_Pipeline` | Generates/refines a business process design via analysis → design → compliance review → simulation review (looping until approved or a revision limit is hit), expands every top-level step into its own detailed subprocess, renders a flow diagram, and produces a final ISO-formatted Word document. |
| `process_update` | `Process_Update_Pipeline` | The same generate/review loop, applied as a delta against an existing process in response to a change request. |
| `process_consultant` | `Process_Consultant_Agent` | Answers questions about an existing business process. |
| `process_scenario_tester` | `Process_Scenario_Tester` | Tests what-if scenarios against an existing process. |
| `process_simulation_query` | `Process_Simulation_Query_Agent` | Runs a cycle-time simulation over an existing process and explains bottlenecks in business language. |
| `design` | `Design_Doc_Pipeline` | Generates/refines an architectural design document (HLD/LLD/Combined) via analysis → design (HLD+LLD in one pass) → compliance review → architecture-simulation review, then renders a flow diagram and a final ISO-formatted Word document. |
| `design_update` | `Design_Doc_Update_Pipeline` | The same generate/review loop, applied as a delta against an existing design document in response to a change request. |
| `design_consultant` | `Design_Consultant_Agent` | Answers questions about an existing design document, with license to bring in outside best-practice recommendations. |
| `design_scenario_tester` | `Design_Scenario_Tester` | Tests what-if scenarios against an existing design document by tracing its real component dependency graph. |
| `design_simulation_query` | `Design_Architecture_Simulation_Query_Agent` | Runs a composite resilience (blast-radius Monte Carlo)/scalability/security/latency simulation over an existing design document and explains findings in business language. |
| `process_architect` | `Process_Architect_Orchestrator` | Top-level front-man routing a request to whichever network above fits it. |

---

## Known issues

- **Diagram layouts**: generated diagrams may occasionally be clipped or laid out sub-optimally,
  especially with very long step/component names. You can usually improve this by shortening the
  offending name in the JSON and regenerating.
- **Agent "chattiness"**: LLMs may occasionally disregard instructions and surface tool-call/JSON
  commentary in chat. In most cases this can be safely ignored.
- **Per-session artifact isolation is not implemented.** `ns run` serves multiple concurrent chat
  sessions, but this project's own state (`process_data.json`/`design_data.json`,
  `cloudarch_drawio.xml`, `approval.json`, every feedback mailbox) lives in one project-wide
  `output/` directory, not scoped per session — two people driving the same network at once will
  read and overwrite each other's artifacts. Safe for one requester at a time.
- **No built-in auth/rate-limiting on `ns run`.** `ns run`'s own server has neither; put an
  authenticating reverse proxy / rate limiter in front of it before exposing it beyond localhost.
  `cli.py -d --flask` (see Running below) is the alternative that DOES have both built in, if
  that's what you need instead of `ns run`'s own UI.
- If a free-tier LLM key is used, you may hit resource limits generating large artifacts.
- This project is for demo purposes; NO WARRANTY OR GUARANTEE OF FUNCTIONALITY IS PROVIDED.

---

## Notes

- If you are generating a new process from scratch, remove `output/process_data.json` (and related
  artifacts) first — stale state is read as the baseline for a fresh generation otherwise. The same
  applies to `output/design_data.json` for design documents. If you are querying, testing, or
  updating an *existing* process/design, leave `output/` alone — it's the input those operations read.
- If the top-level front-man (`process_architect`) picks the wrong network for a question (e.g. it
  treats a design-document question as a process question), naming the network explicitly steers it
  correctly — either talk to that network directly (`ns chat design_consultant`, `--agent
  design_consultant` with `cli.py`), or say "using the Design Consultant..." when talking to the
  front-man.

---

## Features

- **Autonomous multi-agent pipeline**: a "Process Architect" workflow that transforms raw
  requirements into final artifacts without manual intervention — an analysis agent converts
  natural-language intent into a machine-readable requirements specification.
- **Self-auditing compliance gate**: a compliance agent acts as an automated release manager,
  triggering revisions if regulatory or security gaps are found and preventing progression until
  resolved.
- **Self-auditing simulation gate**: a simulation agent runs Monte Carlo-style simulations to
  identify bottlenecks and suggests optimizations or reports unresolved issues.
- **Automated high-fidelity artifacts**: process diagrams (level 1 and 2) embedded in the process
  document, and a professional Word document describing the business process, aligned to
  ITIL/ISO-style conventions. The document-generation step renders and embeds the current level-1
  flow diagram itself; persisted subprocesses are rendered as level-2 diagrams and embedded too.
- **Autonomous design document pipeline**: a parallel "Solution Architect" workflow
  (`design`/`design_update`) that transforms raw architecture requirements into a High-Level Design
  (HLD), Low-Level Design (LLD), or Combined design document, following the same
  requirements → design → review → document flow as the process pipeline.
- **Self-auditing design review loop**: a design-side review/compliance loop iterates over the
  HLD/LLD/Combined content, checking it against the design schema and standards references (TOGAF
  ADM, C4 Model, ISO/IEC/IEEE 42010) until it is structurally and content-complete.
- **Self-auditing design simulation gate**: a design-side simulation agent runs the same
  four-dimension simulation described below as an internal gate inside the design pipeline,
  triggering revisions if resilience, scalability, security, or latency issues are found.
- **Cloud architecture diagramming** (`cloudarch`): a dedicated reviewer/generator loop produces
  and iteratively refines a cloud/UML-style architecture diagram from a design document's
  components, dependencies, and integration points, and applies natural-language refinements to an
  existing diagram (e.g. "add a WAF in front of the load balancer") — the generator loads the
  current diagram before modifying it, rather than only ever starting from scratch. Every
  generation/refinement is expressed as plain zones/components/edges content with no coordinates; a
  deterministic layout engine computes every box's size/position and every edge's route, so icons
  never overlap their own label and edges route as clean axis-aligned lines — the same engine
  enforces the diagram's visual conventions (icon-forward borderless components, left-to-right
  pipeline flow grouped into zones of 2-4 related services, AWS/Azure/GCP service-category color
  coding) so every diagram reads like a professional cloud-provider reference diagram.
- **Cloud architecture consultant & simulation**: a consultant agent answers questions about an
  existing cloud architecture diagram (purpose, components, connections) grounded strictly in the
  diagram's own XML, while a simulation-query agent runs a structural resilience (blast-radius Monte
  Carlo), scalability (fan-in bottleneck), and latency (dependency chain depth) simulation directly
  against the diagram — not the source design document, since the diagram is often more granular
  (WAF/KMS/IAM/CDN-level detail an abstract component list wouldn't enumerate).
- **Cloud architecture FinOps** (`cloudarch_finops`): estimates per-component and total monthly
  costs, then flags sizing, autoscaling, commitment, storage-tiering, and orphaned-resource
  opportunities. It can ground costs for any supported resource when the diagram specifies an
  exact `sku:` and monthly `usage:` for each billable meter (and `region:` where relevant). It
  queries the [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) (public),
  [AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html) (AWS credentials with
  `pricing:GetProducts` required), or [Google Cloud Billing Catalog API](https://docs.cloud.google.com/billing/docs/how-to/get-pricing-information-api) (requires
  `GOOGLE_CLOUD_BILLING_API_KEY` or `GOOGLE_API_KEY`, and the Cloud Billing API enabled). For
  example, a storage component can specify `sku: Standard_LRS` and `usage: 500 GB/month`; a gateway
  can list separate monthly usage lines for hours and requests. The agent only applies catalog
  pricing when each stated usage meter has a unique matching USD rate, and does not infer traffic,
  storage, retention, or request volumes. Catalog rates are public prices and exclude
  account-specific discounts. The estimate reports which component prices are API-grounded versus
  heuristic, making clear which amounts come from provider catalog rates rather than general LLM
  reasoning. Legacy compute pricing without explicit usage assumes one VM running
  730 hours per month. Components without sufficiently detailed, accessible matching catalog data
  retain the existing rough estimate. These estimates are not quotes and should be confirmed with
  the provider's pricing calculator or actual billing data.
- **Real LLD sequence diagrams**: a Low-Level Design component's `sequence_flows` entries carry
  their own inline participants and ordered steps, rendered as an actual UML-style sequence diagram
  (lifelines, sync/async calls, returns) and embedded in the generated document.
- **Four-dimension design simulation**: a composite simulation over an existing design document,
  covering:
  - **Resilience** — a Monte Carlo blast-radius/cascading-failure model built from component
    dependencies, integration points, declared availability targets, and the risk register,
    identifying single points of failure and an overall resilience risk rating.
  - **Scalability** — structural bottleneck detection (components many others depend on with no
    declared elastic/auto-scaling technology), plus any scalability-tagged risks.
  - **Security** — a control-coverage checklist, compliance-standard status tally, security-tagged
    risks, and an externally-exposed-without-full-controls check.
  - **Latency** — declared performance/latency targets cross-checked against the deepest
    dependency chain, flagging undeclared latency budgets on long request paths.
- **Design consultant & scenario testing**: a consultant agent answers general questions about an
  existing design document (ownership, component responsibilities, requirements clarification),
  while a scenario-tester reasons through "what-if" scenarios (e.g. "what if the payments region
  goes down?") by tracing impact through the dependency/integration-point graph.
- **File-based requirements extraction (opt-in)**: any process or design-document
  creation/refinement request can source its requirements from a directory of files instead of (or
  alongside) direct chat text — just ask, e.g. *"read the files in ./vendor-docs and create a
  process for onboarding new vendors."* Text is extracted and combined from every
  `.txt`/`.md`/`.docx`/`.pdf`/`.eml`/`.msg`/`.xls`/`.xlsx` file directly inside the given directory
  using pure-Python extractors (no system binaries required). Strictly opt-in — absent that
  explicit phrasing, no agent reads a directory on its own.
- **Standalone requirements summarization & consultation**: `requirements_summary` can read a
  directory of files on its own — without running a full creation pipeline — synthesize a
  structured requirements summary, report it in plain language, and save it to
  `output/requirements_summary.json` for later reuse. `requirements_consultant` then lets you ask
  follow-up questions about that saved summary at any time, and any later process/design/diagram
  creation request can reuse it instead of re-reading the original documents by saying so
  explicitly (e.g. *"create a process using the saved requirements summary"*).
- **Requirements-quality analysis**: both the standalone summarizer and the pipeline's own analysis
  agents flag requirements that conflict with each other, requirements too vague to act on,
  relative priority (critical/high/medium/low), important requirements *not* stated in the source
  material but reasonably inferable (always clearly labeled as inferred, and never used by a
  generation pipeline unless the request explicitly asks to include them), and entire standard
  categories (security, disaster recovery, data privacy, etc.) the source material never addresses.
- **Requirement traceability register**: every atomic requirement gets a stable id
  (`FR-001`/`NFR-001`/`GOAL-001`/`CON-001`, or `INF-001` for an inferred one), a record of which
  source file it came from, and one or more concrete acceptance criteria — mapped directly into the
  design schema's functional/non-functional requirements and traceability matrix for
  ISO/IEC/IEEE 29148-style traceability.
- **Requirements-aware consultation & simulation**: every consultant, scenario-tester, and
  simulation-query agent also checks once per conversation for a saved requirements summary
  alongside the process/design/diagram it's actually answering about. If a summary exists and the
  question is specifically about requirement fulfillment or coverage (e.g. *"does this diagram
  satisfy the encryption-at-rest requirement?"*), the agent cross-checks the stated requirement
  against the actual data and says plainly whether it's met, partially met, at risk, or not
  addressed. For any other question it stays silent on the subject.

---

### Autonomous Execution Flow

1. **Requirement extraction**: `Analysis_Agent` converts user intent into a machine-readable
   requirements specification.
2. **Iterative refinement**: `Design_Agent` and `Compliance_Agent`/`Simulation_Agent` loop,
   refining the process until operational and regulatory criteria are satisfied.
3. **Schema stabilization**: the finalized design is validated and saved to `output/process_data.json`.
4. **Artifact engineering**: diagrams are rendered and the final specification (Word document) is
   generated from that state.

### Autonomous Design Document Execution Flow

1. **Requirement extraction**: `Design_Doc_Analysis_Agent` converts user intent (target
   architecture, constraints, quality attributes) into a machine-readable requirements
   specification, and determines whether an HLD, LLD, or Combined document is being requested.
2. **Iterative refinement**: `Design_Doc_Agent` and review agents loop over the HLD/LLD/Combined
   content — components, dependencies, integration points, risk register, security architecture,
   scalability/performance targets — until the document is structurally complete.
3. **Schema stabilization**: the finalized design is validated and saved to `output/design_data.json`.
4. **Artifact engineering**: the final design specification (Word document) and flow diagram are
   rendered from that state.

Once a design document exists on disk, it can be queried (`design_consultant`), tested against
what-if scenarios (`design_scenario_tester`), simulated across resilience/scalability/security/
latency (`design_simulation_query`), or updated and re-documented (`design_update`) — mirroring the
equivalent process-side capabilities above. Cloud architecture diagramming (`cloudarch`) is a
separate, standalone network with the same query/simulate/update parity: queried
(`cloudarch_consultant`), simulated (`cloudarch_simulation_query`), cost-estimated
(`cloudarch_finops`), or modified via natural language (`cloudarch` itself) — generate one from a
design document's components whenever you want one, rather than it happening automatically as part
of the design pipeline.

---

## Setup

```bash
uv sync
```

Set an LLM provider API key (see `config/llm_config.hocon` for the configured model;
`GOOGLE_API_KEY`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/etc. — see neuro-san's own
[`docs/api_key.md`](https://github.com/cognizant-ai-lab/neuro-san/blob/main/docs/api_key.md)):

```bash
uv run ns check-llm-keys
```

## Running

```bash
uv run ns run
```

Starts the neuro-san server (`:8080`) and the nsflow chat UI (`:4173`); choose any of the
networks listed in [Status](#status) in the UI. To chat with a network directly from the CLI,
use its name from that table. Set `PYTHONPATH` in the shell before starting `ns chat` (Python
reads it at interpreter startup):

```bash
export PYTHONPATH="$(pwd)"
uv run ns chat requirements_summary
uv run ns chat design_consultant
uv run ns chat process_architect   # top-level front-man, routes across all other networks
```

For example, replace `requirements_summary` above with `cloudarch`, `process`,
`design_simulation_query`, or any other network name in the Status table. The `ns run` UI does
not need `PYTHONPATH`.

Run the test suite with:

```bash
uv run pytest
```

`uv run ns validate registries/<name>.hocon` structurally validates a network file without needing
an API key — useful while editing.

### CLI (`cli.py`)

A standalone CLI, talking to `process_architect` (the top-level front-man) by default:

```bash
uv run python cli.py                        # interactive chat REPL (default)
uv run python cli.py -i "design a vendor onboarding process"   # one prompt, print, exit
uv run python cli.py -f instructions.txt    # submit each line of a file as a turn, in order
uv run python cli.py -d                     # detached: launch ns run's own server + UI instead
uv run python cli.py -d --flask             # detached: run this project's own Flask REST API instead
uv run python cli.py --agent cloudarch      # talk to a different network directly
```

`-d --flask` runs a Flask REST API with the *exact same* contract as the ADK original's own `-d`
mode (`POST /chat`, `POST /chat/stream`, `POST /chat/<session_id>/stop`,
`DELETE /chat/<session_id>`, `GET /artifacts/<name>`,
`GET /status`; the same `Authorization: Bearer <key>` / `X-API-Key` auth, rate limiting, and
loopback-only-unless-authenticated startup refusal) — see
[`samples/WebClient/ProcessEngineering`](../../WebClient/ProcessEngineering/README.md) for a
browser client that talks to either backend interchangeably. `POST /chat/stream` streams
`text/event-stream` progress/delta/done events as the agent network actually works, instead of one
blocking JSON body sent only once the whole turn is done — see the ADK original's own README for
the full event shape (identical here); built on neuro-san's own `streaming_chat()` generator, which
`ChatSession.send_streaming` consumes incrementally instead of draining it fully like `send()`
does. `GET /artifacts/<name>` (`name` is `process` or `design`) returns this project's own current
`output/process_data.json` / `output/design_data.json`, parsed (404 if that pipeline hasn't
produced one yet) -- a raw file read, not the `load_master_process_json`/`load_master_design_json`
`CodedTool` helpers under `coded_tools/common/`, which silently fall back to a blank template when
the file is missing; see the ADK original's own README for the full response shape (identical
here). This is what the web client's **Process / Design** tab consumes.

Both `/chat` and `/chat/stream`'s `"done"` event also carry a `usage` field --
`{"prompt_tokens": N, "completion_tokens": N, "total_tokens": N, "model": "..."}`, or `null` for a
turn that made no LLM calls -- same shape the ADK original reports, so the web client's **Token
Usage** tab doesn't need to know which backend it's talking to. Unlike the ADK original's single
static `MODEL` property, this project's own `token_accounting` (neuro-san's own built-in, already-
aggregated per-request token/cost accounting -- see `_extract_usage` in `cli.py`, and
`LangChainTokenCounter`/`TokenAccountingMessageProcessor` in the installed `neuro_san` package for
where it actually comes from) reports the REAL model(s) genuinely invoked that turn, so `model` here
can differ turn to turn if different pipelines/agents in this network are configured against
different models. `GET /status` does NOT report a model name the way the ADK original's does, for
the same reason -- there is no single static answer to give.

`POST /chat/<session_id>/stop` cancels that session's currently in-flight turn --
`{"status": "ok", "session_id": "...", "stopped": true|false}` (`false` if nothing was actually
running). A **real** cancellation, not merely the client giving up on the connection: it reaches
directly into the underlying `DirectAgentSession`'s own `AsyncioExecutor`
(`session.session.invocation_context.get_asyncio_executor().cancel_current_tasks()`) and cancels
whatever's genuinely in flight there -- neuro-san's own `streaming_chat()` explicitly documents this
as the intended way to interrupt it (see its own "interrupted by caller-side 'close' method" comment
in the installed `neuro_san` package). The cancelled turn's own `/chat/stream` response receives one
final `{"status": "stopped", "response": "<partial answer so far>"}` event over the **same,
still-open** connection before it closes. See `chat_stop`/`ChatSession.send_streaming` in `cli.py`.
The web client's Stop button (shown in place of Send while a turn is streaming) is what actually
calls this in practice.

```bash
uv run python cli.py -d --flask --http -p 8081   # plain HTTP on :8081, no self-signed cert warning
WEBAPIKEY=change-me uv run python cli.py -d --flask   # require an API key before exposing beyond localhost
```

Configured entirely via environment variables (this project has no properties-file config layer —
put these in this project's own `.env` file, same as `LOGLEVEL` below, so they persist across
runs): `WEBAPIKEY`, `WEBRATELIMITPERMINUTE` (default 30/min), `HOST` (default `127.0.0.1`),
`SSLCERTFILE`/`SSLKEYFILE`, `ALLOWINSECUREWEBSERVICE`, `FLASK_SECRET_KEY`. Plain `-d`
(no `--flask`) is unchanged and still the default — `--flask` is an alternative, not a replacement,
for when you specifically want REST-API parity with the ADK original rather than `ns run`'s own
server/UI.

Control lines work inside interactive/`-f` mode: `exit`/`quit`/`stop`, `clear` (reset the session),
a leading `#` (comment, echoed but not sent), `sleep <seconds>`/`wait <seconds>`, a leading `$ ...`
(run a raw shell command instead of sending the line to the agent), and a trailing `\` to continue
one logical line across multiple physical lines.

Every run writes neuro-san's own "thinking" trace to `output/logs/agent_thinking.txt` (one combined
stream) and `output/logs/agent_thinking/` (one file per agent origin in a multi-agent turn):

```bash
tail -f output/logs/agent_thinking.txt
```

`cli.py`'s own diagnostic logging is standard Python `logging`, controlled by a `LOGLEVEL` env var
(DEBUG/INFO/WARNING/ERROR/CRITICAL, default `WARNING`), written to `output/logs/cli.log`. **Off by
default** — nothing appears unless you ask for it:

```bash
LOGLEVEL=DEBUG uv run python cli.py
tail -f output/logs/cli.log
```

A WARNING+ copy of anything logged always prints to the terminal too (on **stderr** specifically,
so it never corrupts output piped from stdout, e.g. `cli.py -i "..." | pbcopy`).

### Docker

Build:

```bash
docker build -t processengineering-neurosan .
```

Run, persisting generated artifacts to a local `output/` directory and passing your LLM key:

```bash
docker run --rm \
  -p 8080:8080 \
  -v "$(pwd)/output:/app/output" \
  -e GOOGLE_API_KEY="${GOOGLE_API_KEY}" \
  processengineering-neurosan
```

Notes:
- Ensure your host `output/` folder is writable by the container's (non-root) user.
- The image's default command runs `ns run --server-only` — the neuro-san HTTP/chat API on
  `:8080`, without the nsflow UI. To get the nsflow UI too, override the command and publish
  `:4173` as well:
  ```bash
  docker run --rm -p 8080:8080 -p 4173:4173 \
    -v "$(pwd)/output:/app/output" \
    -e GOOGLE_API_KEY="${GOOGLE_API_KEY}" \
    processengineering-neurosan \
    uv run ns run
  ```
- Pass whichever provider key you're using via `-e` (`GOOGLE_API_KEY`/`ANTHROPIC_API_KEY`/
  `OPENAI_API_KEY`/etc.) — never bake one into the image.
- The container builds and starts cleanly with no LLM key set too; you'll only hit the "no LLM API
  key configured" wall once you actually chat with it.

---

## Sample Prompts

The following are sample prompts you can use to:
- Create new processes
- Update existing processes
- Investigate existing processes
- Review "what-if" scenarios on existing processes
- Run simulations on process flows to detect issues, bottlenecks, or optimization opportunities

### Creating Processes
- "Create an Enterprise Architecture and Business Enterprise Architecture SDLC process to track EA decisions, outcomes, and progress, with escalation flows."
- "Design a detailed business process for handling inventory stock-outs in a retail environment."
- "Create an SDLC and release process for a WebDev application with microservices using an Agile Scrum base."
- "Please create me a data governance and management process strategy for managing corporate data that will be used in AI strategies."
- "Please create me an SDLC process for developing products at the Enterprise/Program-level using the latest Agile SAFe framework, including program-level management, release train management, big room planning, and dependency handling between groups."
- "Act as a Pharma COO and Architect to design an end-to-end Level 0 Value Chain for a drug development company, covering the lifecycle from Discovery and Pre-Clinical testing through Clinical Development, Regulatory approval, Manufacturing, and Commercial market access."
- "Read the files in ./vendor-docs and create a process for onboarding new vendors." *(file-based requirements extraction — see Features above)*
- "Use the saved requirements summary to create a process for onboarding new vendors." *(reuses a requirements summary saved earlier — see below — instead of re-reading the original documents)*

### Reviewing or Querying Existing Processes
- "Tell me what happens when a security audit is triggered?"
- "What roles are needed for a sprint planning session?"
- "Who is responsible for the escalation process being closed?"
- "Describe the overall process flow."

### Running What-If Scenarios on Existing Processes
- "What would happen if a security audit failed?"
- "What would be the impact on a delivery if releases did not happen on time?"

### Applying Updates to Existing Processes & Regenerating the Documentation
- "Update the process to add security reviews at key stages."
- "Add a code review process to the development steps."

### Running Simulations
- "Dry-run the process and identify any issues."

---

## Sample Prompts — Design Documents

Sample prompts for the design-document (HLD/LLD/Combined architecture) side:

### Creating Design Documents
- "Create a High-Level Design document for a ServiceNow-based Configuration Management and Discovery platform covering AWS and on-premises MID Server clusters, ECC Queue, and Identification & Reconciliation Engine, including component dependencies, integration points, availability targets, and a risk register."
- "Design a Combined HLD/LLD document for a payments microservices platform on AWS, including component-level interfaces, technology stack, security architecture (authN/authZ, data protection, compliance standards), and scalability/performance targets."
- "Create a Low-Level Design document detailing the internal components, sequence flows, and interfaces of the notification service described in our existing HLD."
- "Scan the documents in ./architecture-notes and design a system for our new order management platform." *(file-based requirements extraction)*
- "Design a Combined HLD/LLD using the saved requirements summary, including any inferred requirements." *(reuses a saved requirements summary and opts in to its inferred/derived requirements)*

### Reviewing or Querying Existing Design Documents
- "Which components does the Identification & Reconciliation Engine depend on?"
- "What is the declared availability target for this architecture?"
- "Describe the overall system context and its external systems."

### Running What-If Scenarios on Existing Design Documents
- "What if the AWS MID Server cluster region goes down — what else is affected?"
- "If the PAM/secrets vault integration is compromised, which components and stakeholders are impacted?"

### Running Design Architecture Simulations
- "Run a simulation on the design to check for resilience, scalability, security, and latency issues."
- "Can you check this architecture for single points of failure and scalability bottlenecks?"

### Applying Updates to Existing Design Documents & Regenerating the Documentation
- "Update the design to add a secondary AWS region for the MID Server cluster for resilience."
- "Add an explicit auto-scaling strategy for the Identification & Reconciliation Engine."

### Generating or Regenerating Cloud Architecture Diagrams
- "Generate a cloud architecture diagram for the current design document."
- "Regenerate the architecture diagram to reflect the updated component list."

### Modifying Cloud Architecture Diagrams via Natural Language
- "Add a WAF in front of the load balancer in the architecture diagram."
- "Update the cloud diagram to include a Redis cache between the API and the database."

### Reviewing or Querying Existing Cloud Architecture Diagrams
- "What does this cloud architecture diagram show?"
- "Review the current diagram for best-practice gaps — is there anything missing for security or observability?"

### Running Cloud Architecture Diagram Simulations
- "Simulate a failure in this cloud architecture diagram — what are the single points of failure?"
- "Will the architecture in the diagram scale under load?"

### Estimating Cloud Architecture Costs
- "Estimate the monthly cost of this diagram and identify the best optimization opportunities."
- "Use the `Standard_D2s_v3` VM in `eastus` for the application server and ground its estimate in the Azure price catalog."
- "Estimate an EC2 `m5.xlarge` in `us-east-1` and a GCE `n2-standard-4` in `us-central1`."

---

## Sample Prompts — Standalone Requirements Extraction & Review

These prompts use `requirements_summary` and `requirements_consultant` directly, without running
any process/design/architecture creation pipeline. Useful when you want to extract and review
requirements from a pile of documents before deciding what to build from them.

### Reading & Summarizing Files
- "Read the files in ./vendor-docs and summarize the requirements."
- "Scan ./architecture-notes and extract the requirements into a requirements summary file for later use."

Each run reports a plain-language narrative in chat (goals, requirements, constraints, and any
flagged conflicts/priorities/clarifications/inferred requirements/coverage gaps) and saves a
structured, traceable requirements register to `output/requirements_summary.json`.

### Reviewing a Saved Requirements Summary
- "What's in the saved requirements summary?"
- "Review the requirements summary for conflicts."
- "What's the priority of the requirements we extracted?"
- "What areas aren't covered at all by the source material?"

### Reusing a Saved Requirements Summary in a Creation Request
- "Create a process using the saved requirements summary."
- "Design a system using the saved requirements summary, including any inferred requirements."
  *(the "including any inferred requirements" phrasing is required to opt in — otherwise
  inferred/derived requirements are never used to drive scope, by design.)*

---

## Document Theming

Generated Word documents apply a built-in "Corporate Standard" theme (Segoe UI headings, Calibri
body, blue accent colors, a "Confidential" footer) unconditionally — there is currently no
configuration toggle to select a different theme or fall back to plain styling. See
[NeuroSAN implementation notes](#neurosan-implementation-notes) below.

---

### ISO Compliance Mapping

The following table outlines the alignment of the generated process JSON with international ISO standards.

| ISO Standard | Description | Compliance Level | JSON Evidence / Logic |
| :--- | :--- | :--- | :--- |
| **ISO 9001:2015** | Quality Management Systems (QMS) | **High** | Integrated PDCA cycle via `metrics`, `continuous_improvement`, and `risks_and_controls`. |
| **ISO 15378:2017** | QMS for Medicinal Products & GxP | **High** | Explicit inclusion of `governance_requirements` (GMP, GLP, GCP) and rigorous `change_management`. |
| **ISO 31000:2018** | Risk Management Guidelines | **Medium-High** | Detailed `risks_and_controls` and `critical_failure_factors` mapping to risk identification. |
| **ISO 13485:2016** | Medical Devices Quality Management | **Medium** | Alignment of design-control phases and `system_requirements`. |
| **ISO 14001:2015** | Environmental Management | **Low** | Core structure exists, but requires specific environmental impact and waste metrics. |
| **ISO/IEC 27001** | Information Security Management | **Low** | Requires further detail on digital access controls and data encryption protocols. |

**Primary compliance pillars:**
1. **Quality (ISO 9001):** defining `process_owner` and success criteria for every stage ensures accountability and measurable performance.
2. **Risk (ISO 31000):** every identified risk is paired with a specific control mechanism, creating a resilient operational framework.

### Design Document Standards Alignment

| Standard | Description | Alignment Level | JSON Evidence / Logic |
| :--- | :--- | :--- | :--- |
| **ISO/IEC/IEEE 42010:2022** | Systems and Software Engineering — Architecture Description | **High** | `system_context`, `high_level_design`, and `low_level_design` map directly to architecture viewpoints and views; `quality_attributes[]` records architecturally significant requirements. |
| **ISO/IEC/IEEE 29148:2018** | Systems and Software Engineering — Requirements Engineering | **High** | `requirements.functional_requirements`/`requirements.non_functional_requirements` (stable `FR-*`/`NFR-*` ids, priority, source, acceptance criteria, status) populated directly from the analysis-stage requirements register. |
| **TOGAF ADM** | The Open Group Architecture Framework — Architecture Development Method | **Medium-High** | `system_context.external_systems`, `high_level_design.components`, and `risk_register`/`risks_and_mitigations` align to Business/Data/Application/Technology architecture phases and governance gates. |
| **ISO/IEC 25010:2011** | Systems and Software Quality Requirements and Evaluation (SQuaRE) | **Medium-High** | `quality_attributes[]` (characteristic enum including `performance_efficiency`, `security`, etc., each with a metric/target) map to SQuaRE quality characteristics. |
| **C4 Model** | Context, Containers, Components, Code | **Medium** | `system_context` → Context; `high_level_design.components` → Containers/Components; `low_level_design` → Code-level detail. |
| **arc42** | Pragmatic Architecture Documentation Template | **Medium** | `availability_and_resilience`, `scalability_and_performance`, and `security_architecture` map to arc42's cross-cutting concepts and quality-scenario sections. |

**Design-side simulation & analysis coverage** — the design simulation agent provides quantitative
evidence against several of the standards above with no additional schema fields needed:
1. **Resilience/Availability:** a Monte Carlo blast-radius simulation over component dependencies, integration points, availability targets, and the risk register produces single-point-of-failure and cascading-failure evidence.
2. **Scalability:** fan-in bottleneck analysis against the scaling strategy and declared elastic technologies.
3. **Security/Compliance:** a control-coverage checklist plus a compliance-status tally.
4. **Latency:** declared performance targets cross-checked against the deepest dependency chain.

---

## Project layout

```
registries/<name>.hocon       One file per agent network. manifest.hocon registers which ones serve.
coded_tools/common/            Shared, framework-agnostic logic (paths, mailbox, loop control,
                               process/drawio JSON persistence, directory-file extraction).
coded_tools/common/docgen/     ISO-formatted Word document + flow/UML diagram generation, for both
                               the process and design schemas.
coded_tools/<network>/        Thin CodedTool wrappers neuro-san resolves per-network (its "class"
                               field is always relative to coded_tools/<network_name>/) -- mostly
                               one-line re-exports of the shared logic in coded_tools/common/.
output/                       Generated artifacts (process_data.json, cloudarch_drawio.xml,
                               requirements_summary.json, approval.json, *.docx, *_flow.png, ...)
                               -- gitignored.
cli.py                        Standalone CLI entry point -- see "CLI (cli.py)" above.
Dockerfile                    Container image -- see "Docker" above.
codeDoc/                      Structure diagrams (class inventory/hierarchy, network composition,
                               rendered class/sequence PNGs) -- see codeDoc/README.md.
```

See [`codeDoc/README.md`](codeDoc/README.md) for class and network-composition diagrams (Mermaid +
rendered PNGs) if you're navigating this codebase for the first time or extending it.

---

## NeuroSAN implementation notes

This section covers implementation details and deliberate differences worth knowing about if
you're comparing this to a similar system built on a different agent framework, or extending it
further.

**Why the generate/review loop looks the way it does.** neuro-san has no built-in "run until
approved, then stop" loop primitive. Every pipeline's front-man instead follows the same explicit
convention: *reset state → generate → review(s) → `loop_control` → continue-or-stop*.
`coded_tools/common/iteration_feedback.py` is the generate/review feedback mailbox
(`output/iteration_feedback*.json`, with a per-channel variant so multiple reviewers in the same
pass don't overwrite each other) and cumulative approval state (`output/approval.json`).
`coded_tools/common/loop_control.py` returns an authoritative `"STOP"`/`"CONTINUE"` verdict that a
front-man's own instructions are told to treat as final — checked in the order that matters
(approval before max-iterations, so a genuine approval on the last allowed iteration reports as
approved, not exhausted).

**`max_execution_seconds`.** neuro-san gives every agent a 300-second execution budget by default,
independently at every level of a call chain — a top-level front-man has its own budget, and
whichever pipeline it routes to has a *separate* 300s budget of its own. A full process generation
(analysis → design → compliance → simulation, looped, plus one subprocess-expansion call per
top-level step) can genuinely exceed 5 minutes. `config/llm_config.hocon` sets
`"max_execution_seconds": 3600`, which every network inherits.

**Conversation-history summarization.** A pipeline front-man calls several of its own tools in
sequence within one turn (reset → generate → review(s) → `loop_control`, repeated up to the
pipeline's own iteration cap), and each call+result pair is appended to that agent's own chat
history. Since every stage re-reads its real state from disk (`load_master_process_json`,
`load_iteration_feedback`, etc.) rather than from that accumulated history, it's safe to let
neuro-san's built-in summarization middleware condense older messages once a front-man's own
history crosses a threshold, keeping only the most recent few for continuity.
`config/llm_config.hocon`'s `"pipeline_middleware"` configures
`neuro_san.middleware.neuro_san_summarization_middleware.NeuroSanSummarizationMiddleware`
(triggers at 150,000 tokens, keeps the last 8 messages), referenced via `${pipeline_middleware}`
on each of the five pipeline front-men (`process`, `process_update`, `design`, `design_update`,
`cloudarch`) — the rest (consultants, scenario-testers, simulation-queries) don't run a
comparable multi-step self-loop, so they don't need it. The middleware constructs its own LangChain
model and does not inherit the network's `llm_config`; its configured `"model"` therefore needs to
match an available provider/API key. It currently uses `openai:gpt-6-luna`, so `OPENAI_API_KEY`
works without requiring `GOOGLE_API_KEY`. This is covered by
`tests/test_pipeline_middleware.py`.

**Cloud architecture diagrams rendering with messy, overlapping, or box-crossing arrows and
labels.** Three real generated diagrams, each shown directly, surfaced seven distinct real causes
across three rounds — the first two rounds fixed cosmetic crowding (labels/lines landing too close
together); the third round, against a more complex real diagram, found `_route_edge` could still
route a line straight **through** an unrelated box, not just crowd one. All seven are fixed,
confirmed directly against reconstructions of all three real diagrams (not just reasoned about),
with regression tests for each. This is the single layout engine behind both diagram *creation* and
*updates* — `CloudArch_Pipeline` calls the same `save_drawio_structured` → `build_structured_drawio_xml`
path regardless of which one a user asked for, so every fix below applies to both:

1. **Labels landing on zone boundaries.** `_route_edge` deliberately routes bent edges through the
   reserved gaps *between* zones/rows (so a line never cuts through a box) — but nothing ever told
   drawio where to put the LABEL on that bent path, so it fell back to drawio's own default: the
   midpoint by raw arc length of the whole polyline. For an uneven multi-segment path (a short leg,
   then a long leg, then another short leg), that arc-length midpoint can land barely past the first
   corner, i.e. right where a zone's own border line sits. Fixed by `_label_position_fraction`,
   which instead places the label at the midpoint of the path's LONGEST straight segment.
2. **Multiple edges sharing one box's connection point.** Every edge got a connection point fixed at
   the dead-center of whichever side it approached a box from, with no awareness of how many OTHER
   edges also connected to that same box on that same side — e.g. an API Gateway fanning out to two
   Fargate clusters had both edges start at the IDENTICAL pixel. Fixed by `_assign_connection_slots`,
   which groups edges by `(box, side)` and spreads them evenly across that side.
3. **Unrelated edges' labels landing close together by coincidence.** `_label_position_fraction`
   only keeps a label off corners on its OWN edge's path — two entirely unrelated edges (different
   source AND target) could still compute to nearly the same point (confirmed: two real labels only
   5px apart). Fixed by `_resolve_label_collisions`, a pairwise pass that nudges any pair closer than
   a threshold apart by the minimum needed to clear it, via a standard mxGraph label `offset`.
4. **Same-row edges between non-adjacent zones cutting through the zone between them.** The
   same-row routing picked an x midway between src's and tgt's own box edges, assuming their zones
   are immediate neighbors — when another zone sits between them (e.g. an ingest source routing
   straight to a component two zones over), that midpoint lands inside the intervening zone, and the
   line visibly sliced through whatever component was there.
5. **Cross-row edges from a component with siblings in the way cutting through them.** Routing
   straight down from a component's own x to reach a later row ignored any OTHER components stacked
   between it and that row within its own zone — the first of several stacked components routing to
   a later row cut straight through its own siblings below it.
6. **Cross-row edges skipping an entire intervening row cutting through that row's own zone.** An
   edge from row 0 to row 2 only ever computed a channel between row 0 and row 1, then dropped
   straight down through the whole of row 1 to reach row 2 — if row 1 held a single zone stretched to
   the row's full width (a common shape for a "spans everything" tier), there was no x left that
   wasn't inside it.
   Fixes 4-6 are all fixed by `_safe_x_for_vertical_span`, which verifies (and searches outward from)
   a candidate route coordinate against every real component it would actually pass, instead of
   assuming a coordinate derived from box/row geometry is automatically clear.
7. **Two edges landing in the same physical gap via different routing branches getting no stagger
   coordination.** `_channel_key` groups edges sharing a channel so they fan out instead of
   overlapping, but its grouping for the row-gap channel didn't match which edges actually ended up
   routed through it once fixes 4-6 started sending MORE edges through that same gap — a same-row
   detour and an adjacent-row edge could land in the identical gap under different channel keys and
   render as overlapping lines with no coordination between them. Fixed by making `_channel_key`'s
   row-gap key match `_route_edge`'s own choice of which gap it actually uses.

This file (`coded_tools/cloudarch/cloudarch_layout_engine.py`) is a byte-identical copy of the ADK
original's `cloudarch_layout_agent.py` (confirmed via `diff`/md5 before each round of fixes, so this
genuinely wasn't a missed port of an existing upstream fix — every bug was equally present, and
unfixed, in both); every fix was applied to both to keep them in sync, along with this port's own
previously-nonexistent dedicated test coverage for this module (`tests/test_cloudarch_layout_engine.py`,
ported from the ADK original's `tests/test_cloudarch_layout_agent.py`, which this port had never
carried over, plus new tests for all seven fixes above).

**Deliberate simplifications** (functional parity, not line-for-line fidelity with any particular
reference implementation):
- Plain `-d`/`--detached` still defaults to `ns run`'s own server/UI, which has no built-in auth/
  rate-limiting (see [Known issues](#known-issues) above) — `-d --flask` is the opt-in alternative
  that has both, matching the ADK original's own `-d` mode exactly (see Running below).
- Per-session artifact isolation is not implemented (see Known issues above) — only
  `output/requirements_summary.json` prefers a session's own save (via neuro-san's `sly_data`) over
  the shared on-disk file; nothing else does yet.
- `cloudarch`'s diagram generation always uses the structured, deterministic layout engine; there's
  no free-hand/hand-written-XML path.
- Document theming always applies the single built-in "Corporate Standard" theme — there's no
  configuration toggle to pick a different theme or disable it.
- **No prompt/context caching** (distinct from the summarization middleware above). Confirmed via
  direct inspection of neuro-san's Gemini LLM policy and middleware package: there's no equivalent
  to server-side cached-content reuse across turns — every call sends its full prompt. Only a
  generic LangChain response-cache passthrough exists, and only for the Bedrock provider, unused
  by this project's own `gemini-3-flash` configuration.
- The design pipeline's optional grounding stage (spec cross-check against an OpenAPI document) is
  not implemented — it would default off regardless.
- `review_and_governance` (review history/change log/approval workflow) is never populated — it
  describes events that haven't happened yet at generation time, so no section is rendered for it.

---

## Verification

- `uv run pytest` — directory extraction, drawio save/load round-trips, the deterministic cloud
  architecture layout engine (no two boxes ever overlap, every edge routes through reserved space,
  every edge label lands away from a corner), all three Monte Carlo simulations (process
  cycle-time, cloudarch resilience/scalability/latency, design-document resilience/scalability/
  security/latency blast-radius), the per-channel feedback mailbox, full pipeline integration tests
  calling the real `CodedTool` classes in the front-man's own sequence, end-to-end
  document-generation tests for both schemas, HOCON structural validation for every network, and
  `loop_control` unit-tested against the exact ordering that matters (approval checked *before*
  max-iterations).
- `uv run ns chat <network> --one-shot` against every network — confirms the full network (every
  agent, every `CodedTool`'s `"class"` resolution) loads and resolves correctly end-to-end.
- `uv run python cli.py -i "..."` against `process_architect` — confirms the CLI's direct neuro-san
  session wiring independently of the `ns chat`/`ns validate` tooling above.
- **CI** (`.github/workflows/testbuild.yml`): a dedicated `neurosan_processengineering_tests` job
  runs the full `pytest` suite on every push/PR touching `samples/**`. The `build_and_test` matrix
  separately builds and smoke-tests this project's Docker image (`neurosan_process` entry).
