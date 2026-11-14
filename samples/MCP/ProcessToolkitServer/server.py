"""Standalone FastMCP server exposing shared/process_toolkit's document,
diagram, and workbook generation to MCP clients outside the Neuro-San and
ADK ProcessEngineering agent apps -- those two keep calling process_toolkit
in-process through their own coded_tools/process_agents wrappers and never
touch this server at all; this is a separate integration surface for a
third-party consumer.

Run directly for Streamable HTTP (the default -- a standing network
service any MCP client can connect to at http://<host>:<port>/mcp):

    uv run python server.py

Or over stdio, for a client that launches this as a subprocess:

    uv run python server.py --transport stdio

Or over HTTPS, by pointing at a real (or, for local testing, self-signed)
certificate/key pair -- both are required together:

    uv run python server.py --ssl-certfile cert.pem --ssl-keyfile key.pem

PROCESS_TOOLKIT_MCP_SSL_CERTFILE / _SSL_KEYFILE (optional; no default --
plain HTTP unless both are set) are the env-var equivalents of
--ssl-certfile/--ssl-keyfile, for container deployments that mount
certificates at a fixed path rather than passing CLI flags.
PROCESS_TOOLKIT_MCP_SSL_KEYFILE_PASSWORD decrypts an encrypted private key,
if needed.

PROCESS_TOOLKIT_MCP_OUTPUT_DIR (default: "<this dir>/output") sets the
absolute root every generated artifact is written under -- process_toolkit's
own paths.output_dir() otherwise defaults to a *relative*, cwd-dependent
"output", which isn't safe for a server process a caller can launch from
anywhere. PROCESS_TOOLKIT_MCP_HOST / PROCESS_TOOLKIT_MCP_PORT configure the
Streamable HTTP bind address (defaults 0.0.0.0:8765).

PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED (default: "true") / _PER_SECOND
(default: 5.0) / _BURST (default: 10) bound how fast one connecting IP can
call tools under Streamable HTTP -- every tool here can trigger real disk
I/O (writing a .docx/.xlsx), so an unthrottled third-party caller could
otherwise flood the server with generation requests. See
_rate_limit_client_id's own docstring for why this is scoped to tool calls
and keyed by connecting IP rather than any MCP-protocol session concept,
and tests/conftest.py's own comment for why the test suite disables this
entirely for the shared in-memory server.mcp instance every other test in
this project calls through.
"""

import argparse
import base64
import os
from contextlib import contextmanager
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from process_toolkit import paths
from process_toolkit.portfolio_backlog.portfolio_backlog import (
    load_portfolio_backlog as _load_portfolio_backlog,
    save_portfolio_backlog as _save_portfolio_backlog,
)
from process_toolkit.docgen.edge_inference import generate_clean_diagram

import dispatch

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.environ.get("PROCESS_TOOLKIT_MCP_OUTPUT_DIR") or os.path.join(THIS_DIR, "output")
paths.OUTPUT_DIR = os.path.abspath(DEFAULT_OUTPUT_DIR)
os.makedirs(paths.OUTPUT_DIR, exist_ok=True)

# Files process_toolkit itself writes into a session dir that are never a
# generated artifact a caller asked for -- excluded from list_artifacts so
# the catalog only ever shows real outputs.
_NON_ARTIFACT_FILENAMES = {paths.SESSION_META_FILENAME}

mcp = FastMCP("process-toolkit")


