# ProcessEngineering: Agent Discovery API & Open Agentic Web Alignment

## 1. Executive Summary

This document covers two distinct things, kept carefully separate:

1. **ProcessEngineering's own Agent Discovery API** -- a REST surface, shared by both the
   Google Cloud ADK (`samples/GCP/ProcessEngineering`) and Neuro-San
   (`samples/Neurosan/ProcessEngineering`) backends, for MCP-style clients (Claude, Cursor,
   VS Code, OpenAI Agent SDK) to discover this platform's agents, artifacts, and workflows.
   This is a real, working, useful API -- but it is **this project's own convention**, not
   an implementation of any external standard.

2. **Genuine alignment with the external "Open Agentic Web" standard**
   (https://github.com/cognizant-ai-labs/agentic-web) -- the Neuro-San port publishes its
   agent networks as portable, resolved JSON exactly per that spec's own file conventions.
   This piece is real, narrow, and explicitly scoped (see §4 below for what it does and
   does not cover).

An earlier version of this document, and the code it described, claimed the REST API in
part 1 *was* an implementation of the external standard in part 2. That claim was wrong --
checked directly against the standard's own README and its full MVP Profile 0.2
specification document, neither of which describes anything resembling a server-side REST
discovery API. The external spec is specifically about publishing a resolved **Neuro-San
HOCON agent network** as JSON, executed by a **browser runtime** (the reference
implementation is `nsDeploy`) using **visitor-supplied (BYOK) LLM credentials** -- a
fundamentally different model from a server-executed, server-funded Python backend. "Agent
Cards" (inputs/outputs/category/provenance) is actually terminology from a *different*,
related protocol (A2A); the Open Agentic Web spec explicitly notes that a site may
separately publish an A2A Agent Card, but that its own reference loader (`nsDeploy`) does
not consume it. This document, and the code's own docstrings/manifest fields, have been
corrected accordingly.

---

## 2. Status At A Glance: Done / Not Done / Compliant / Not Compliant

### Done

- **ProcessEngineering's own Agent Discovery API** (§3): `/.well-known/agent.json`,
  `/agents`, `/agents/<name>`, `/capabilities`, `/workflows`, `/workflows/<name>`,
  `/artifacts/contracts`, `/artifacts/contracts/<type>` -- shared code, both ports, plus
  FastMCP tool equivalents on the MCP server. Honestly labeled as this project's own
  convention.
- **Real Open Agentic Web data publication, Neuro-San port** (§4): `/agent-manifest.json`
  (real spec shape: `{"networks": {<name>: {name, description, front_man, hocon}}}`) and
  `/networks/<name>.network.json` (fully resolved agent-network JSON), for all 42 publicly
  listed `registries/*.hocon` networks.
- **nsDeploy feasibility investigation** (§4.2): hands-on, not theoretical -- installed and
  run against this project's own registries, with concrete results recorded.

### Not Done

- **Browser execution of this project's pipelines** -- no network is actually running inside
  a browser runtime anywhere in this project. `network_publishing.py` only publishes the
  *data* a browser runtime would need; nothing in this repo consumes it that way.
- **Hosting this project's real coded tools through nsDeploy (or any MCP-in-the-browser
  path)** -- confirmed broken in nsDeploy's static mode (all 15 of `design.hocon`'s tools
  silently dropped); untested and expected to be hard in served mode, due to this project's
  own session-state assumptions (`output/` dirs, pipeline locks, session purging).
- **BYOK for this platform's own agents** -- still server-managed LLM credentials
  throughout. (nsDeploy's own BYOK, `runtime/byok.js`, works -- but only for networks
  actually running inside it, which this project's pipelines aren't.)
- **GCP/ADK data publication** -- no HOCON there at all; would need an ADK-to-HOCON
  converter, not attempted.
