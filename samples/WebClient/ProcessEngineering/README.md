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
  note above the reply, so a long multi-agent turn doesn't look like it's hung.
- **`delta`** events update the reply's text as it's produced. While streaming, this is rendered
  as **plain text**, deliberately not run through the markdown-lite renderer — a delta is an
  in-progress fragment (e.g. an unclosed &#96;&#96;&#96;code block&#96;&#96;&#96;), and parsing
  that as markdown mid-stream renders broken HTML far more often than it renders anything useful.
- **`done`** finalizes the reply: the complete text is rendered through the real markdown-lite
  renderer exactly once, and the copy button/timestamp are added.

If `/chat/stream` isn't reachable at all (an older backend without it, a network hiccup before the
stream even starts), the client transparently falls back to the non-streaming `POST /chat` — the
same retry-with-backoff request the very first version of this client always used — so the turn
still completes, just without the live updates. If the connection instead drops *mid-stream*
(after some text has already appeared), it is **not** silently retried, since re-sending the same
query could trigger a second, duplicate, possibly-billable model call — instead the partial text
stays on screen with an inline error appended.

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