def _rate_limit_client_id(context: MiddlewareContext) -> str:
    """Keys the rate limiter by the connecting IP under Streamable HTTP --
    the only transport where multiple distinct, concurrent real clients
    actually exist. fastmcp_context.session_id looked like the right key
    at first, but isn't: confirmed directly (even against a real
    Streamable HTTP connection, not just the in-memory test transport) that
    FastMCP mints a NEW session_id on every single tool call, not once per
    connection -- keying on it would silently rate-limit nothing at all,
    since every call would always look like a brand-new client with a
    full, untouched bucket.

    Under stdio there is exactly one client per server process by
    construction, so the fallback below applies one shared budget for that
    process's whole lifetime -- correct there, not an approximation. The
    same fallback also covers this project's own in-memory test transport
    (get_http_request() has nothing to find), which is why
    tests/conftest.py disables rate limiting entirely for the shared
    server.mcp instance every other test in this project calls through --
    the actual enforcement logic is instead proven in
    tests/test_server_helpers.py against short-lived, dedicated FastMCP
    instances."""
    try:
        request = get_http_request()
    except RuntimeError:
        return "non-http-client"
    return (request.client.host if request.client else None) or "non-http-client"


class ToolCallRateLimitingMiddleware(Middleware):
    """Wraps fastmcp's own RateLimitingMiddleware, but only for tool calls.

    RateLimitingMiddleware's own on_request hook fires for every MCP
    message (initialize, tools/list, discover, ...), not just tools/call --
    throttling administrative traffic the same as the actual, disk-writing
    tool invocations isn't the intent here, so this only implements
    on_call_tool, leaving on_request at the base class's pass-through."""

    def __init__(self, **kwargs: Any) -> None:
        self._delegate = RateLimitingMiddleware(**kwargs)

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        return await self._delegate.on_request(context, call_next)


def _rate_limiting_enabled() -> bool:
    return os.environ.get("PROCESS_TOOLKIT_MCP_RATE_LIMIT_ENABLED", "true").strip().lower() not in (
        "0", "false", "no", "off",
    )


if _rate_limiting_enabled():
    mcp.add_middleware(ToolCallRateLimitingMiddleware(
        max_requests_per_second=float(os.environ.get("PROCESS_TOOLKIT_MCP_RATE_LIMIT_PER_SECOND", "5.0")),
        burst_capacity=int(os.environ.get("PROCESS_TOOLKIT_MCP_RATE_LIMIT_BURST", "10")),
        get_client_id=_rate_limit_client_id,
    ))


def _domain_or_error(schema_type: str) -> dispatch.DomainOps:
    ops = dispatch.DOMAINS.get(schema_type)
    if ops is None:
        raise ToolError(
            f"Unknown schema_type '{schema_type}'. Expected one of: {sorted(dispatch.DOMAINS)}."
        )
    return ops


@contextmanager
def _session(session_id: Optional[str]):
    # paths.use_session is itself a @contextmanager -- calling it only
    # builds the generator, it doesn't run sanitize_session_id's check
    # until __enter__ actually executes. A try/except around the call
    # (rather than around entering the `with`) would never catch
    # anything, since __enter__ happens later, inside our own caller's
    # `with _session(...):` statement -- wrapping that entry here is
    # what actually converts the raw ValueError into a ToolError.
    try:
        with paths.use_session(session_id):
            yield
    except ValueError as error:
        raise ToolError(str(error)) from error


def _snapshot_mtimes(directory: str, suffix: str) -> dict[str, float]:
    if not os.path.isdir(directory):
        return {}
    return {
        name: os.path.getmtime(os.path.join(directory, name))
        for name in os.listdir(directory)
        if name.endswith(suffix)
    }


def _new_or_changed(before: dict[str, float], directory: str, suffix: str) -> list[str]:
    after = _snapshot_mtimes(directory, suffix)
    return sorted(name for name, mtime in after.items() if before.get(name) != mtime)


def _encode_file(path: str) -> dict[str, Any]:
    with open(path, "rb") as f:
        content = f.read()
    return {
        "filename": os.path.basename(path),
        "base64": base64.b64encode(content).decode("ascii"),
        "size_bytes": len(content),
    }


