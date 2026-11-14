# ProcessToolkitServer

A standalone [FastMCP](https://gofastmcp.com) server that exposes
`shared/process_toolkit`'s document, diagram, and workbook generation to MCP
clients outside this repo's two agent apps (`samples/Neurosan/ProcessEngineering`,
`samples/GCP/ProcessEngineering`).

**This is not used by either of those two agent apps.** They keep calling
`process_toolkit` in-process through their own `coded_tools`/`process_agents`
wrapper code, as before. This server is a separate integration surface for a
third-party MCP client that wants the same document/diagram/workbook
generation without being either of those agent apps.

## What it exposes

`process_toolkit` validates and persists a JSON "baseline" per artifact type,
then renders that baseline into a `.docx`/`.png`/`.xlsx`. This server exposes
that same shape as a small, `schema_type`-parameterized tool set rather than
one tool per domain per operation:

| Tool | Purpose |
| --- | --- |
| `list_schema_types()` | The `schema_type` values every other tool accepts: `design`, `togaf`, `process`, `requirements`, `proposal_response`, `test_specification`. |
| `load_template(schema_type)` | The blank/example JSON shape for that domain. |
| `load_context(schema_type, session_id?)` | The currently saved JSON for that domain within a session (or the template, if nothing saved yet). |
| `validate_json(schema_type, data)` | Structural validation only -- `{"valid": bool, "issues": [...]}`. Never checks factual correctness. |
| `persist_json(schema_type, data, session_id?)` | Validates, then writes `data` as the domain's baseline. |
| `generate_document(schema_type, session_id?, variant?, process_name?)` | Renders the Word document(s) from the persisted baseline. `variant` matters only for `design` (`"hld"\|"lld"\|"both"`) and `togaf` (`"vision"\|"definition"\|"both"`). Returns the produced file(s) as base64. |
| `generate_diagram(schema_type, session_id?)` | Renders the whole-document flow/architecture diagram -- only meaningful for `design` and `process`. Every other `schema_type` returns `{"diagram": null}` with a `NOT_APPLICABLE` message rather than fabricating one. |
| `generate_portfolio_backlog(backlog, session_id?)` | Saves an Enterprise Agile Portfolio Backlog and renders its Excel workbook in one call (this domain validates and renders together, unlike every other `schema_type`). |
| `load_portfolio_backlog_json(session_id?)` | The currently saved portfolio backlog JSON. |
| `list_artifacts(session_id?)` | Every generated file currently on disk for a session. |
| `get_artifact(filename, session_id?)` | One artifact, as base64 -- since an external MCP client has no shared filesystem with this server. |

`togaf`'s diagrams are rendered per-section, inline inside `generate_document`
itself -- there's no single whole-document diagram to ask for separately, so
`generate_diagram("togaf", ...)` reports `NOT_APPLICABLE` rather than an
error. Same for `requirements`/`proposal_response`/`test_specification`, which
have no diagram at all.

### Session isolation

Every stateful tool takes an optional `session_id`. Concurrent callers using
different `session_id` values never see each other's generated files --
internally this wraps each call in `process_toolkit.paths.use_session(...)`,
the same mechanism both agent apps use for their own concurrent chat sessions.
Omitting `session_id` resolves to a single shared `"default"` session.

## Running the server

```bash
uv sync
uv run python server.py                        # Streamable HTTP on http://0.0.0.0:8765/mcp
uv run python server.py --transport stdio       # stdio, for a client that launches this as a subprocess
uv run python server.py --ssl-certfile cert.pem --ssl-keyfile key.pem   # HTTPS -- see below
```

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROCESS_TOOLKIT_MCP_OUTPUT_DIR` | `<this dir>/output` | Absolute root every generated artifact is written under. |
| `PROCESS_TOOLKIT_MCP_HOST` | `0.0.0.0` | Streamable HTTP bind host. |
| `PROCESS_TOOLKIT_MCP_PORT` | `8765` | Streamable HTTP bind port. |
| `PROCESS_TOOLKIT_MCP_SSL_CERTFILE` / `_SSL_KEYFILE` | unset (plain HTTP) | Env-var equivalents of `--ssl-certfile`/`--ssl-keyfile`, below. |
| `PROCESS_TOOLKIT_MCP_SSL_KEYFILE_PASSWORD` | unset | Decrypts an encrypted private key, if needed. |
| `PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED` | `true` | Set to `false`/`0`/`no`/`off` to disable rate limiting entirely. |
| `PROCESS_TOOLKIT_MCP_RATE_LIMIT_PER_SECOND` | `5.0` | Sustained tool calls/second admitted per connecting IP. |
| `PROCESS_TOOLKIT_MCP_RATE_LIMIT_BURST` | `10` | Burst capacity on top of the sustained rate. |

### HTTPS

`--ssl-certfile`/`--ssl-keyfile` (or their env-var equivalents) terminate TLS
directly in the server process via uvicorn, the same mechanism
`samples/Neurosan/ProcessEngineering`'s own `ns run` relies on for its HTTP
layer. Both flags are required together -- passing just one is a startup
error, not a silent fallback to plain HTTP. They only apply to
`--transport http`; combining them with `--transport stdio` is also a
startup error, since stdio has no network socket to terminate TLS on.

For local testing, generate a self-signed cert (the one-liner
`tests/test_server.py`'s own `_generate_self_signed_cert` helper uses, via
Python's `cryptography` package, works too):

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -keyout key.pem -out cert.pem -subj "/CN=localhost"
uv run python server.py --ssl-certfile cert.pem --ssl-keyfile key.pem
```

