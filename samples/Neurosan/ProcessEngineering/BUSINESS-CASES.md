# Business Case: The Process Architect Agent Suite

**Scope:** this document covers the Process Architect agentic system — available as two
interchangeable implementations, Google ADK (`samples/GCP/ProcessEngineering`) and neuro-san
(`samples/Neurosan/ProcessEngineering`) — which generates, reviews, and maintains business process
documentation, technical design documents, cloud architecture diagrams, and cost estimates.

---

## The pitch, in one paragraph

Formal process documentation, design documents, cloud architecture diagrams, and requirements
registers are expensive to produce, slow to update, and go stale the moment they're published. This
agent suite produces all four — to a consistent, audit-ready standard, cross-referenced and
mutually consistent — in minutes instead of days, with compliance review, performance simulation,
and cost estimation built into the generation step itself rather than bolted on afterward. It
doesn't replace the people who own these documents; it replaces the multi-day first draft they
currently have to produce before their judgment is even needed.

---

## The business problem

Every organization running regulated, audited, or simply complex operations needs a standing
library of documentation it rarely has the capacity to properly maintain:

- **Business process documents / SOPs** — who does what, in what order, under what controls. Used
  for onboarding, audits, compliance attestations, and operational handoffs. Usually written once,
  under deadline pressure, and never revisited until an audit forces the issue.
- **Technical design documents (HLD/LLD)** — the architectural record a system is supposed to be
  built against. Frequently out of date within a quarter of being written, because updating one
  properly means re-touching every section it affects, not just the part that changed.
- **Cloud architecture diagrams and cost estimates** — typically produced by a cloud architect and
  then separately costed by a FinOps analyst days or weeks later, by which point the design has
  often already moved on. Early-stage cost estimates are commonly rough guesses rather than
  catalog-grounded numbers, which is exactly when a costly architectural mistake is cheapest to
  catch.
- **Requirements extraction** — turning a folder of emails, meeting notes, specs, and contracts into
  a single traceable requirements register is a real, recurring task before any of the above can
  even start, and it's almost always done by hand.

The common thread: these are high-value documents that take disproportionate specialist time to
produce in a *first-draft, compliant, internally consistent* form — and that time is spent before
any of the actual expert judgment (does this process make sense, is this architecture sound, is
this estimate realistic) even begins.

---

## What the agents actually produce

Every output below is a real, structured artifact — not a chat answer that has to be manually
transcribed into a document afterward.

| Capability | Output |
|---|---|
| **Process generation & update** | ISO-structured process document: stakeholders, step-by-step workflow with inputs/outputs/success criteria, detailed sub-process breakdowns (3–10 sub-steps per step, each with its own risks, governance, and change-management detail), metrics/KPIs, critical success/failure factors, governance & risk register, a rendered swimlane flow diagram, and a Monte Carlo cycle-time simulation identifying likely bottlenecks |
| **Design document generation & update** | HLD/LLD/combined design: components, interfaces, quality attributes, compliance & standards mapping, risk register, and a resilience/scalability/security/latency simulation against the design |
| **Cloud architecture diagram & FinOps** | A real drawio/mxGraph cloud architecture diagram (AWS/Azure/GCP), a dry-run resilience/scalability/latency analysis of that diagram, and a monthly cost estimate **grounded in live provider pricing catalogs** (not rule-of-thumb guesses), with concrete cost-optimization recommendations — rightsizing, autoscaling, reserved capacity, storage tiering, orphaned-resource detection |
| **Requirements extraction** | Reads a directory of source documents (PDF, Word, Excel, Outlook `.msg`) and produces a structured, ID-tracked requirements register with priority flags, conflict detection, clarification-needed flags, and a record of what it inferred versus what was explicitly stated |
| **Consultant / what-if / query agents** | Answer questions and run what-if scenarios against any of the above *without* re-running the full generation pipeline — fast, cheap, read-only access to what already exists |