def _safe_artifact_path(filename: str) -> str:
    """Mirrors the existing per-port safe_output_file_path's own guard
    (basename-only, then confirm the resolved path is really inside the
    session's output dir) -- duplicated here rather than imported, since
    that helper lives in each port's own coded_tools/process_agents
    package, not in process_toolkit itself, exactly like the two ports
    already duplicate it between each other."""
    base_dir = os.path.abspath(paths.output_dir())
    candidate = os.path.abspath(os.path.join(base_dir, os.path.basename(filename or "")))
    if not filename or not candidate.startswith(base_dir + os.sep):
        raise ToolError(f"No such artifact: {filename!r}")
    if not os.path.isfile(candidate):
        raise ToolError(f"No such artifact: {filename!r}")
    return candidate


@mcp.tool
def list_schema_types() -> list[str]:
    """Lists the schema_type values accepted by every other tool on this
    server (load_template, load_context, validate_json, persist_json,
    generate_document, generate_diagram)."""
    return sorted(dispatch.DOMAINS)


@mcp.tool
def load_template(schema_type: str) -> dict:
    """Returns the blank/example JSON shape for `schema_type`."""
    return _domain_or_error(schema_type).load_template()


@mcp.tool
def load_context(schema_type: str, session_id: Optional[str] = None) -> dict:
    """Returns the current saved JSON for `schema_type` within `session_id`
    (or the bare template if nothing has been persisted yet)."""
    ops = _domain_or_error(schema_type)
    with _session(session_id):
        return ops.load_context()


@mcp.tool
def validate_json(schema_type: str, data: dict) -> dict:
    """Structurally validates `data` against `schema_type`'s schema.
    Returns {"valid": bool, "issues": [...]}. This is a structural check
    only (required fields, stable ids, non-empty acceptance criteria,
    etc.) -- it does not and cannot check whether the content is
    factually correct."""
    ops = _domain_or_error(schema_type)
    return ops.validate(data)


@mcp.tool
def persist_json(schema_type: str, data: dict, session_id: Optional[str] = None) -> dict:
    """Validates then writes `data` as the baseline JSON for `schema_type`
    within `session_id`. For requirements/proposal_response/
    test_specification -- which have no native "persist only if valid"
    step in process_toolkit itself -- this server composes validate_json
    and the domain's own save function at this boundary instead, so every
    schema_type gets the same contract here even though process_toolkit's
    own save_* for those three stays intentionally unvalidated."""
    ops = _domain_or_error(schema_type)
    with _session(session_id):
        message = ops.persist(data)
    return {"message": message, "success": message.startswith("SUCCESS")}


@mcp.tool
def generate_document(
    schema_type: str,
    session_id: Optional[str] = None,
    variant: Optional[str] = None,
    process_name: str = "Process",
) -> dict:
    """Generates the Word document(s) for `schema_type` from its currently
    persisted JSON (call persist_json first). `variant` only matters for
    "design" ("hld"|"lld"|"both") and "togaf" ("vision"|"definition"|
    "both") -- ignored for every other schema_type. Returns the produced
    file(s) as base64, since an external MCP client has no shared
    filesystem with this server."""
    _domain_or_error(schema_type)
    with _session(session_id):
        directory = paths.output_dir()
        before = _snapshot_mtimes(directory, ".docx")
        message = dispatch.generate_document_for(schema_type, process_name, variant)
        changed = _new_or_changed(before, directory, ".docx")
        documents = [_encode_file(os.path.join(directory, name)) for name in changed]
    return {"message": message, "documents": documents}


@mcp.tool
def generate_diagram(schema_type: str, session_id: Optional[str] = None) -> dict:
    """Generates the whole-document flow/architecture diagram for
    `schema_type` (meaningful for "design" and "process" only -- "togaf"'s
    diagrams are per-section and rendered inline by generate_document
    instead; requirements/proposal_response/test_specification have no
    diagram at all). Returns {"message": ..., "diagram": null} rather than
    fabricating a diagram when the schema_type has none."""
    ops = _domain_or_error(schema_type)
    if not ops.has_diagram:
        return {
            "message": f"NOT_APPLICABLE: '{schema_type}' has no whole-document diagram to generate.",
            "diagram": None,
        }
    with _session(session_id):
        directory = paths.output_dir()
        before = _snapshot_mtimes(directory, ".png")
        message = generate_clean_diagram(schema_type)
        changed = _new_or_changed(before, directory, ".png")
        diagram = _encode_file(os.path.join(directory, changed[0])) if changed else None
    return {"message": message, "diagram": diagram}