For a real deployment, mount a real certificate/key pair into the container
(see the Docker section below) rather than baking one into the image.

### Rate limiting

Every tool here can trigger real disk I/O (writing a `.docx`/`.xlsx`), so an
unthrottled caller could flood the server with generation requests. Tool
calls (only -- `tools/list`/`initialize`/etc. are never throttled) are
rate-limited per connecting IP under Streamable HTTP, using a token-bucket
algorithm ([`fastmcp`'s own `RateLimitingMiddleware`](https://gofastmcp.com),
scoped down to `tools/call` only). Exceeding the limit returns a clean MCP
error ("Rate limit exceeded for client: \<ip\>"), not a crash.

This is IP-keyed, not connection- or session-keyed: FastMCP's own
`session_id` turned out to be minted fresh on every single tool call (even
under a real, already-established Streamable HTTP connection), not once per
connection, so it can't be used to recognize "the same caller" across calls.
Under stdio there's exactly one client per server process by construction,
so the whole process shares one budget there -- correct, not an
approximation, for that transport.

## Docker

The build context must be the **repo root**, not this directory, because
`pyproject.toml`'s `[tool.uv.sources]` entry for `process-toolkit` points
outside it (`../../../shared/process_toolkit`) -- mirrors
`samples/Neurosan/ProcessEngineering`'s own Dockerfile for the same reason.

```bash
# from the repo root
docker build -f samples/MCP/ProcessToolkitServer/Dockerfile -t process-toolkit-mcp .
docker run --rm -p 8765:8765 process-toolkit-mcp
```

The server is then reachable at `http://localhost:8765/mcp`. Mount a volume
over `/app/samples/MCP/ProcessToolkitServer/output` if generated artifacts
need to survive a container restart.

To serve HTTPS from the container, mount a real cert/key pair and point the
env vars at the mounted paths:

```bash
docker run --rm -p 8765:8765 \
  -v /path/to/certs:/certs:ro \
  -e PROCESS_TOOLKIT_MCP_SSL_CERTFILE=/certs/cert.pem \
  -e PROCESS_TOOLKIT_MCP_SSL_KEYFILE=/certs/key.pem \
  process-toolkit-mcp
```

## Connecting from another MCP client

Any MCP client in any language can connect to the Streamable HTTP endpoint
directly:

```
http://<host>:8765/mcp
```

Typical flow: `load_template("togaf")` -> fill in the data -> `validate_json`
-> `persist_json` -> `generate_document` -> `get_artifact` for each returned
filename (decode its `base64` field to get the real `.docx`/`.png`/`.xlsx`
bytes).

## Reference client

`client.py` is a small [fastmcp](https://gofastmcp.com) client used to prove
the server works end-to-end -- it is not meant to be the only way to consume
this server, just a worked example and the fixture this project's own
verification runs against.

```bash
uv run python server.py &                      # start the server
uv run python client.py demo                    # runs the togaf vision-document flow above
                                                 # against http://127.0.0.1:8765/mcp
uv run python client.py demo --stdio            # same demo, launching the server over stdio instead
```

The demo writes the generated `.docx` into `demo_downloads/` so you can open
it and confirm it's a real, non-empty document.

## Tests

```bash
uv run pytest
```

Three files, 79 tests total:

| File | Level | Covers |
| --- | --- | --- |
| `tests/test_server.py` | Integration (real MCP protocol) | Every tool called through `fastmcp.Client`'s in-memory transport, plus tests that start the server with `transport="http"` on an ephemeral port and connect over a real Streamable HTTP socket (both plain and TLS, the latter against a locally-generated self-signed cert) -- proving the network path itself works, not just the tool functions in isolation. |
| `tests/test_server_helpers.py` | Unit | `server.py`'s internal helpers (`_domain_or_error`, `_session`, `_snapshot_mtimes`/`_new_or_changed`, `_encode_file`, `_safe_artifact_path`, `_rate_limit_client_id`, `_rate_limiting_enabled`, `_parse_args`'s SSL-flag validation, `_uvicorn_ssl_config`) called directly as plain Python functions, plus the `ToolCallRateLimitingMiddleware` class exercised against short-lived, dedicated FastMCP instances (never the shared `server.mcp` singleton -- see `tests/conftest.py`'s own comment for why). |
| `tests/test_dispatch.py` | Unit | `dispatch.py`'s `DOMAINS` table (every domain has the right callables, variant-kwarg/diagram flags match reality) and the `_validate_then_save`/`generate_document_for` composition helpers, using stub validate/save functions rather than real domain logic. |

The unit layer caught a real bug during development: `_session`'s
`try/except` originally wrapped the *call* to `paths.use_session(session_id)`
rather than its `__enter__` -- since `use_session` is itself a
`@contextmanager`, calling it only builds the generator, so
`sanitize_session_id`'s validation (which runs on `__enter__`) raised a raw
`ValueError` straight through the MCP boundary instead of a clean
`ToolError`. `tests/test_server_helpers.py::TestSession::test_an_unsafe_session_id_raises_a_tool_error_not_a_raw_value_error`
caught it; `tests/test_server.py`'s matching regression test proves the fix
holds through the real tool-call path too.
