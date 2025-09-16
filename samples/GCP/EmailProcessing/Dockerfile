ARG pythonVersion=3.12.9
FROM python:${pythonVersion}-alpine AS builder

RUN apk add --no-cache --repository=http://dl-cdn.alpinelinux.org/alpine/edge/main \
    && apk -U upgrade \
    && apk add --no-cache curl cargo

WORKDIR /app

COPY requirements.txt .
COPY resources ./resources
COPY adk ./adk

RUN pip install -r requirements.txt

ARG account=emailuser
RUN addgroup --system ${account} && adduser ${account} --system
RUN adduser ${account} ${account} 

CMD ["python3","-m","adk.adkCloudRunService"]
