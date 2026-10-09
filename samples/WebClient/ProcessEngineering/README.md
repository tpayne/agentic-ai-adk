# Process Architect — Web Client

A small, static, backend-agnostic chat UI for the Process Architect REST API. No build step, no
framework, no server-side code of its own — open `public/index.html` (or serve the `public/`
directory) in a browser, point it at a running backend, and chat.

It works against **either** ProcessEngineering backend, unmodified, because both now expose the
*exact same* REST contract:

| Backend | Where | How to start it (non-colliding ports, HTTP for local testing) |
|---|---|---|
| ADK (Google ADK) | `samples/GCP/ProcessEngineering` | `python -m process_agents.agent -d --http -p 8080` |
| neuro-san | `samples/Neurosan/ProcessEngineering` | `uv run python cli.py -d --flask --http -p 8081` |

(Both default to HTTPS on port 443 with no flags — `--http -p <port>` above is just a
convenient, non-privileged way to run either, or both side by side, for local testing.
`--http` serves plain HTTP so there's no self-signed-certificate browser warning to click
through; the **ADK**/**Neuro-SAN** presets in the sidebar point at exactly these two ports.)

Both expose:

```
GET    /status                  -> {"status": "live"}
POST   /chat                    {"query": "...", "session_id": "..." (optional)}
                                 -> {"status": "ok", "session_id": "...", "query": "...", "response": "..."}
POST   /chat/stream              same body; text/event-stream of progress/delta/done events instead
DELETE /chat/<session_id>       -> {"status": "ok", "session_id": "...", "cleared": true|false}
GET    /artifacts/<name>        "process" or "design" -> {"status": "ok", "name": "...",
                                 "data": {...the parsed output/<name>_data.json...}}, or 404 if
                                 that pipeline hasn't produced one yet
```

Same request/response shapes, same `Authorization: Bearer <key>` / `X-API-Key` auth header
convention, same rate-limiting and loopback-only-unless-authenticated posture. This page doesn't
know or care which one it's talking to — it just needs a Base URL.

## Running it

Pick any of these — all serve the same three static files:

```bash
# From this directory:
cd samples/WebClient/ProcessEngineering/public

# Option 1: Python's built-in static server (no dependencies)
python3 -m http.server 5500
# then open http://localhost:5500

# Option 2: open the file directly in a browser
open index.html          # macOS
xdg-open index.html      # Linux
```

Either way, nothing is installed and nothing talks to the network except the REST calls you make
to whichever backend Base URL you configure in the sidebar.

## Using it

1. Start a backend (see the table above) and note its URL, e.g. `https://127.0.0.1:8443`.
2. Open this client, click the **ADK** or **Neuro-SAN** preset (or type a custom URL), and click
   **Connect**. The status pill turns green once `GET /status` succeeds.
3. If the backend has an API key configured (`webApiKey` / `WEBAPIKEY` — see each backend's own
   README), paste it into the **API key** field. It's sent as `Authorization: Bearer <key>` on
   every request and is only ever stored in this browser's own `localStorage`, never anywhere
   else.
4. Type a message and press Enter to send (Shift+Enter for a line break) — see **Composing a
   message** below for the full editing toolbar. The response streams in live — a small italic
   note above the reply shows which agent/tool is currently active, and the text fills in as it's
   produced rather than appearing all at once after a long silent wait. The session id returned by
   the first event is reused automatically for every turn after that, so the conversation actually
   continues rather than starting fresh each time.
5. **+ New chat** clears the session client-side and asks the backend to drop its own server-side
   state for it (`DELETE /chat/<session_id>`) — best-effort; if the backend is unreachable at that
   moment, the client still forgets the id and starts clean either way.

## Composing a message

The message box is a rich-text editor, not a plain text field, with a small toolbar above it:

| Button | Does |
|---|---|
| **B** | Bold the selection (or what you type next) — `Ctrl`/`Cmd`+`B` also works. |
| *I* | Italicize the selection — `Ctrl`/`Cmd`+`I` also works. |
| List icon | Toggle a bullet list. Enter adds a new item while inside one; Shift+Enter still works too. |
| Download icon | **Save chat** — see below. |

The box expands automatically as you type (up to a max height, then scrolls) and supports full
multi-line input: **Enter sends**, **Shift+Enter inserts a line break** within the same message.
What you type is converted to the same lightweight markdown the agents' own replies use — so
`**bold**`/`*italic*`/bullets round-trip through the exact same renderer on both sides of the
conversation — and that markdown is what's actually sent as the backend's `query`, not raw HTML.

**Command history**: **↑**/**↓** recall previously sent messages, bash-style — press ↑ on an empty
box (or with the cursor on the first line of a multi-line draft) to step backward through what
you've sent, ↓ to step forward again. If you'd started typing something new before you began
recalling, ↓ past the newest history entry restores that unsent draft rather than leaving the box
empty. Within a multi-line draft, ↑/↓ move the cursor normally until it's actually on the first/last
line — they don't hijack ordinary cursor movement. History persists for the page session (cleared on
reload, but **not** by **+ New chat** — a message is still worth recalling even after starting a
fresh conversation) and only stores the plain text actually sent, not its rich formatting.

