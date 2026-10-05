# ProcessEngineering (neuro-san port)

A port of [`samples/GCP/ProcessEngineering`](../../GCP/ProcessEngineering)'s **functionality** to
[Cognizant's neuro-san](https://github.com/cognizant-ai-lab/neuro-san) multi-agent framework. This
is a functional port, not a code port: the ADK original is built on Google's Agent Development Kit
(Python `LlmAgent`/`LoopAgent`/`SequentialAgent` classes); this project is built on neuro-san's
declarative HOCON agent networks + Python `CodedTool`s. No ADK code is reused — every agent's
*instructions* and every tool's *logic* were ported deliberately, verified independently, and
re-expressed in neuro-san's own idioms.

## Status

**The port is complete.** All sixteen of the ADK original's agent networks are ported, wired, and
verified (structurally and functionally — see [Verification](#verification) below; a real LLM API
key is needed to exercise an actual conversation, which hasn't been done in this environment):

| Network | ADK original | What it does |
|---|---|---|
| `requirements_summary` | `Requirements_Summary_Agent` | Reads a directory of source files, extracts a structured, traceable requirements register, saves it for later reuse. |
| `requirements_consultant` | `Requirements_Consultant_Agent` | Answers questions about a previously-saved requirements summary. |
| `cloudarch` | `CloudArch_Pipeline` (`CloudArch_Agent` + `CloudArch_Reviewer_Agent`) | Generates/refines a cloud architecture diagram (drawio/mxGraph XML) via a deterministic layout engine, audited by a reviewer agent in a generate→review→revise loop. |
| `cloudarch_consultant` | `CloudArch_Consultant_Agent` | Answers questions about an existing cloud architecture diagram. |
| `cloudarch_simulation_query` | `CloudArch_Simulation_Query_Agent` | Runs a resilience/scalability/latency simulation over an existing diagram and explains findings in business language. |
| `process` | `Full_Design_Pipeline` | Generates/refines a business process design JSON via analysis → design → compliance review → simulation review (looping until approved or a revision limit is hit), expands every top-level step into its own detailed subprocess, renders a flow diagram, and produces a final ISO-formatted Word document. |
| `process_update` | `Update_Design_Pipeline` | The same generate/review loop, applied as a delta against an existing process design in response to a change request, instead of a fresh generation. |
| `process_consultant` | `Consultant_Agent` | Answers questions about an existing business process design. |
| `process_scenario_tester` | `Scenario_Tester` | Tests what-if scenarios against an existing process design. |
| `process_simulation_query` | `Simulation_Optimization_Query_Agent` | Runs a cycle-time simulation over an existing process design and explains bottlenecks in business language. |
| `design` | `Full_Design_Doc_Pipeline` | Generates/refines an architectural design document (HLD/LLD/Combined JSON) via analysis → design (HLD+LLD in one pass) → compliance review → architecture-simulation review, then renders a flow diagram and a final ISO-formatted Word document. |
| `design_update` | `Update_Design_Doc_Pipeline` | The same generate/review loop, applied as a delta against an existing design document in response to a change request. |
| `design_consultant` | `Design_Consultant_Agent` | Answers questions about an existing architectural design document, with license to bring in outside best-practice recommendations for design review. |
| `design_scenario_tester` | `Design_Scenario_Tester` | Tests what-if scenarios against an existing design document by tracing its real component dependency graph. |
| `design_simulation_query` | `Design_Architecture_Simulation_Query_Agent` | Runs a composite resilience (blast-radius Monte Carlo)/scalability/security/latency simulation over an existing design document and explains findings in business language. |
| `process_architect` | `Process_Architect_Orchestrator` (`root_agent`) | Top-level front-man routing a request to whichever of the fifteen networks above fits it, via neuro-san's same-server external-agent references. |

### A real bug found (and fixed) during this port

Porting `cloudarch_simulation_query`'s functionality surfaced a genuine, pre-existing bug in the
**ADK original**, not something introduced here. `parse_drawio_graph` only recognized a diagram
vertex via a shape token on the cell's *own* style. `build_structured_drawio_xml` (the now-default
diagram-generation path, copied verbatim into this port) puts that shape token on a separate child
icon cell instead — the labeled parent cell that edges actually reference as source/target carries
no shape token itself. The ADK original's own test fixture for this function predates that
layout-engine change (made earlier in the same session that produced this port) and never exercised
the combination, so every edge from a structured-engine-generated diagram has been silently
matching no real vertex — not a crash, a silently wrong, all-isolated-nodes graph presented as a
valid simulation result. Fixed here in `coded_tools/cloudarch/drawio_graph.py` (recognizes a vertex
via its own style OR a child cell's, when that child's parent is itself a vertex); worth porting
the same fix back to the ADK original's `utils.py`.

## Why neuro-san needed a different design for the generate/review loop

The ADK original's self-auditing pipelines are an ADK `LoopAgent` wrapping a generator + reviewer +
a stop-controller agent, with the stop controller setting `tool_context.actions.escalate = True` to
end the loop early on approval. **neuro-san has no equivalent runtime primitive.** This port
replaces it with:

- `coded_tools/common/iteration_feedback.py` — the generate/review feedback mailbox
  (`output/iteration_feedback*.json`) and cumulative approval state (`output/approval.json`).
  Ported near-verbatim from the ADK original's `save_iteration_feedback`/`load_iteration_feedback`
  — this was always just file I/O, nothing ADK-specific about it. **Extended with per-channel
  mailboxes** (`iteration_feedback_<channel>.json`) so multiple reviewers in the same pass (e.g.
  `process`'s Compliance_Agent *and* Simulation_Agent) don't overwrite each other's feedback before
  the generator reads it — the ADK original avoided this with a dedicated "refinement clone" agent
  immediately after each reviewer; here, the generator just reads every reviewer's channel together.
- `coded_tools/common/loop_control.py` — the one piece that *was* ADK-specific. A front-man agent's
  own instructions call this after every review and are told, explicitly, that its `"STOP"` verdict
  is authoritative ("you MUST NOT call the generator again"), replacing the runtime `escalate` flag
  with an instructed convention. Checked in the same order as the ADK original (approval before
  max-iterations — a genuine approval on the last allowed iteration must not be reported as
  "iteration budget exhausted") and unit-verified in isolation before being trusted in a real
  network.

Every pipeline network's front-man encodes the same shape: *reset state → generate → review(s) →
loop_control → continue-or-stop*.

### A real bug found (and fixed) in this port, caught only once a live LLM exercised it

Every structural check used throughout this port (`ns validate`, and "reaches the no-LLM-key
wall") has a blind spot: neither one ever actually resolves a `CodedTool` class or invokes a
sub-agent, because that only happens once a real model decides to call a tool — which needs a
working LLM key, which this environment never had until this was exercised against one for real.
That's exactly when a genuine, systemic bug surfaced: when a front-man calls an internal LLM
sub-agent as a tool, neuro-san's `BranchActivation.build()` constructs that sub-agent's triggering
`HumanMessage` from (1) one sentence per declared `"function.parameters.properties"` entry, filled
from the caller's tool-call arguments, and (2) an optional static `"command"` field on the agent's
own HOCON entry. Every "reads its own state from disk/mailbox, no arguments needed" stage agent in
this port (`Design_Agent`, `Compliance_Agent`, `Simulation_Agent`, `CloudArch_Reviewer_Agent`,
`Subprocess_Driver_Agent`, and their `_update`/`Design_Doc_*` counterparts — 14 agents across 5
network files) declared neither, so the HumanMessage submitted to start their turn was a literal
empty string. Gemini's SDK rejects an all-empty message list outright with `ValueError: contents
are required.` (confirmed via a live run); other providers may tolerate a system-prompt-only turn
with no human content, which is presumably why this had no chance to surface earlier. Fixed by
adding a short `"command"` field (e.g. `"Review the current architecture now."`) to every affected
agent — confirmed end-to-end against neuro-san's own `ArgumentAssigner`/`BranchActivation` code
path, not just "the YAML parses." `tests/test_hocon_agent_messages.py` guards against this
regressing: it loads every network the same way `ns chat`/`ns run` do and replicates neuro-san's
own assignments-string construction for every internal sub-agent.

### The document-generation stage

Both `process.hocon` and `design.hocon`/`design_update.hocon` end their pipeline with two more
CodedTool-only steps: `generate_*_flow_diagram` (a diagram inferred from the design's own
steps/dependencies or components/integration-points, pure `networkx`/`matplotlib`) and
`generate_*_document` (the final ISO-formatted `.docx`, pure `python-docx`). Both schema paths are
ported near-verbatim from the ADK original's `edge_inference_agent.py` and `doc_generation_agent.py`
+ its `helpers/doc_*.py`/`doc_design_sections.py` modules — all pure Python with zero ADK
dependency, living under `coded_tools/common/docgen/`. A single shared `generate_clean_diagram()`/
`create_standard_doc_from_file()` pair auto-detects (or is told explicitly) which schema is active
and dispatches to the right renderer — `_build_process_document` or `_build_design_document` —
so the process and design pipelines reuse the exact same diagram-inference and document-assembly
machinery rather than two parallel copies of it.

### A real bug found (and fixed) during doc-generation testing: sparse generated documents

The first real end-to-end run against a live LLM (a GitOps/Scrum process JSON) produced a
generated `.docx` that was missing or blanking content the real `process_data.json` clearly had.
Tracked down field-by-field against the real JSON, this turned out to be several distinct bugs,
some inherited from the ADK original and some new regressions in this port:

- **This port's own regression — complete content loss.** This port's `PROCESS_TEMPLATE`
  (`coded_tools/common/process_json.py`) gave `change_management`/`continuous_improvement` as bare
  empty **strings** (`""`), diverging from both the ADK original's own `process_schema.json`
  template *and* this port's own verbatim-ported renderers (which expect a **list** of objects). A
  real, well-formed `change_management` sentence was silently dropped entirely — the renderer's
  `for cm in items` iterated the string's characters, found none were dicts, and rendered nothing.
  Fixed by restoring the ADK's own template shape for every field (metrics/CSF/CFF/
  reporting_and_analytics/system_requirements/stakeholders/change_management/
  continuous_improvement all now give the LLM a concrete one-item example object instead of a bare
  `[]`/`""`), and by making `_add_change_management_section`/`_add_continuous_improvement_section`
  additionally tolerate a plain non-empty string (rendered as a descriptive paragraph) so a
  real value shaped that way is never discarded outright, regardless of which shape a given
  generation lands on.
- **Two genuine pre-existing bugs in the ADK original**, confirmed directly against its own
  `process_schema.json`/`doc_content.py`/`doc_governance.py` — not something this port introduced:
  `doc_content.py`'s overview section checks for an `"owner"` key, but the template's actual field
  is `"process_owner"`; and `doc_governance.py`'s reporting-and-analytics table checks `"name"`/
  `"title"`, but the template's own shape uses `"metric"`. Both fields rendered blank even on a
  perfectly template-conforming ADK run. Fixed in this port's `content.py`/`governance.py` by
  checking both the original and the correct key (worth porting back upstream).
- **Defensive hardening against whichever shape a model actually produces.** Even with the
  template fixed, a model will sometimes reasonably improvise its own internally-consistent
  `{"id": "CON-001", "description": "..."}` traceability-style shape for a list field instead of
  a plain string — confirmed directly against real generated output. Passing a bare dict straight
  to `doc.add_paragraph()`/`_add_bullet()` doesn't raise; python-docx silently iterates the dict's
  *keys* as characters, producing garbage like `"iddescription"`. `structure.py`'s new
  `_item_text(item, *content_keys)` helper tries each likely content key, falls back to joining
  every non-`"id"` value, and is now used by every bullet/name-cell renderer that touches a
  user-authored list field (constraints, assumptions, governance requirements, process triggers,
  process end conditions, metrics, CSF/CFF, stakeholders' Responsibilities column), so a document
  renders real content regardless of which shape a given generation happens to land on.
- **`consumed_keys` in `generation.py`** was missing `"purpose"`/`"scope"`/`"process_owner"`/
  `"owner"` even though all four ARE rendered in section 1.0 Overview, so they also duplicated,
  verbatim, into Appendix B's "leftover data" catch-all. Fixed by adding them to the set.

All of the above were verified against the user's own real `process_data.json` (not a synthetic
fixture), and locked in by `tests/test_docgen.py::test_real_world_doc_renders_id_tagged_dicts_and_string_shapes`,
which uses the exact real-world field shapes described here (id-tagged dicts, plain-string
change_management/continuous_improvement, role-only stakeholders).

A follow-up live run then surfaced one more instance of the same underlying class of bug: sections
5.0-8.0 (Metrics, Critical Success Factors, Critical Failure Factors, Reporting and Analytics) all
rendered with a blank Description column. The real data wasn't malformed this time -- each item
genuinely had only `{"id", "<name>"}` and no `"description"` at all, because `Analysis_Agent`'s
instructions (`registries/process.hocon`) named these four fields in a bare, shapeless bullet list,
unlike `constraints`/`assumptions`/`requirements_register`, which each get an explicit per-item
shape and an "ALWAYS include description" directive. A live model reasonably produced the
minimal shape nothing more specific was asked for. Fixed two ways: `Analysis_Agent`'s instructions
now give each of these four fields the same explicit `{"id", "<name>", "description", ...}` shape
and an "ALWAYS include description" directive the other fields already had; and
`validate_process_json` (`coded_tools/common/process_json.py`) now hard-rejects any
metrics/CSF/CFF/reporting_and_analytics entry missing a name or a description, the same way it
already hard-rejects a process_step missing a `step_name`/`responsible_party` -- so this can't
silently regress into prose-only guidance again, and `Design_Agent`'s existing
validate-fix-revalidate loop forces a correction before persisting rather than a human discovering
a blank column after the fact. Covered by
`tests/test_process_json.py::test_validate_rejects_metrics_csf_cff_reporting_entries_missing_a_description`
and its accepts-counterpart.

### The design-document pipeline's architecture simulation

`design.hocon`/`design_update.hocon`'s Simulation_Agent (and the standalone
`design_simulation_query` network) runs a different kind of simulation than `process`'s Monte Carlo
cycle-time one, because the design schema has no numeric duration field to simulate. Instead,
`coded_tools/design/simulation.py` (ported near-verbatim from the ADK original's
`design_simulation_agent.py`) models a blast-radius/cascading-failure Monte Carlo over the design's
real `high_level_design.components[].dependencies`/`integration_points[]` graph, combined with
structural scalability (fan-in bottleneck detection), security (control-coverage + real
`compliance_status` enum checks), and latency (dependency-chain depth vs. declared performance
targets) analyses — nothing here fabricates a number the schema doesn't actually have a field for.

### A neuro-san quirk worth knowing: declare `"parameters"` on every externally-referenced front-man

Wiring `process_architect` (the top-level front-man that reaches every other network via
`"/network_name"` external-agent references) surfaced a quirk, not a bug: a front-man whose
`"function"` has no explicit `"parameters"` block still works, but neuro-san synthesizes a default
single `"inquiry"` string parameter for it and logs a warning on every call. Harmless, but silent
and avoidable — every front-man meant to be called this way (all sixteen in this project) now
declares its own explicit `"parameters"` block instead of relying on the synthesized default, which
also gives each one control over exactly what its caller passes. Separately, an explicit *empty*
`"parameters": {"type": "object", "properties": {}}` is flatly **rejected** (not just warned about)
for a truly argument-less `CodedTool` — omit `"parameters"` entirely for those instead.

## Setup

```bash
uv sync
```

Set an LLM provider API key (see `config/llm_config.hocon` for the configured model;
`GOOGLE_API_KEY`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` etc. — see neuro-san's own
[`docs/api_key.md`](https://github.com/cognizant-ai-lab/neuro-san/blob/main/docs/api_key.md)):

```bash
uv run ns check-llm-keys
```

## Running

```bash
uv run ns run
```

Starts the neuro-san server (`:8080`) and the nsflow chat UI (`:4173`). Or chat with one network
directly from the CLI without the UI:

```bash
uv run ns chat requirements_summary
uv run ns chat cloudarch
uv run ns chat process
uv run ns chat design
uv run ns chat process_architect   # top-level front-man, routes across all other networks
# ... or any other network under registries/ -- see Status above for the full list
```

**A `neuro-san-studio` gap worth knowing, not a bug in this project:** `ns chat`'s default direct
(in-process) connection mode sets `PYTHONPATH` as an environment variable
(`ProjectEnvironment.apply()`), but setting `os.environ["PYTHONPATH"]` from inside an
already-running process has no effect on that process's own `sys.path` -- Python only reads
`PYTHONPATH` at interpreter *startup*. `ns run` doesn't hit this (it spawns the real server as a
child process, which correctly inherits `PYTHONPATH` at its own startup), but a plain `ns chat`
does, and the failure only surfaces the moment an agent actually calls a `CodedTool` (import
resolution genuinely breaks, with an error like `Could not find class "...CodedTool" ... under
AGENT_TOOL_PATH "coded_tools"`) -- not at session-open time, so it looks like the network loaded
fine right up until that point. Export `PYTHONPATH` in your shell yourself first, so the
interpreter inherits it correctly at startup:

```bash
export PYTHONPATH="$(pwd)"
uv run ns chat cloudarch
```

`cli.py` (below) isn't affected -- it's a plain script, so Python puts its own directory (this
project's root) on `sys.path[0]` automatically before any of its own code runs.

Run the test suite with:

```bash
uv run pytest
```

`uv run ns validate registries/<name>.hocon` structurally validates a network file without needing
an API key — useful while editing.

### CLI (`cli.py`)

Reinstates the ADK original's CLI surface (`process_agents/common/agent.py`) against this port,
talking to `process_architect` (the top-level front-man) by default:

```bash
uv run python cli.py                        # interactive chat REPL (default)
uv run python cli.py -i "design a vendor onboarding process"   # one prompt, print, exit
uv run python cli.py -f instructions.txt    # submit each line of a file as a turn, in order
uv run python cli.py -d                     # see below
uv run python cli.py --agent cloudarch      # talk to a different network directly
```

Same control lines as the ADK original work inside interactive/`-f` mode: `exit`/`quit`/`stop`,
`clear` (reset the session), a leading `#` (comment, echoed but not sent), `sleep <seconds>`/
`wait <seconds>`, a leading `$ ...` (run a raw shell command instead of sending the line to the
agent), and a trailing `\` to continue one logical line across multiple physical lines.

`-i`/`-f`/interactive mode talk to neuro-san directly via a **DIRECT, in-process session** (no
server needs to be running). `-d`/`--detached` is the one flag that behaves differently from the
ADK original on purpose: rather than reimplementing its bespoke Flask REST API (with its own
auth/rate-limiting), `-d` launches neuro-san's own server + nsflow UI (`ns run`) — see
[Deliberate simplifications](#deliberate-simplifications-vs-the-adk-original) for why that layer
isn't ported. `--http`/`-p`/`--port` only apply with `-d`, matching the ADK original.

Every run writes neuro-san's own "thinking" trace -- this project's equivalent of the ADK
original's `output/logs/pipeline_*.log` -- to `output/logs/agent_thinking.txt` (one combined
stream) and `output/logs/agent_thinking/` (one file per agent origin in a multi-agent turn,
easier to follow than the combined stream once more than one sub-agent is involved):

```bash
tail -f output/logs/agent_thinking.txt
```

A fresh session (startup, or the `clear` control line) clears the previous trace first, so it
never mixes two unrelated conversations together. This is neuro-san's own always-on record,
independent of the logging level described below.

`cli.py`'s own logging mirrors the ADK original's `agent.py` setup exactly: standard Python
`logging`, a `LOGLEVEL` env var (same name, same five values -- DEBUG/INFO/WARNING/ERROR/
CRITICAL, default `WARNING`), writing to `output/logs/cli.log`. **Off by default** -- this
project's own tool/sub-agent trace logs at DEBUG, and a per-turn token-accounting summary at INFO,
so neither appears anywhere unless you ask for it:

```bash
LOGLEVEL=DEBUG uv run python cli.py
tail -f output/logs/cli.log
```

```
2026-10-05 15:50:27 DEBUG ProcessArchitect.CLI.Trace: cloudarch.CloudArch_Pipeline [AGENT]: Calling reset_loop_state now.
2026-10-05 15:50:28 DEBUG ProcessArchitect.CLI.Trace: cloudarch.reset_loop_state [AGENT_TOOL_RESULT] (result from reset_loop_state): <structure: status>
2026-10-05 15:50:41 INFO ProcessArchitect.CLI.Trace: token accounting: {"gemini-3-flash": {"total_tokens": 2280}}
```

A WARNING+ copy of anything logged (including neuro-san/langchain's own internal warnings, e.g. a
timed-out agent) always prints to the terminal too, regardless of `LOGLEVEL` -- written to
**stderr** specifically, so it never corrupts output piped from stdout (e.g. `cli.py -i "..." |
pbcopy` capturing just the final answer). Confirmed directly: before this was wired up, that same
warning printed completely unformatted (no timestamp, no logger name) because nothing had
attached a handler to it at all, making it look like it had been echoed into the next `[user]: `
prompt rather than what it actually was -- a log line with nowhere configured to go.

### A real timeout worth knowing about: `max_execution_seconds`

neuro-san gives every agent a 300-second (5-minute) execution budget by default
(`RunContextRunnable.run_it`), independently at every level of a call chain -- `process_architect`
has its own 300s budget wrapping whichever pipeline it routes to, and that pipeline's own
front-man has a SEPARATE 300s budget of its own. `process`/`process_update`'s full sequence
(analysis → design → compliance → simulation, looped up to 2×, then `Subprocess_Driver_Agent`
making one further LLM call per top-level step) can genuinely exceed 5 minutes for a real
request -- confirmed directly: both `Process_Architect_Orchestrator` and the nested
`Process_Pipeline` timed out independently on the same request. Fixed by setting
`"max_execution_seconds": 3600` in `config/llm_config.hocon`, which every network already
`include`s, so the higher budget applies everywhere in one place.

### Docker

Ported from the ADK original's `Dockerfile`, re-expressed for this project's own tooling (`uv` +
`pyproject.toml`/`uv.lock`, not `pip`/`requirements.txt`) and serving model (`ns run`'s own HTTP
server, not a hand-rolled entrypoint):

```bash
docker build -t processengineering-neurosan .
docker run --rm -p 8080:8080 -e GOOGLE_API_KEY=... processengineering-neurosan
```

Builds and starts cleanly with no LLM key set too (confirmed: every one of this project's networks
loads into the running server with zero errors) — you'll only hit the familiar "no LLM API key"
wall once you actually chat with it. Pass whichever provider key you're using via `-e` at `docker
run` time (`GOOGLE_API_KEY`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/etc.) — never bake one into the
image.

## Project layout

```
registries/<name>.hocon       One file per agent network. manifest.hocon registers which ones serve.
coded_tools/common/            Shared, framework-agnostic logic (paths, mailbox, loop control,
                               process/drawio JSON persistence, directory-file extraction).
coded_tools/common/docgen/     ISO-formatted Word document + flow/UML diagram generation, for both
                               the process and design schemas -- see "The document-generation
                               stage" above.
coded_tools/<network>/        Thin CodedTool wrappers neuro-san resolves per-network (its "class"
                               field is always relative to coded_tools/<network_name>/) -- mostly
                               one-line re-exports of the shared logic in coded_tools/common/.
output/                       Generated artifacts (process_data.json, cloudarch_drawio.xml,
                               requirements_summary.json, approval.json, *.docx, *_flow.png, ...)
                               -- gitignored, same filenames/shapes as the ADK original so the two
                               samples describe the same artifacts even though no code is shared.
cli.py                        ADK-compatible CLI entry point -- see "CLI (cli.py)" above.
Dockerfile                    Container image -- see "Docker" above.
```

## Deliberate simplifications vs. the ADK original

Ported for *functional* parity, not line-for-line fidelity. Noted here rather than silently:

- **Custom Flask web-service layer (auth, rate-limiting, per-session isolation) is not ported.**
  neuro-san's own `ns run` server + nsflow UI already serves multiple concurrent sessions; that
  hardening was specific to the ADK sample's bespoke Flask mode.
- **`cloudarch`'s freehand-XML path (`save_drawio`) is not ported.** The structured, deterministic
  layout engine (`save_drawio_structured`) is the default and only path here — the ADK original
  only ever fell back to freehand XML on explicit user request, which this port doesn't yet expose.
- **`process`'s JSON validation is a minimal structural check** (required fields present, every
  step has a `step_name`/`responsible_party`, dependencies reference real steps), not the full
  `process_schema.json` JSON-Schema document the ADK original validates against.
- **Pure-logging ADK tools with no state effect** (`log_cloudarch_metadata`,
  `log_cloudarch_reviewer_metadata`, `log_design_metadata`) are dropped entirely — confirmed
  side-effect-free in the original before cutting them, to keep each network's tool list to what
  actually matters.
- **`output/requirements_summary.json` session-scoping uses neuro-san's `sly_data`** in place of
  the ADK original's `tool_context.state` — same idea (a session's own save is preferred over
  whatever a different concurrent session most recently overwrote the shared file with), different
  mechanism's name.
- **The ADK original's separate JSON-normalization loop** (a dedicated `JSON_Normalizer_Agent` +
  `JSON_Review_Agent` sub-loop, run after compliance/simulation approve) **is absorbed into
  `Design_Agent`'s own validate→persist steps** here, rather than ported as a fourth separate
  reviewer agent — `Design_Agent` already repairs and validates before every `persist_final_json`
  call, which is the same structural-completeness guarantee under a different label.
- **The subprocess generator and writer are merged into one agent.** The ADK original hands a
  generated subprocess flow between two agents via ADK session state (a generator, then a separate
  writer that persists it). Here, `Subprocess_Generator_Agent`'s own tool-call arguments already
  carry the validated data directly — there's no session-state hand-off to replicate, so
  `save_subprocess_flow` does the writer's persistence+path-safety job in the same step.
- **`design`'s HLD and LLD generation are one agent, one pass.** The ADK original runs a separate
  `Design_Doc_HLD_Agent` then `Design_Doc_LLD_Agent` (each its own LLM call), then reuses a third
  "Combined" generator cloned three more times as the post-compliance/post-simulation/post-
  grounding refinement step. Here, one `Design_Doc_Agent` populates `high_level_design` and
  `low_level_design` together and is the only generator the review loop ever calls again — same
  simplification `process.hocon` already makes for its own single `Design_Agent`.
- **The design pipeline's optional grounding stage (OpenAPI-spec cross-check) is dropped
  entirely.** It defaults OFF in the ADK original (`enableGroundingAgent=false`) and is a straight
  clone of the process pipeline's own grounding agent/instructions there (no design-specific
  logic) — dropping it removes an always-disabled path rather than any real design-side behavior.
- **The design pipeline's separate JSON-normalization loop is absorbed into `Design_Doc_Agent`'s
  own validate→persist steps**, the same simplification `process.hocon` makes for its own
  `Design_Agent`.
- **`review_and_governance` (review history/change log/approval workflow) is never populated.**
  The ADK original's own instruction files already tell the generating agent to leave it empty on
  creation, since it describes events (reviews, approvals) that haven't happened yet; this port
  simply never renders a section for it either, rather than rendering an always-empty one.

## Verification

Every piece above was checked at the Python level (not just "the YAML parses") before being
trusted in a network:

- `uv run pytest` — a real test suite (`tests/`), not just ad-hoc scripts: directory extraction,
  drawio save/load round-trips, all three Monte Carlo simulations (process cycle-time, cloudarch
  resilience/scalability/latency, and design-document resilience/scalability/security/latency
  blast-radius) against known inputs, the per-channel feedback mailbox (proving two reviewers
  writing in the same pass don't clobber each other), full pipeline integration tests calling the
  real `CodedTool` classes in the front-man's own sequence, end-to-end document-generation tests
  (a real `.docx` built and its headings inspected, for both schemas), HOCON structural validation
  for every ported network, and critically, `loop_control` unit-tested against the exact ordering
  the ADK original's docstring calls out as load-bearing: approval checked *before*
  max-iterations, so a genuine approval on the final allowed iteration reports as approved, not
  exhausted.
- `uv run ns chat <network> --one-shot` against every network — confirms the full network (every
  agent, every `CodedTool`'s `"class"` resolution) loads and resolves correctly end-to-end; each
  one correctly reaches (and only fails at) the "no LLM API key configured" step, since no live
  credentials are available in the environment this was built in.
- `uv run python cli.py -i "..."` against `process_architect` — confirms the CLI's direct neuro-san
  session wiring independently of the `ns chat`/`ns validate` tooling above.
