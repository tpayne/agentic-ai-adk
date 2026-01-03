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

WORKDIR /app

COPY requirements.txt .
COPY process_agents ./process_agents
COPY instructions ./instructions

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

ARG account=adk_process_user
RUN useradd -ms /bin/bash ${account}

# Ensure output directories exist
RUN mkdir -p /app/output/logs /app/output/subprocesses /app/output/docs \
    && chown -R ${account}:${account} /app/ \
    && chmod -R o+rwx /app/

USER ${account}

ENTRYPOINT ["/bin/sh", "-c"]
CMD ["rm -rf .venv && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && .venv/bin/adk run process_agents"]