**Resizable box**: drag the handle in the box's bottom-right corner to resize it in either
direction — wider to see more of a long line, taller for more room to work with a longer draft.
Height still also grows automatically as you type (up to a generous cap), independent of any
manual resize; it resets to the default size on reload.

**Save chat** exports the full conversation so far (every finalized turn, not just the current one)
as a `.md` file. In Chromium-based browsers this opens a real **Save As** dialog (the File System
Access API); in browsers without it (Firefox, Safari as of this writing) it triggers a normal
file download instead — either way, you end up with a timestamped
`process-architect-chat-<date>.md` file containing the transcript.

## Streaming

Every turn is sent to `POST /chat/stream` first — the same endpoint both backends' CLIs now
expose (see each backend's own README) — and the UI updates live as `progress`/`delta`/`done`
events arrive:

- **`progress`** events ("CloudArch_Pipeline — Calling Reviewer...") show up as a small italic
  note above the reply, so a long multi-agent turn doesn't look like it's hung. Once the turn
  finishes, that note is replaced by a small collapsed **"Thinking (N steps)"** disclosure in the
  same spot — click it to expand the full list of every `progress` event seen during that turn
  (which agent/tool, and what it reported), so the trace that led to the response stays inspectable
  after the fact instead of vanishing the moment the reply lands. Collapsed by default to keep the
  transcript uncluttered; dropped entirely for a turn that had no progress events at all.
- **`delta`** events update the reply's text as it's produced. While streaming, this is rendered
  as **plain text**, deliberately not run through the markdown-lite renderer — a delta is an
  in-progress fragment (e.g. an unclosed &#96;&#96;&#96;code block&#96;&#96;&#96;), and parsing
  that as markdown mid-stream renders broken HTML far more often than it renders anything useful.
- **`done`** finalizes the reply: the complete text is rendered through the real markdown-lite
  renderer exactly once, and the copy button/timestamp are added.

While a turn is streaming, the composer's **Send** button is replaced by a red **Stop** button.
Clicking it calls `POST /chat/<session_id>/stop` on the connected backend — a **real** cancellation
of the backend's in-flight model call (see each backend's own README for the mechanics), not just
the client giving up on the connection, which on its own would NOT stop the actual turn (or its real
token cost) from running to completion regardless. The cancelled turn's own response arrives as one
final **`stopped`** event over the same connection, carrying whatever partial text/token usage had
accrued up to that point — rendered in the transcript with a muted dashed border and a small
"Stopped" badge instead of the usual timestamp, distinct from both a normal reply and an error (the
user asked for this, it isn't a failure). Any partial usage from a stopped turn is still recorded on
the **Token Usage** tab like any other turn.

If `/chat/stream` isn't reachable at all (an older backend without it, a network hiccup before the
stream even starts), the client transparently falls back to the non-streaming `POST /chat` — the
same retry-with-backoff request the very first version of this client always used — so the turn
still completes, just without the live updates. If the connection instead drops *mid-stream*
(after some text has already appeared), it is **not** silently retried, since re-sending the same
query could trigger a second, duplicate, possibly-billable model call — instead the partial text
stays on screen with an inline error appended.

## Agent Network tab

The **Agent Network** tab (next to **Chat**, with a live badge showing how many agents have been
invoked so far) builds a call graph of the session as it happens, entirely from the `origin` field
on each `progress` SSE event — no backend change was needed for this, since that field was already
part of the streaming contract (see **Streaming** above).

- **Solid arrows ("Calls into")** come from neuro-san's own dotted origin paths (e.g.
  `process_architect.cloudarch.CloudArch_Pipeline.CloudArch_Reviewer_Agent`), which already encode
  the full caller hierarchy for that network — split on `.` and rendered as a tree.
