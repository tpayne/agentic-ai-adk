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
from process_toolkit.docgen.vsdx_export import build_cloudarch_vsdx, build_process_design_vsdx
from process_toolkit.itsm.simulation import simulate_itsm_risk_and_coverage as _simulate_itsm_risk_and_coverage
from process_toolkit.drawio.persistence import load_drawio_xml as _load_drawio_xml, reset_drawio_xml as _reset_drawio_xml
from process_toolkit.cloudarch.simulation import simulate_cloudarch_architecture as _simulate_cloudarch_architecture
from process_toolkit.cloudarch.attack_simulation import simulate_cloudarch_attack as _simulate_cloudarch_attack
from process_toolkit.cloudarch.finops import estimate_cloudarch_finops as _estimate_cloudarch_finops
from process_toolkit.schema.master_json import load_master_json as _load_master_json
from process_toolkit.schema.subprocess_json import save_subprocess_flow as _save_subprocess_flow
from process_toolkit.iac.generation import save_iac_files as _save_iac_files
from process_toolkit.feedback.iteration_feedback import (
    load_iteration_feedback as _load_iteration_feedback,
    save_iteration_feedback as _save_iteration_feedback,
    reset_approval_state as _reset_approval_state,
    reset_feedback_channels as _reset_feedback_channels,
    format_review_status_summary as _format_review_status_summary,
)
from process_toolkit.agentic_web import (
    get_agent_card as _get_agent_card,
    get_agent_manifest as _get_agent_manifest,
    get_all_workflows as _get_all_workflows,
    get_artifact_contract as _get_artifact_contract,
    get_workflow as _get_workflow,
    list_all_artifact_contracts as _list_all_artifact_contracts,
    search_capabilities as _search_capabilities,
    wrap_artifact_envelope as _wrap_artifact_envelope,
)

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
    and "itsm"'s diagrams are per-section and rendered inline by
    generate_document instead; requirements/proposal_response/
    test_specification have no diagram at all). Returns {"message": ...,
    "diagram": null} rather than fabricating a diagram when the schema_type
    has none."""
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
def export_process_design_vsdx(schema_type: str, session_id: Optional[str] = None) -> dict:
    """On-demand Visio (.vsdx) export of the whole-document flow/
    architecture diagram for `schema_type` ("design" or "process" only --
    same has_diagram gate as generate_diagram, since there is nothing to
    export for a schema_type with no whole-document diagram at all).
    Unlike generate_diagram/generate_document, this never runs as part of
    any generate/review pipeline -- it's a standalone action an MCP client
    calls explicitly. Returns {"message": ..., "vsdx": null} when the
    schema_type has no diagram, or when the underlying export itself
    reports an error (its own message, prefixed "ERROR:", is still
    returned either way for the caller to relay)."""
    ops = _domain_or_error(schema_type)
    if not ops.has_diagram:
        return {
            "message": f"NOT_APPLICABLE: '{schema_type}' has no whole-document diagram to export.",
            "vsdx": None,
        }
    with _session(session_id):
        directory = paths.output_dir()
        before = _snapshot_mtimes(directory, ".vsdx")
        message = build_process_design_vsdx(schema_type)
        changed = _new_or_changed(before, directory, ".vsdx")
        vsdx = _encode_file(os.path.join(directory, changed[0])) if changed else None
    return {"message": message, "vsdx": vsdx}


@mcp.tool
def export_cloudarch_vsdx(session_id: Optional[str] = None) -> dict:
    """On-demand Visio (.vsdx) export of the currently saved cloud-
    architecture diagram (load_drawio's own cloudarch_drawio.xml) for
    `session_id`. Standalone -- never runs as part of any cloudarch
    pipeline. Returns {"message": ..., "vsdx": null} when nothing has
    been generated yet, or on export failure (the message itself,
    prefixed "ERROR:", is still returned either way)."""
    with _session(session_id):
        directory = paths.output_dir()
        before = _snapshot_mtimes(directory, ".vsdx")
        message = build_cloudarch_vsdx()
        changed = _new_or_changed(before, directory, ".vsdx")
        vsdx = _encode_file(os.path.join(directory, changed[0])) if changed else None
    return {"message": message, "vsdx": vsdx}


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


@mcp.tool
def load_drawio(session_id: Optional[str] = None) -> dict:
    """Returns the currently saved cloud-architecture diagram's XML for
    `session_id` -- {"status": "NOT_FOUND"|"OK"|"ERROR", "xml": str|None}."""
    with _session(session_id):
        return _load_drawio_xml()


@mcp.tool
def reset_drawio(session_id: Optional[str] = None) -> dict:
    """Removes any saved cloud-architecture diagram (plus its concurrency-
    lock/debug-dump siblings) for `session_id`, so a session's first touch
    of the cloudarch subsystem never inherits a diagram a different,
    unrelated session left behind."""
    with _session(session_id):
        _reset_drawio_xml()
    return {"status": "OK"}


@mcp.tool
def simulate_architecture(xml_content: Optional[str] = None, session_id: Optional[str] = None) -> str:
    """Runs the cloud-architecture resilience/scalability/latency
    simulation. `xml_content` defaults to the session's currently saved
    diagram (via load_drawio) when omitted. Returns a JSON-encoded string
    (not a dict) -- matching process_toolkit.cloudarch.simulation's own
    return type exactly, including its own {"error": ...} shape on
    failure (this tool never raises for a missing diagram/bad input)."""
    with _session(session_id):
        return _simulate_cloudarch_architecture(xml_content)


@mcp.tool
def simulate_attack(xml_content: Optional[str] = None, session_id: Optional[str] = None) -> str:
    """Runs the cloud-architecture attack-path simulation (unauthenticated
    access, lateral movement, privilege escalation, data exfiltration,
    credential compromise). Same xml_content/return-shape contract as
    simulate_architecture."""
    with _session(session_id):
        return _simulate_cloudarch_attack(xml_content)


@mcp.tool
def estimate_finops(xml_content: Optional[str] = None, session_id: Optional[str] = None) -> str:
    """Estimates cloud-architecture cost and optimization opportunities.
    Same xml_content/return-shape contract as simulate_architecture."""
    with _session(session_id):
        return _estimate_cloudarch_finops(xml_content)


@mcp.tool
def simulate_itsm_risk(session_id: Optional[str] = None) -> dict:
    """Runs the ITSM structural risk/coverage analysis over the session's
    currently saved itsm_data.json -- role-concentration bottlenecks,
    missing incident escalation paths, SLA entries missing a measurement
    window, configuration items with an outsized blast radius, and
    process areas with no RACI governance entry. Not a timing simulation
    -- itsm_data.json has no duration/date fields to model one from, by
    design."""
    with _session(session_id):
        return _simulate_itsm_risk_and_coverage()


@mcp.tool
def save_iac(files: dict[str, str], session_id: Optional[str] = None) -> dict:
    """Persists the complete set of Infrastructure-as-Code files
    ({relative_filename: content}) for `session_id`, overwriting any
    previous IaC generation for this session first. Returns
    {sanitized_relative_filename: ...} -- the server-side path itself
    isn't meaningful to a remote caller, so this returns just the
    sanitized filenames (process_interface's own save_iac_files mirrors
    the same content locally too, since it already has it in hand)."""
    with _session(session_id):
        written = _save_iac_files(files)
    return {"files_written": sorted(written.keys())}


@mcp.tool
def load_master_json(schema_type: Optional[str] = None, session_id: Optional[str] = None) -> dict:
    """Generic reader for whichever of design_data.json/process_data.json
    exists for `session_id` -- `schema_type` ("design"|"process") reads
    exactly that file; omitted, it auto-detects by most-recently-modified.
    Equivalent to load_context("design"/"process") when schema_type is
    given explicitly; this tool exists for the auto-detect case only
    load_master_json itself supports."""
    with _session(session_id):
        return _load_master_json(schema_type)


@mcp.tool
def save_subprocess_flow(step_name: str, flow: dict, session_id: Optional[str] = None) -> dict:
    """Persists a generated subprocess flow for one parent-process step
    (output/<session_id>/subprocesses/<safe_name>.json). Returns
    {"status": "OK"|"ERROR", ...} -- never raises for invalid input,
    matching process_toolkit's own contract."""
    with _session(session_id):
        return _save_subprocess_flow(step_name, flow)


@mcp.tool
def load_feedback(reset_data: bool = True, channel: str = "", session_id: Optional[str] = None) -> dict:
    """Reads the named review-feedback mailbox for `session_id`, then
    drains it (unless reset_data=False) so a later, unrelated read never
    sees stale content. channel="" is the single unchanneled mailbox most
    pipelines use; named channels (e.g. "compliance", "simulation") let
    multiple reviewers in the same pipeline keep separate mailboxes."""
    with _session(session_id):
        return _load_iteration_feedback(reset_data=reset_data, channel=channel)


@mcp.tool
def save_feedback(feedback_data: Any, channel: str = "", session_id: Optional[str] = None) -> dict:
    """Normalizes a reviewer's payload, updates the cumulative approval
    state for any approval marker found in it, and writes the mailbox for
    `session_id`/`channel`."""
    with _session(session_id):
        message = _save_iteration_feedback(feedback_data, channel=channel)
    return {"message": message, "success": message.startswith("SUCCESS")}


@mcp.tool
def reset_approval_state(session_id: Optional[str] = None) -> dict:
    """Clears stale approval/stop-counter state left over from an earlier,
    unrelated pipeline run for `session_id`. Call once before a fresh
    generate/review loop starts."""
    with _session(session_id):
        _reset_approval_state()
    return {"status": "OK"}


@mcp.tool
def reset_feedback_channels(session_id: Optional[str] = None) -> dict:
    """Clears every known feedback mailbox for `session_id` left over from
    an earlier, unrelated pipeline run."""
    with _session(session_id):
        _reset_feedback_channels()
    return {"status": "OK"}


@mcp.tool
def review_status_summary(channels: Optional[list[str]] = None, session_id: Optional[str] = None) -> str:
    """Deterministically renders each named channel's CURRENT mailbox
    state (APPROVED, or every open issue's own persisted text) into one
    plain-text summary for `session_id`, without draining any mailbox.
    channels defaults to process_toolkit's own default
    ("compliance", "simulation") when omitted."""
    with _session(session_id):
        if channels is None:
            return _format_review_status_summary()
        return _format_review_status_summary(channels)


@mcp.tool
def get_agent_manifest(base_url: str = "") -> dict:
    """Returns ProcessEngineering's own agent discovery manifest (this project's own
    Agent Discovery API, not an implementation of the external "Open Agentic Web"
    standard)."""
    return _get_agent_manifest(base_url=base_url)


@mcp.tool
def list_agents(
    query: Optional[str] = None,
    category: Optional[str] = None,
    artifact: Optional[str] = None,
    agent_type: Optional[str] = None,
) -> list[dict]:
    """Lists machine-readable Agent Cards for all specialist networks."""
    return _search_capabilities(
        query=query,
        category=category,
        artifact=artifact,
        agent_type=agent_type,
    )


@mcp.tool
def get_agent_card(name: str) -> dict:
    """Returns detailed Agent Card metadata for a specialist agent by name."""
    card = _get_agent_card(name)
    if card is None:
        raise ToolError(f"No agent card found for '{name}'")
    return card


@mcp.tool
def list_workflows() -> list[dict]:
    """Lists all published engineering lifecycle workflows."""
    return _get_all_workflows()


@mcp.tool
def get_workflow(workflow_name: str) -> dict:
    """Returns a specific engineering lifecycle workflow definition."""
    wf = _get_workflow(workflow_name)
    if wf is None:
        raise ToolError(f"No workflow definition found for '{workflow_name}'")
    return wf


@mcp.tool
def list_artifact_contracts() -> list[dict]:
    """Lists all standardized artifact contracts across the platform."""
    return _list_all_artifact_contracts()


@mcp.tool
def get_artifact_contract(artifact_type: str) -> dict:
    """Returns a specific standardized artifact contract schema."""
    contract = _get_artifact_contract(artifact_type)
    if contract is None:
        raise ToolError(f"No artifact contract found for '{artifact_type}'")
    return contract


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
