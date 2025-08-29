# Email Processing Sample
This sample code demonstrates how to use the Agentic Development Kit (ADK) to process emails using Google Cloud Platform (GCP) services. The code includes functionalities for reading, processing, and responding to emails using AI agents.

## Prerequisites
- Python 3.8 or higher
- GCP account with necessary permissions
- Google Cloud SDK installed and configured
- An email service (e.g., Gmail) with API access enabled
- A GCP API key (see https://aistudio.google.com/apikey to generate one for your project)

## Setup and Test Agent
To setup and test the agent, you can do the following.

```bash
    rm -r .venv
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    export GOOGLE_API_KEY=<YourKey>
    python3 agent.py
```

## Test Deployment Emulation
To check that the agent is working correctly in the GCP ADK environment, you can use the web service.

```bash
    (cd ..; adk web) 
    open http://127.0.0.1:8000
```

## Deploy to GCP
To deploy to GCP, you will need to do the following.

```bash
    cd ..
    rm -fr EmailProcessing/.venv/
    local gsName="$(echo gs://adk-email-processing-$(gcloud config get-value project)-$(date +%Y%m%d-%H%M%S))"
    gcloud auth application-default login
    gcloud storage buckets create ${gsName}
    adk deploy agent_engine EmailProcessing/ \
        --project=$(gcloud config get-value project) \
        --region=us-central1 \
        --staging_bucket="${gsName}" \
        --display_name="email_processing"
```

## Notes
- For notes on ADK agents - see https://google.github.io/adk-docs/agents/