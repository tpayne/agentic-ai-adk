# Dockerfile
ARG pythonVersion=3.12.9
FROM python:${pythonVersion}-alpine AS builder

# Added graphviz and ttf-freefont for diagram generation
RUN apk add --no-cache --repository=http://dl-cdn.alpinelinux.org/alpine/edge/main \
    && apk -U upgrade \
    && apk add --no-cache curl cargo graphviz ttf-freefont

WORKDIR /app

COPY requirements.txt .
COPY process_agents ./process_agents

RUN pip install -r requirements.txt

ARG account=adk_process_user
RUN addgroup --system ${account} && adduser --system ${account}
RUN adduser ${account} ${account}

USER ${account}

# Run the root agent module
ENTRYPOINT ["python3", "-m", "process_agents.agent"]
CMD []
