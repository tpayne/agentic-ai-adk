"""Sync-callable bridge to the ProcessToolkitServer FastMCP server.

Every consumer in both agent apps calls process_interface functions
synchronously (neuro-san CodedTool.invoke(), ADK tool functions), but
fastmcp.Client is async. Rather than asyncio.run(...) a fresh event loop
and a fresh connection per call (correct but slow, and asyncio.run()
cannot be called from a thread that already has a running loop -- both
agent apps may call into this from an async context), this module owns one
background thread with its own long-lived event loop, and one long-lived
Client connected on that loop, reused across calls via
run_coroutine_threadsafe(...).result(timeout).
"""

import asyncio
import threading
from typing import Any, Optional

from fastmcp import Client

from process_interface import config

_lock = threading.Lock()
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_client: Optional[Client] = None
_client_url: Optional[str] = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    if _loop is not None and _loop.is_running():
        return _loop

    ready = threading.Event()

    def _run() -> None:
        global _loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _loop = loop
        ready.set()
        loop.run_forever()

    _loop_thread = threading.Thread(target=_run, name="process-interface-mcp-loop", daemon=True)
    _loop_thread.start()
    ready.wait()
    assert _loop is not None
    return _loop


async def _get_connected_client(url: str) -> Client:
    global _client, _client_url
    if _client is not None and _client_url == url and _client.is_connected():
        return _client

    if _client is not None:
        try:
            await _client.close()
        except Exception:
            pass  # best-effort -- a dead/stale connection isn't worth failing over

    client = Client(url)
    await client.__aenter__()
    _client = client
    _client_url = url
    return _client


async def _call_async(tool_name: str, arguments: dict[str, Any], url: str) -> Any:
    client = await _get_connected_client(url)
    try:
        result = await client.call_tool(tool_name, arguments)
    except Exception:
        # One reconnect-and-retry, in case the server restarted or the
        # connection went stale between calls -- a long-lived process
        # making many calls over time shouldn't need a manual restart
        # just because the server bounced once.
        global _client
        _client = None
        client = await _get_connected_client(url)
        result = await client.call_tool(tool_name, arguments)
    return result.data


def call(tool_name: str, arguments: Optional[dict[str, Any]] = None) -> Any:
    """Synchronously calls `tool_name` on the configured MCP server and
    returns its structured `.data`. Raises process_interface.config.
    ProcessInterfaceConfigError if no MCP URL is configured."""
    # config.resolve() itself already raises ProcessInterfaceConfigError if
    # mode=="mcp" with no URL set -- resolved.mcp_url is guaranteed non-None
    # past this point, nothing further to check here.
    resolved = config.resolve()

    with _lock:
        loop = _ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            _call_async(tool_name, arguments or {}, resolved.mcp_url), loop
        )
    return future.result(timeout=resolved.mcp_timeout)


def reset() -> None:
    """Drops the cached client/connection -- for tests that flip
    PROCESS_TOOLKIT_MCP_URL mid-process. Does not stop the background
    loop/thread (harmless to leave running; a fresh client reconnects
    lazily on the next call())."""
    global _client, _client_url
    with _lock:
        loop = _loop
        client = _client
        _client = None
        _client_url = None
    if client is not None and loop is not None and loop.is_running():
        async def _close() -> None:
            try:
                await client.close()
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(_close(), loop).result(timeout=5)
