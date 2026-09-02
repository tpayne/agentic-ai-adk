ARG pythonVersion=3.12.9
FROM python:${pythonVersion}-alpine AS builder

RUN apk add --no-cache --repository=http://dl-cdn.alpinelinux.org/alpine/edge/main \
    && apk -U upgrade \
    && apk add --no-cache curl cargo

WORKDIR /app

COPY requirements.txt .
COPY finance_agents ./finance_agents

RUN pip install -r requirements.txt

ARG account=yahoo_finance_user
RUN addgroup --system ${account} && adduser --system ${account}
RUN adduser ${account} ${account}

USER ${account}

# Run the adk.agent module as the container entrypoint so CLI flags are forwarded.
ENTRYPOINT ["python3", "-m", "finance_agents.agent"]
CMD []