- **`links.json`** -- nothing to publish yet (no genuinely external peer references exist in
  this project's registries).
- **Peer-consumption protocol** (spec §3.2: loading *another* site's network into this one) --
  not implemented; this project is a publisher only, and has no browser runtime to consume
  anything into.

### Compliant (with the real external "Open Agentic Web" spec)

- **Tenet One (Common Multi-Agent Representation)** -- Neuro-San port only. The published
  `agent-manifest.json` + `<network>.network.json` files use the spec's own required shape
  and the actual Neuro-San HOCON data model, at the spec's own conventional paths.
- The overall pattern matches the spec's own named "Private stewards" extension (§7) --
  recognized by the spec itself as legitimate, not partial/lesser conformance.

### Not Compliant

- **Tenet Two (Browser Execution)** -- not implemented anywhere in this project.
- **Tenet Three (Pluggable Inference / BYOK)** -- not implemented for this project's own
  agents.
- **§6 "MVP Interoperability Checks"** (the spec's own literal conformance test) -- cannot
  be passed without Tenets Two and Three, since most of the checks are behavioral
  (load-and-run in a browser, prove a peer never receives the visitor's key), not data
  checks.
- **GCP/ADK port** -- zero alignment; no HOCON, no publication, no claim.
- **ProcessEngineering's own Agent Discovery API (§3)** -- was never a conformance attempt
  in the first place; listed here only to be explicit that it still isn't one.

This is a deliberate, evidence-based stopping point (see §4.2's nsDeploy findings for why),
not an oversight. If priorities change, §4.2's "Done" items (the manifest/network JSON
publication) remain a correct, reusable foundation for later work -- nothing here needs to
be redone, only extended.

---

## 3. Part One: ProcessEngineering's Own Agent Discovery API

Shared infrastructure lives in `shared/process_toolkit/src/process_toolkit/agentic_web/`:

```
shared/process_toolkit/src/process_toolkit/agentic_web/
├── __init__.py               # Re-exports of all capabilities, cards, and workflows
├── agent_cards.py            # 32 machine-readable AgentCard definitions
├── artifact_contracts.py     # 13 ArtifactContract specifications & envelope wrapper
├── workflows.py              # 6 engineering lifecycle workflow definitions
└── registry.py               # Manifest generator and capability search engine
```

Exposed identically via `shared/process_interface/src/process_interface/agentic_web.py`
(switchable local/MCP, same pattern as the rest of `process_interface`), and wired into
both ports' Flask servers (`samples/GCP/ProcessEngineering/process_agents/common/agent.py`,
`samples/Neurosan/ProcessEngineering/cli.py`):

| Endpoint | Method | Description |
|---|---|---|
| `/.well-known/agent.json` | `GET` | This project's own discovery manifest |
| `/agents` | `GET` | Capability registry of all agent cards |
| `/agents/<name>` | `GET` | Detailed Agent Card for a specific agent |
| `/capabilities` | `GET` | Searchable capability catalog with filtering |
| `/workflows` | `GET` | Lists all available lifecycle workflows |
| `/workflows/<name>` | `GET` | Step ordering, transitions, produced artifacts |
| `/artifacts/contracts` | `GET` | Lists all artifact contracts |
| `/artifacts/contracts/<type>` | `GET` | Full schema fields, mime type, producer |

Query parameters for `/agents` and `/capabilities`: `?category=`, `?artifact=`, `?type=`,
`?query=`, `?full=true`, `?wrapped=true`. All of these routes bypass authentication and
rate-limiting (see each port's own `_enforce_web_controls`), since they're meant to be
inspectable by external orchestrators without prior credentials.

These routes are also exposed as FastMCP tools by `samples/MCP/ProcessToolkitServer/server.py`
(`get_agent_manifest`, `list_agents`, `get_agent_card`, `list_workflows`, `get_workflow`,
`list_artifact_contracts`, `get_artifact_contract`) for MCP clients that prefer tool calls
over raw HTTP.

This part of the platform makes **no conformance claim** against any external
interoperability standard -- it's documented here because it's genuinely useful, not
because it satisfies someone else's spec.

---

## 4. Part Two: Open Agentic Web Alignment (Neuro-San Port Only)

### 4.1 What this actually publishes

`samples/Neurosan/ProcessEngineering/network_publishing.py` publishes this project's
Neuro-San agent networks per the real spec's section 3.3 ("Minimum Public Files"):

| Endpoint | Method | Description |
|---|---|---|
| `/agent-manifest.json` | `GET` | `{"networks": {<name>: {name, description, front_man, hocon}}}` for every publicly-listed `registries/*.hocon` network |
| `/networks/<name>.network.json` | `GET` | The resolved (includes + substitutions expanded) agent-network JSON for one published network |

- **Which networks are published**: every entry in `registries/manifest.hocon` -- this
  project's own existing, authoritative "what does this site serve" list -- that is not
  explicitly marked `"public": false`. That file already distinguishes publicly-listed
  networks from internal support networks (e.g. the Agent Network Designer's own helper
  networks), so this reuses an existing decision rather than inventing a new one.
- **How the JSON is resolved**: via `neuro_san.internals.graph.persistence.
  agent_network_restorer.AgentNetworkRestorer` -- the same class `cli.py` already uses
  elsewhere (`_build_agent_instructions_index`) to fully resolve a registry's HOCON
  `include`s and `${...}` substitutions. No new HOCON-resolution logic was written.
- **`front_man`**: not an explicit HOCON field -- computed the same way this project
  already establishes it elsewhere (`basic/music_nerd.hocon`'s own header comment, mirrored
  in `cli.py`): the first top-level `tools` entry with both a `name` and `instructions`.

### 4.2 Scope & limitations (read this before assuming "compliant")

This is **data-portability only** -- Tenet One of the spec ("Common Multi Agent
Representation"). It deliberately does **not** attempt:

- **Tenet Two (Browser Execution)**: the spec requires a browser runtime (`nsDeploy`) to
  actually *run* a published network client-side. This platform's agents still run
  server-side, in Neuro-San's own Python runtime or Google ADK -- publishing the network
  JSON does not change that.
- **Tenet Three (Pluggable Inference / BYOK)**: the spec's model is that the *visitor*
  supplies their own LLM router and credential. This platform uses server-managed LLM
  credentials; it is not BYOK.

**Checked directly, not just assumed -- here's why Tenets Two/Three were deliberately not
pursued further.** `nsDeploy` (the spec's own reference runtime, Apache-2.0,
https://github.com/cognizant-ai-lab/nsdeploy) was installed in an isolated environment and
run against this project's own registries via `--studio <project-root>` (its "point at an
arbitrary local checkout" mode, not just the public `neuro-san-studio` repo it defaults to):

- `basic/music_nerd.hocon` (a pure chat agent, no coded tools) built a complete, correct
  static bundle: real `index.html`, a real `agent-manifest.json`, and the full vendored JS
  runtime -- including real, already-working BYOK (`runtime/byok.js`). The "write a browser
  runtime from scratch" problem is genuinely solved by adopting this tool.
- `design.hocon` (a real pipeline, 7 agents, 15 coded tools) resolved correctly against this
  project's own layout -- but **every one of its 15 coded tools was silently dropped**, with
  nsDeploy's own message: *"static bundles do not install or execute Python tools."* A
  static deployment of this pipeline would be a chat UI that can talk about design but
  cannot generate, validate, persist, or simulate anything -- none of what the pipeline is
  actually for. Running them for real needs nsDeploy's *served* (non-static) mode, which
  hosts Python tools as local MCP servers -- untested here, and expected to be genuinely
  hard: this project's coded tools depend on `process_interface`/`process_toolkit`'s own
  session model (contextvar-scoped `output/` directories, pipeline locks, session purging)
  that a generic "wrap a Python function as an MCP tool" host has no reason to know about.
  Getting each tool working would be its own, per-pipeline integration effort, not a
  configuration flag.
- A minor, non-fatal HOCON-resolution mismatch also surfaced (`Cannot include file title`),
  a sign this project's HOCON wasn't written with this specific resolver in mind.

**Conclusion: not worth doing.** The browser-runtime problem (building Tenet Two/Three from
scratch) turned out to be solved for free by an existing tool. The tool-integration problem
(making this project's actual pipelines do real work through it) did not, and is
substantial, per-pipeline, uncertain-until-attempted engineering -- for a platform that
already works well as a server-executed system. This was a deliberate stop, made with real
evidence in hand, not an unexamined gap.

This combination -- publishing public network data while keeping execution and credentials
server-side -- is explicitly named by the spec itself (section 7, "Private stewards") as a
recognized extension pattern, not a failure to conform: *"Operator-hosted Neuro SAN
networks that keep credentials and private policy on the steward's server while loading and
running public agent networks locally."* That's an accurate description of what this
section implements.

**GCP/ADK is not covered.** That port has no Neuro-San HOCON registries at all -- it's
built on Google ADK's own agent/tool object model. The spec itself notes that other
frameworks "map into this representation" via a converter, and names Google ADK
specifically as a candidate for one. Building that converter (with the semantic-equivalence
verification it would need) is real, separate, and larger work -- not attempted here. GCP's
`/agent-manifest.json` path is intentionally unserved (404) rather than faked.

**`links.json` is not published.** That file maps symbolic external (different-origin) peer
network references to concrete URLs. None of this project's own registries reference a
genuinely external peer today -- every cross-network reference (e.g.
`process_architect.hocon`'s own `"/design_update"`) is a same-server internal reference.
There is nothing for `links.json` to resolve yet.

**No peer-consumption protocol.** This section makes this project a valid network
*publisher*. It does not implement the spec's own consent/loading protocol for *consuming*
someone else's published network (section 3.2) -- that's a browser-runtime concern, and
this project doesn't run one.

### 4.3 Verifying it

```bash
cd samples/Neurosan/ProcessEngineering
uv run python -c "
import cli
app = cli.build_web_app('process_architect', https=False)
client = app.test_client()
print(client.get('/agent-manifest.json').get_json())
print(client.get('/networks/design.network.json').get_json())
"
```

Or against a running server:

```bash
curl http://localhost:8080/agent-manifest.json
curl http://localhost:8080/networks/design.network.json
```

---

## 5. External Agent Invocation & Interoperability

External agents (Claude Code, Cursor, VS Code Copilot, OpenAI Agent SDK, LangChain, AutoGen)
can interact with ProcessEngineering via three transport modes. None of these is itself an
Open Agentic Web conformance claim -- see §4 for the one piece that is.

### A. FastMCP / Model Context Protocol
Start the server in MCP mode:
```bash
PROCESS_TOOLKIT_MODE=mcp python -m process_interface.server
```
Add to your `claude_desktop_config.json` or `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "process_engineering": {
      "command": "python",
      "args": ["-m", "process_interface.server"],
      "env": {
        "PROCESS_TOOLKIT_MODE": "mcp"
      }
    }
  }
}
```

### B. This Project's Own Agent Discovery API
```python
import httpx

# 1. Discover capabilities
manifest = httpx.get("http://localhost:5000/.well-known/agent.json").json()

# 2. Find design agents
agents = httpx.get("http://localhost:5000/agents?category=design").json()

# 3. Inspect artifact contracts
contract = httpx.get("http://localhost:5000/artifacts/contracts/high_level_design").json()
```

### C. OpenAI Agent SDK & Tool Calling
Invoke the agent network directly via the standard REST chat endpoint:
```python
import httpx

response = httpx.post(
    "http://localhost:5000/chat",
    json={
        "query": "Create an architecture design for an event-driven order processing system."
    },
    headers={"Authorization": "Bearer <API_KEY>"},
    timeout=120.0,
)
result = response.json()
print(result["response"])
```