@mcp.tool
def generate_portfolio_backlog(backlog: dict, session_id: Optional[str] = None) -> dict:
    """Saves `backlog` (the Enterprise Agile Portfolio Backlog JSON shape)
    and renders its Excel workbook in one call -- mirrors
    process_toolkit's own save_portfolio_backlog, which validates and
    renders together rather than as separate steps, unlike every other
    schema_type on this server."""
    with _session(session_id):
        directory = paths.output_dir()
        message = _save_portfolio_backlog(backlog, None)
        workbook = None
        if message.startswith("SUCCESS"):
            for name in os.listdir(directory):
                if name.endswith(".xlsx"):
                    workbook = _encode_file(os.path.join(directory, name))
                    break
    return {"message": message, "workbook": workbook}


@mcp.tool
def load_portfolio_backlog_json(session_id: Optional[str] = None) -> dict:
    """Returns the currently saved Enterprise Agile Portfolio Backlog JSON
    for `session_id` (status "NOT_FOUND" if nothing has been generated
    yet)."""
    with _session(session_id):
        return _load_portfolio_backlog(None)


@mcp.tool
def list_artifacts(session_id: Optional[str] = None) -> list[dict]:
    """Lists every generated artifact currently on disk for `session_id`
    (filename, size_bytes, modified_at), independent of which tool
    produced it."""
    with _session(session_id):
        directory = paths.output_dir()
        entries = []
        for name in sorted(os.listdir(directory)):
            if name in _NON_ARTIFACT_FILENAMES:
                continue
            full_path = os.path.join(directory, name)
            if not os.path.isfile(full_path):
                continue
            entries.append({
                "filename": name,
                "size_bytes": os.path.getsize(full_path),
                "modified_at": os.path.getmtime(full_path),
            })
        return entries


@mcp.tool
def get_artifact(filename: str, session_id: Optional[str] = None) -> dict:
    """Returns one artifact from `session_id`'s output directory as
    base64, by filename as reported by list_artifacts/generate_document/
    generate_diagram/generate_portfolio_backlog."""
    with _session(session_id):
        return _encode_file(_safe_artifact_path(filename))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default=os.environ.get("PROCESS_TOOLKIT_MCP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PROCESS_TOOLKIT_MCP_PORT", "8765")))
    parser.add_argument(
        "--ssl-certfile", default=os.environ.get("PROCESS_TOOLKIT_MCP_SSL_CERTFILE"),
        help="Serve over HTTPS using this certificate. Requires --ssl-keyfile too.",
    )
    parser.add_argument(
        "--ssl-keyfile", default=os.environ.get("PROCESS_TOOLKIT_MCP_SSL_KEYFILE"),
        help="Private key for --ssl-certfile. Requires --ssl-certfile too.",
    )
    args = parser.parse_args()

    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        parser.error("--ssl-certfile and --ssl-keyfile must be given together, not just one.")
    if args.transport == "stdio" and (args.ssl_certfile or args.ssl_keyfile):
        parser.error("--ssl-certfile/--ssl-keyfile only apply to --transport http (stdio has no network socket).")
    return args


def _uvicorn_ssl_config(args: argparse.Namespace) -> dict[str, Any]:
    if not args.ssl_certfile:
        return {}
    config: dict[str, Any] = {"ssl_certfile": args.ssl_certfile, "ssl_keyfile": args.ssl_keyfile}
    keyfile_password = os.environ.get("PROCESS_TOOLKIT_MCP_SSL_KEYFILE_PASSWORD")
    if keyfile_password:
        config["ssl_keyfile_password"] = keyfile_password
    return config


if __name__ == "__main__":
    args = _parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="http", host=args.host, port=args.port,
            uvicorn_config=_uvicorn_ssl_config(args),
        )
