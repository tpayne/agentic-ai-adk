ARG pythonVersion=3.12.9
FROM python:${pythonVersion}-alpine AS builder

RUN apk add --no-cache --repository=http://dl-cdn.alpinelinux.org/alpine/edge/main \
    && apk -U upgrade \
    && apk add --no-cache curl cargo

WORKDIR /app

COPY requirements.txt .
COPY adk ./adk

RUN pip install -r requirements.txt

ARG account=yahoo_finance_user
RUN addgroup --system ${account} && adduser --system ${account}
RUN adduser ${account} ${account}

USER ${account}

# Run the merged ADK LLM agent module implemented in adk/adk_yfinance_llm_agent.py
CMD ["python3", "-m", "adk.agent"]

