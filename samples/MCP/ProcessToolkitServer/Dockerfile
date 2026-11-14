# Build context for this Dockerfile MUST be the repo root (not this
# directory), because pyproject.toml's `[tool.uv.sources]` depends on
# shared/process_toolkit (../../../shared/process_toolkit from this
# project's own directory), which lives outside it:
# `docker build --file samples/MCP/ProcessToolkitServer/Dockerfile .`
# from the repo root. A build invoked with this directory as context
# cannot see that shared code and `uv sync` will fail.
#
# Mirrors samples/Neurosan/ProcessEngineering's own Dockerfile (uv +
# pyproject.toml/uv.lock, same shared-package-at-matching-depth trick) --
# see that file's comments for why uv (unlike pip) needs the real
# directory depth, not just a deep-enough-looking one. fastmcp and
# process-toolkit's own dependencies (matplotlib, pandas, python-docx,
# networkx, openpyxl) all ship prebuilt manylinux wheels for this base
# image, so no apt-get build toolchain is needed here either.
FROM python:3.15-slim

# Installs the `uv` binary itself by copying it out of Astral's own
# published image, rather than `pip install uv`.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# /app stands in for the repo root inside the image, at the same directory
# depth as the real repo (samples/MCP/ProcessToolkitServer, shared/
# process_toolkit) so pyproject.toml's unmodified "../../../shared/
# process_toolkit" source entry resolves identically to local dev.
WORKDIR /app/samples/MCP/ProcessToolkitServer

# The shared package itself, copied to the exact path pyproject.toml's own
# "../../../shared/process_toolkit" source entry already resolves to from
# this WORKDIR -- no path differences needed between local dev and this
# image.
COPY shared/process_toolkit /app/shared/process_toolkit

# Dependencies first (cached across builds unless pyproject.toml/uv.lock
# change), application code second. Paths relative to the repo-root build
# context.
COPY samples/MCP/ProcessToolkitServer/pyproject.toml samples/MCP/ProcessToolkitServer/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY samples/MCP/ProcessToolkitServer/server.py samples/MCP/ProcessToolkitServer/dispatch.py samples/MCP/ProcessToolkitServer/client.py ./
RUN uv sync --locked --no-dev

ARG account=process_toolkit_mcp_user
RUN useradd -ms /bin/bash ${account} \
    && mkdir -p /app/samples/MCP/ProcessToolkitServer/output \
    && chown -R ${account}:${account} /app \
    && chmod -R o+rx /app/shared/

USER ${account}

# PROCESS_TOOLKIT_MCP_OUTPUT_DIR defaults to "<this dir>/output" (see
# server.py's own module docstring) -- already the right, writable,
# absolute path for this image, so it's left unset here. Mount a volume
# over /app/samples/MCP/ProcessToolkitServer/output if generated artifacts
# need to survive a container restart.
EXPOSE 8765

# Matches server.py's own default: Streamable HTTP, bound to 0.0.0.0 so
# the endpoint is reachable from outside the container, at
# http://<host>:8765/mcp. Override with `docker run -e
# PROCESS_TOOLKIT_MCP_PORT=...` if 8765 needs to change.
CMD ["uv", "run", "python", "server.py"]
