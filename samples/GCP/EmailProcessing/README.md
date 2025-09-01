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
    {
        "email_source": "Hi, I need help with my laptop that won't turn on. I've tried charging it and pressing the power button multiple times. Can you help me draft an email to tech support?",
        "email_draft": "Subject: Re: Urgent: Laptop is not turning on\n\nDear John Doe,\n\nThank you for reaching out to IT support. I understand your laptop is not turning on, and you've already tried charging it and pressing the power button. I'll do my best to assist you.\n\nTo help me diagnose the problem, could you please provide the following information:\n\n1.  **Laptop Model:** Please provide the exact model number of your laptop (e.g., Dell XPS 13, Lenovo ThinkPad T480). This is usually found on a sticker on the bottom of the laptop.\n2.  **Power Adapter:** Is the charging indicator light on the laptop lighting up when the adapter is plugged in?\n3.  **External Display:** If possible, can you connect your laptop to an external monitor to see if there is any display output?\n4.  **Battery Removal:** If your laptop has a removable battery, please remove it, hold the power button for 30 seconds, reinsert the battery, and try turning it on again.\n5.  **Recent Events:** Were there any recent events, such as a power surge, liquid spill, or physical damage, that might have caused this issue?\n\nOnce I have this information, I can provide more specific troubleshooting steps.\n\nIf the issue persists and we cannot resolve it quickly, I will create an IT support ticket for you with the following details:\n\n*   **Summary:** Laptop not powering on.\n*   **Description:** User reports laptop is not turning on despite being charged and power button pressed multiple times. Further troubleshooting steps will be attempted.\n*   **Priority:** High\n*   **Classification:** Hardware\n\nThank you for your patience.\n\nSincerely,\n\nHelpBot\nIT Support\n",
        "email_sentiment": "negative",
        "email_review_comments": "No further comments."
    }

    python3 agent.py \
        "Hi, My laptop is making clunking noises when I boot it up and it then starts to whine. I think the fan or HD has a problem. How should I proceed? This is urgent. Thanks, Jim"
    {
        "email_source": "Hi, My laptop is making clunking noises when I boot it up and it then starts to whine. I think the fan or HD has a problem. How should I proceed? This is urgent. Thanks, Jim",
        "email_draft": "Subject: Re: a new support request - Laptop Noise Issue\n\nDear Jim,\n\nThank you for reaching out to IT Support. I understand that you're experiencing unusual noises (clunking and whining) from your laptop upon startup, which you suspect may be related to the fan or hard drive. I'll do my best to assist you.\n\nGiven the symptoms you describe, there are a couple of potential causes:\n\n1.  **Hard Drive Issues:** Clunking sounds are often indicative of a mechanical hard drive failing. The read/write head may be malfunctioning, causing the noise.\n2.  **Fan Problems:** A failing fan can produce whining or grinding noises, especially if a bearing is worn out or the fan is obstructed.\n\n**Troubleshooting Steps:**\n\nTo help me diagnose the issue more effectively, could you please try the following and provide the results?\n\n1.  **Listen Carefully:** Try to pinpoint the location of the noise. Is it coming from the area around the fan vents or from the main body of the laptop where the hard drive is usually located?\n2.  **Check the System's Temperature:** After the laptop has been running for a few minutes (if it remains stable enough to do so), check the system temperature. You can often do this through system monitoring software or the BIOS. High temperatures can confirm fan issues. (Instructions on how to check temperature via BIOS vary by manufacturer but generally require pressing DEL, F2, F12, or ESC keys repeatedly as the system boots.)\n3.  **Run a Disk Check:** If the system is stable enough, run a disk check utility (e.g., `chkdsk` in Windows) to check for file system errors or bad sectors on your hard drive.\n    *   In Windows, open Command Prompt as administrator, and type `chkdsk /f /r` and press Enter. You will be prompted to schedule the check on the next restart. Type `Y` and press Enter, then restart your computer.\n\n**Important Note:** If you suspect a failing hard drive, immediately back up any critical data if possible to prevent data loss.\n\nIf the problem persists or you are uncomfortable performing these steps, I will create an IT support ticket for you.\n\n**IT Ticket Details (If needed):**\n\n*   **Summary:** Laptop making clunking and whining noises on startup.\n*   **Description:** The user reports that their laptop is making clunking noises during boot-up, followed by a whining sound. The user suspects a failing hard drive or fan. Urgent due to potential data loss or hardware failure.\n*   **Priority:** High\n*   **Classification:** Hardware\n\nPlease provide the requested information so I can assist you further.\n\nThank you,\n\nIT Support\n",
        "email_sentiment": "negative",
        "email_review_comments": "No further comments."
    }

    python3 agent.py \
        '{"fromEmailAddress":"jdoe@example.com", "subject":"Laptop issues", "body":"Urgent: I need help! My laptop has bluescreened and will not longer boot up. I have work I need to do and I am blocked without my machine. I need assistance ASAP! Please contact me! Thanks, Joe"}'                                                       
    {
        "email_source": "Urgent: I need help! My laptop has bluescreened and will not longer boot up. I have work I need to do and I am blocked without my machine. I need assistance ASAP! Please contact me! Thanks, Joe",
        "email_draft": "Subject: Re: Laptop issues\n\nDear Joe,\n\nI understand your laptop is experiencing a blue screen error and is preventing you from working. I'll do my best to assist you in resolving this issue quickly.\n\nA blue screen error (also known as a \"Stop Error\") generally indicates a critical system error in Windows. Since the system is not booting, here are some steps we can try:\n\n1.  **Attempt to boot into Safe Mode:**\n    *   Restart your computer.\n    *   As it restarts (before the Windows logo appears), repeatedly press the F8 key. This should bring up the Advanced Boot Options menu.\n    *   Select \"Safe Mode\" using the arrow keys and press Enter.\n    *   If you can boot into Safe Mode, it indicates that the core Windows services are functioning, and the issue may be related to a driver or software.\n\n2.  **If Safe Mode Fails, try Last Known Good Configuration:**\n    *   As with Safe Mode, access the Advanced Boot Options menu (repeatedly press F8 during startup).\n    *   Select \"Last Known Good Configuration (advanced)\" and press Enter. This will attempt to boot using the last registry and driver configuration that worked.\n\n3.  **Check Hardware Connections (If comfortable):** While less likely with a laptop, ensure that the RAM modules are properly seated. Consult your laptop's manual for instructions on how to access the RAM.\n\nIf you are able to boot into Safe Mode, please provide the following information:\n\n*   When did the blue screen issue start occurring?\n*   Were there any recent software or driver updates installed before the issue started?\n*   What is the exact blue screen error message (if you can recall it)? This can help pinpoint the cause.\n*   What were you doing when the blue screen occurred?\n\nIf neither Safe Mode nor Last Known Good Configuration works, I will need to create a ticket for further investigation.\n\nIn that case the ticket will have the following details:\n\n*   **Summary:** Laptop experiencing blue screen and unable to boot.\n*   **Description:** User's laptop is encountering a blue screen error during startup, preventing normal operation. Attempts to boot into Safe Mode and Last Known Good Configuration have failed. User is blocked from work.\n*   **Priority:** High\n*   **Classification:** OS\n\nPlease let me know the results of trying Safe Mode and Last Known Good Configuration.\n\nRegards,\n\nHelpBot\n",
        "email_sentiment": "negative",
        "email_review_comments": "No further comments."
    }
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
    export PROJECT_ID=$(gcloud config get-value project)
    adk deploy agent_engine EmailProcessing/ \
        --project=$(gcloud config get-value project) \
        --region=us-central1 \
        --staging_bucket="${gsName}" \
        --display_name="email_processing"
```

## Notes
- For notes on ADK agents - see https://google.github.io/adk-docs/agents/