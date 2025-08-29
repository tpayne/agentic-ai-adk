# Email Processing Sample
This sample code demonstrates how to use the Agentic Development Kit (ADK) to process emails using Google Cloud Platform (GCP) services. The code includes functionalities for reading, processing, and responding to emails using AI agents.

## Prerequisites
- Python 3.8 or higher
- GCP account with necessary permissions
- Google Cloud SDK installed and configured
- An email service (e.g., Gmail) with API access enabled

## Setup

```bash
    rm -r .venv
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python3 agent.py
    adk deploy agent_engine \
        --project=$(gcloud config get-value project) \
        --region=us-central1 \
        --staging_bucket=$(gcloud storage buckets list --project=$(gcloud config get-value project) --format="value(nam --limit=1) \
        --display_name="email_processing"
```