# Build context for this Dockerfile MUST be the repo root (not this
# directory), because requirements.txt depends on shared/process_toolkit
# (../../../shared/process_toolkit from this sample's own directory), which
# lives outside it: `docker build --file samples/GCP/ProcessEngineering/Dockerfile .`
# from the repo root. A build invoked with this directory as context (the
# old convention, before process_toolkit existed) cannot see that shared
# code and will fail installing requirements.txt.
ARG pythonVersion=3.12.9
FROM python:${pythonVersion}-slim AS builder

# System dependencies for matplotlib, numpy, pandas, graphviz, docx, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    gcc \
    g++ \
    build-essential \
    libfreetype6-dev \
    libpng-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# /app stands in for the repo root inside the image, with the same directory
# depth as the real repo (samples/GCP/ProcessEngineering, shared/process_toolkit)
# so requirements.txt's unmodified "-e ../../../shared/process_toolkit" entry
# resolves identically to local dev. This isn't just cosmetic: pip tolerates
# "../../../" clamping at a shallower WORKDIR via plain lexical normalization,
# but uv (used by the neuro-san port's matching Dockerfile) hard-errors on a
# relative path that would need to go above its base directory -- matching
# the real depth avoids relying on that pip-only leniency at all.
WORKDIR /app/samples/GCP/ProcessEngineering

# The shared package itself, copied to the exact path requirements.txt's own
# "../../../shared/process_toolkit" entry already resolves to from this
# WORKDIR -- no path differences needed between local dev and this image.
COPY shared/process_toolkit /app/shared/process_toolkit

# Copy files (paths relative to the repo-root build context)
COPY samples/GCP/ProcessEngineering/requirements.txt .
COPY samples/GCP/ProcessEngineering/process_agents ./process_agents
COPY samples/GCP/ProcessEngineering/instructions ./instructions
COPY samples/GCP/ProcessEngineering/properties ./properties

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

ARG account=adk_process_user
RUN useradd -ms /bin/bash ${account}

# Ensure output directories exist. The runtime CMD below reinstalls
# requirements.txt (including -e ../../../shared/process_toolkit) as
# ${account}, not root, so that user needs read access to the shared copy too.
RUN mkdir -p /app/samples/GCP/ProcessEngineering/output/logs /app/samples/GCP/ProcessEngineering/output/subprocesses /app/samples/GCP/ProcessEngineering/output/docs \
    && chown -R ${account}:${account} /app/ \
    && chmod -R o+rwx /app/samples/ \
    && chmod -R o+rx /app/shared/

USER ${account}

ENTRYPOINT ["/bin/sh", "-c"]
CMD ["rm -rf .venv && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m process_agents.agent"]