- **Dashed arrows ("Handed off to")** connect whichever node was active immediately before to the
  next one whenever control moves somewhere NOT already covered by a hierarchy edge. This is what
  makes the graph useful for the ADK backend too, whose `origin` is just a flat agent name with no
  nesting info of its own (see `_stream_chat_turn`'s own docstring) — the dashed edges are the only
  signal available there, and they still work the same way for neuro-san whenever control actually
  jumps across branches (e.g. one pipeline handing off to an unrelated one) rather than just going
  one level deeper into the same one.
- The node currently streaming pulses; its ring stops once that turn's `done`/`error` arrives.
  A node's size and the small count badge both grow with how many times it's been invoked.

**Click any node** to open a detail panel: the node's full path, which backend/session it belongs
to, total invocation count, and a reverse-chronological list of every recorded invocation — each
with its timestamp, the progress text seen at that moment, and the user query that triggered it.
This is the "debugging a chat session" view: if an agent did something unexpected, click it and see
exactly when, how many times, and in response to what.

**Zoom and pan** for larger graphs: the **+**/**−** buttons and the reset-view button in the
bottom-right corner, the mouse wheel, and click-and-drag all work. The view auto-fits the whole
graph by default and keeps re-fitting as new nodes stream in — the moment you manually zoom or
drag, that stops (your view is left alone) until you hit reset, which snaps back to auto-fitting
everything again.

The graph (and its detail data) is scoped to the current session — **+ New chat** clears it along
with the transcript, and switching Base URL/API key without starting a new chat does not retroactively
relabel anything already recorded.

## Process / Design tab

The **Process / Design** tab is a read-only, hierarchical viewer for whichever pipeline's current
output the connected backend has on disk — `output/process_data.json` or `output/design_data.json`
— fetched via the new `GET /artifacts/<name>` endpoint above. Unlike the Chat and Agent Network
tabs (built entirely from data already flowing over the streaming contract), this one needed a new
backend route, since the web client is a static page with no filesystem access of its own: both
backends serve it identically, deliberately as a raw file read rather than reusing each project's
own `load_master_process_json`/`load_master_design_json` helpers, which silently fall back to a
blank template when the file is missing — this tab needs a real 404 to tell "genuinely not
generated yet" apart from "here's an empty template".

- The **Process**/**Design** toggle picks which artifact to load; the icon-only refresh button
  (top-right of the toolbar, next to the toggle) re-fetches the currently selected one on demand —
  this tab never auto-refreshes on its own, since the underlying file only changes when a pipeline
  run finishes, not on any predictable schedule the client could poll against.
- The tree starts at the root, top-left, with children expanding down and to the right as you open
  them — click the small arrow to expand or collapse a node; this state is tracked per JSON path
  (e.g. `$.process_steps[2].substeps[0]`) and preserved across re-renders within the same load.
- **Click a row** (not just its arrow) to open a detail panel showing that node's own direct
  properties — for an object, its immediate fields with each one's type and a short preview; for an
  array, its items the same way; for a primitive, the full value. It deliberately does NOT dump
  everything nested below the clicked node — that's what expanding (or clicking into) a child row
  is for.
- Switching the artifact, or hitting refresh, clears any open detail panel and resets the tree back
  to just the root expanded, since an expand/selection state built against one artifact's shape has
  no guaranteed correspondence to the other's (or to a re-run pipeline's updated shape).
- Built the same way as the Agent Network graph: DOM nodes via `document.createElement`/
  `.textContent`, never `innerHTML` string concatenation, since the JSON being rendered is arbitrary
  backend output and could contain HTML-like strings.

## Token Usage tab

The **Token Usage** tab charts token usage per turn as the conversation moves on, and estimates
what it cost. Every `/chat`/`/chat/stream` response from either backend now carries a `"usage"`
field:

```json
{"prompt_tokens": 1234, "completion_tokens": 567, "total_tokens": 1801, "model": "gemini-3.8-flash"}
```

(or `null` for a turn that made no LLM calls) -- see each backend's own README for exactly how it's
computed there; the two arrive at the same shape very differently (ADK accumulates real
`usage_metadata` off the event stream itself; neuro-san surfaces its own built-in, already-aggregated
token accounting), but the client doesn't need to know which one it's talking to.

- **One bar per turn**, height = that turn's own `total_tokens` -- NOT a running cumulative total,
  so the chart genuinely rises and falls turn to turn, with a thin dashed trend line connecting each
  bar's peak. A bar is colored **green** (light), **amber** (moderate), or **red** (heavy) by fixed
  thresholds on that turn's token count (2,000 / 8,000 by default -- see `USAGE_THRESHOLDS` in
  `app.js` if your own usage patterns call for different cutoffs). Fixed, not relative to the
  session's own range, so "red" means roughly the same thing from one conversation to the next
  rather than always being whatever the single biggest turn so far happened to be.