Every generated document carries forward the same requirements register IDs from extraction through
process/design through to final sign-off, so a reviewer can trace any requirement to the exact step
or component that addresses it.

---

## Time and cost: what this typically replaces

These are indicative, order-of-magnitude figures based on common industry effort for comparable
manual work — not a guarantee, and actual savings depend heavily on process complexity, review
rigor, and your organization's own documentation standards. Use them as a starting point for your
own estimate, not a promised number.

| Deliverable | Typical manual effort (first draft) | With the agent suite |
|---|---|---|
| Formal process document / SOP, full ISO structure with sub-process detail | 3–10 business-analyst-days (stakeholder interviews, drafting, diagramming, formatting) | Minutes to a complete, reviewed first draft |
| HLD/LLD design document | Several senior-architect-days | Minutes |
| Cloud architecture diagram + cost estimate | 1–3 days across a cloud architect and a separate FinOps review | Minutes, with catalog-grounded pricing from the start |
| Requirements register from a document folder | Hours to days of manual reading and synthesis | Minutes |

At a loaded rate of roughly $75–150/hr for a business analyst or architect, a single formal process
document commonly represents **$1,500–$9,000 of labor** before any review cycle even begins. A
design/costing cycle that previously took a week of combined specialist time compresses to minutes
of generation plus the review time a human would need regardless — the expensive part isn't review,
it's getting to a reviewable first draft at all.

The compounding saving is in **maintenance**, not just first-draft creation: because generation is
cheap and repeatable, a process or design document can be regenerated after every material change
instead of being patched by hand and slowly drifting out of sync with reality — the single biggest
reason enterprise documentation libraries decay.

---

## Risk and quality, not just speed

- **Compliance and simulation review are part of generation, not a separate downstream step.**
  Every process and design document is automatically checked against compliance rules and
  performance/resilience simulation, with automatic revision cycles, before it's presented as final.
- **Structural *and* content-depth validation.** Outputs are rejected and regenerated if a section is
  merely schema-complete but substantively thin (a one-line placeholder instead of real detail) —
  this is enforced automatically, not left to a reviewer to catch after the fact.
- **End-to-end traceability.** Every requirement carries an ID from extraction through to the
  specific process step or design component that addresses it, which is exactly what an audit or a
  disputed scope conversation needs and almost never has.
- **Catalog-grounded cost estimates**, not heuristics — the FinOps output cites the actual pricing
  source and assumptions behind every number, so it can be defended in a budget conversation.

---

## Deployment flexibility

The same capability ships as two independent, functionally-equivalent implementations sharing one
business-logic core:

- **Google ADK** — for organizations standardized on Google Cloud and the Gemini model family.
- **neuro-san** — open-source orchestration, portable across infrastructure, and provider-agnostic
  (Gemini, Claude, GPT, or others) — a fit for multi-cloud or vendor-flexibility requirements.

Neither is a reduced version of the other; picking one is an infrastructure decision, not a
capability trade-off.

---

## Who this is for

- **Business analysts / process owners** — stop starting every SOP from a blank page.
- **Enterprise & solution architects** — design documents that stay current because regenerating one
  is cheap enough to actually do after every change.
- **Cloud architects / FinOps teams** — architecture and cost estimate produced together, from the
  same source of truth, instead of two teams working from two different drafts days apart.
- **Compliance, audit, and governance functions** — documentation with built-in traceability and
  governance sections by default, not retrofitted before an audit.
- **Consulting and delivery practices** — compress the billable-but-low-margin "first draft"
  phase of an engagement, freeing senior time for the judgment calls clients are actually paying for.

---

## Bottom line

The expensive part of enterprise documentation was never the expertise — it's the hours spent
getting from a blank page to something an expert can actually review. This agent suite collapses
that gap from days to minutes, for four of the most common and most neglected document types in any
mid-to-large organization, while adding compliance checking, performance simulation, and
cost-grounding that most manually-produced versions skip entirely.
