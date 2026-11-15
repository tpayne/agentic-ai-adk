"""Resolves PROCESS_TOOLKIT_MODE/_MCP_URL fresh from the environment on every
call -- this package has no config file of its own and no caller-specific
convention (neuro-san's `.env`, GCP's `properties/agentapp.properties` via
`getProperty()`) baked in; each port is responsible for pushing its own two
settings into os.environ before process_interface is first used. Read fresh
rather than cached at import time so flipping the env var mid-process (e.g.
in a test) takes effect on the next call, matching the pattern this
codebase's own env-var reads already use (see e.g. coded_tools/common/
loop_control.py's LOOP_HARD_STOP).
"""

import os
from dataclasses import dataclass

MODE_ENV_VAR = "PROCESS_TOOLKIT_MODE"
MCP_URL_ENV_VAR = "PROCESS_TOOLKIT_MCP_URL"
MCP_TIMEOUT_ENV_VAR = "PROCESS_TOOLKIT_MCP_TIMEOUT"

DEFAULT_MCP_TIMEOUT_SECONDS = 30.0


class ProcessInterfaceConfigError(RuntimeError):
    """Raised when mode=mcp is selected but no MCP URL has been configured."""


@dataclass(frozen=True)
class ResolvedConfig:
    mode: str  # "local" or "mcp"
    mcp_url: str | None
    mcp_timeout: float


def resolve() -> ResolvedConfig:
    """Anything other than exactly "mcp" (case-insensitive, trimmed) resolves
    to "local" -- fails safe to the in-process behavior that existed before
    this package did, rather than failing safe to a network call."""
    raw_mode = os.environ.get(MODE_ENV_VAR, "local").strip().lower()
    mode = "mcp" if raw_mode == "mcp" else "local"

    mcp_url = os.environ.get(MCP_URL_ENV_VAR) or None
    if mode == "mcp" and not mcp_url:
        raise ProcessInterfaceConfigError(
            f"{MODE_ENV_VAR}=mcp but {MCP_URL_ENV_VAR} is not set. "
            "Set it to the ProcessToolkitServer's Streamable HTTP endpoint, "
            "e.g. http://127.0.0.1:8765/mcp."
        )

    timeout_raw = os.environ.get(MCP_TIMEOUT_ENV_VAR)
    try:
        mcp_timeout = float(timeout_raw) if timeout_raw else DEFAULT_MCP_TIMEOUT_SECONDS
    except ValueError:
        mcp_timeout = DEFAULT_MCP_TIMEOUT_SECONDS

    return ResolvedConfig(mode=mode, mcp_url=mcp_url, mcp_timeout=mcp_timeout)


def is_mcp_mode() -> bool:
    return resolve().mode == "mcp"