- **Narrow, tightly-packed, left-justified bars** -- a fixed per-bar width/gap, not stretched to fill
  the canvas, so the chart reads as a graph rather than a handful of wide step-diagram blocks. The
  content starts at the left edge and simply grows wider as more turns arrive (same philosophy as the
  Agent Network graph's own "natural size" layout) -- it does not re-flow or shrink existing bars to
  keep fitting the visible width.
- **Zoom and pan**, identical to the Agent Network tab: the **+**/**−**/reset-view buttons in the
  bottom-right corner, the mouse wheel, and click-and-drag all work. The view auto-fits (anchored to
  the left, not centered) by default and keeps re-fitting as new turns stream in; manually zooming or
  dragging stops that until Reset is clicked.
- **Click a bar** for that turn's exact breakdown (prompt/completion/total tokens, estimated cost,
  reported model, the query that triggered it) in the same detail-panel pattern as the Agent Network
  and Process/Design tabs.
- **Model**, shown read-only above the chart, is never picked manually -- it's whatever the connected
  backend itself reports: `GET /status`'s `model` field for the ADK original's one static model, or a
  turn's own `usage.model` for neuro-san (which can genuinely invoke different models turn to turn,
  since its own token accounting reports the real model(s) actually used). The backend's own config is
  the source of truth for which model ran, so there's nothing to select.
- **Estimated cost** (per turn, in its detail panel, and summed for the whole session in the stats
  bar) is computed client-side from a small built-in reference table of current public per-1M-token
  rates (`MODEL_PRICING` in `app.js`, covering the models this project's own `properties`/`config`
  files are actually set up to use -- Gemini 3.x Flash, Gemini 2.5 Flash/Pro, Claude Sonnet
  5/Opus 4.8/Haiku 4.5, GPT-4o, Bedrock Claude Sonnet 4.5 -- checked against each provider's own
  pricing page as of 2026-10), looked up by the auto-detected model above. An exact match isn't
  required -- a reported model string that's a more specific/versioned variant of a table entry (e.g.
  a backend reporting `gemini-3.8-flash-002`) still resolves via a prefix match (`findPricingByModelName`
  in `app.js`) rather than silently showing nothing. Only shows `—` (with a tooltip naming the
  unmatched model) when nothing in the table is even a prefix match, rather than guessing a
  possibly-wrong price. Clearly an *estimate* either way: pricing pages change, promotional rates
  expire, and the table may not match a negotiated/enterprise rate.
- The chart (and the detected model) is scoped to the current session -- **+ New chat** clears the
  turn history the same way it clears the Agent Network graph.

## Why CORS just works

This is a page served from one origin (`file://`, or whatever host serves `public/`) calling a
REST API on another (the backend's own host:port) — normally a CORS problem. Both backends'
`build_web_app` now reflect the request's `Origin` header on every response (including the
preflight `OPTIONS` request this page's browser sends automatically) rather than requiring a
server-side allowlist, since neither backend uses cross-origin cookies for authentication: this
client always sends the session id explicitly in the `POST /chat` body instead, so there's no
credential being carried cross-origin for a permissive CORS policy to leak.

## Design notes

- **No external dependencies.** No CDN fonts, no bundled chat/markdown library — the small
  markdown-lite renderer in `app.js` (bold/italic/inline code/code blocks/links/lists/headings) is
  self-contained, so the page keeps working with no internet access beyond the REST calls
  themselves.
- **Retry with backoff.** Used for the `/chat` fallback path (see Streaming above): a request that
  fails with a transient network error or a `429`/`502`/`503`/`504` is retried automatically (up to
  2 extra attempts, exponential backoff) — a `400`/`401` is not retried, since retrying the exact
  same malformed/unauthenticated request won't change the outcome.
- **Not `EventSource`.** The browser's native `EventSource` API is GET-only and can't send custom
  headers, so there'd be no way to attach `Authorization`/`X-API-Key` to a streamed request when an
  API key is configured. `app.js` instead reads `/chat/stream`'s response body directly via
  `fetch()` + `ReadableStream`, parsing the same `data: {...}\n\n` framing SSE uses by hand — same
  wire format, just read manually instead of through `EventSource`.
- **Light/dark theme**, following the OS preference by default, with a manual override saved
  locally.
- **Responsive** — the sidebar collapses behind a menu button below ~860px wide.

## Known limitations

- This talks to one backend session at a time. Switching the Base URL or API key does not
  automatically end the previous backend's session server-side — click **+ New chat** first if you
  want the old one cleaned up before switching.
- The markdown-lite renderer intentionally only covers the common constructs the agents' own
  responses actually use (see above) — it is not a full CommonMark implementation (no tables,
  nested blockquotes, etc.).
