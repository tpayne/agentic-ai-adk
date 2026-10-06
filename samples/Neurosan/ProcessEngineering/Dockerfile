# Ported from samples/GCP/ProcessEngineering's Dockerfile. Re-expressed for
# this project's own tooling (uv + pyproject.toml/uv.lock, not pip +
# requirements.txt) and serving model (neuro-san's own `ns run` HTTP
# server + nsflow UI, not a hand-rolled `python -m process_agents.agent`
# entrypoint -- see README.md's "Deliberate simplifications" for why that
# custom Flask layer isn't ported at all).
#
# The ADK original's apt-installed build toolchain (gcc/g++/build-essential/
# libfreetype6-dev/libpng-dev/libjpeg-dev, for compiling matplotlib/numpy/
# pandas from source) isn't needed here: this project's equivalent
# dependencies (matplotlib, pandas, python-docx, networkx) all ship
# prebuilt manylinux wheels for this base image, confirmed via `uv sync`
# installing them with no compilation step. graphviz is also dropped --
# this port's diagram generation is pure matplotlib/networkx layout, never
# shells out to a `dot`/`neato` binary the way the ADK original's diagram
# tooling could.
FROM python:3.14-slim

# Installs the `uv` binary itself by copying it out of Astral's own
# published image, rather than `pip install uv` -- the standard way to get
# uv into a Docker build without needing pip/network access for it
# specifically.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependencies first (cached across builds unless pyproject.toml/uv.lock
# change), application code second.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev

ARG account=neurosan_process_user
RUN useradd -ms /bin/bash ${account} \
    && mkdir -p /app/output \
    && chown -R ${account}:${account} /app

USER ${account}

# Same two env vars cli.py sets for itself (see cli.py's own module
# docstring) -- a direct/in-process neuro-san session resolves agent names
# and CodedTool classes against these, not simply "relative to cwd".
ENV AGENT_MANIFEST_FILE=/app/registries/manifest.hocon
ENV AGENT_TOOL_PATH=/app/coded_tools

# Matches `ns run`'s own defaults (see README.md's "Running" section):
# 8080 for the neuro-san HTTP/chat API, 4173 for the nsflow UI.
EXPOSE 8080
EXPOSE 4173

# --server-host 0.0.0.0 so the HTTP API is reachable from outside the
# container -- `ns run`'s own default (NEURO_SAN_SERVER_HOST) is
# "localhost", which would make the server unreachable from outside the
# container's own network namespace. Set an LLM provider API key (see
# README.md's "Setup" section) via `docker run -e GOOGLE_API_KEY=...`
# (or ANTHROPIC_API_KEY/OPENAI_API_KEY/etc.) -- never bake one into this
# image or a wrapper script.
CMD ["uv", "run", "ns", "run", "--server-only", "--server-host", "0.0.0.0"]
