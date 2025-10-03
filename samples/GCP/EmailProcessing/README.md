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

Note - To run the `agent.py` standalone, you may need to add a `main` runner routine as the code is currently configured as a REST API service only, e.g. add the following code to the .py file.

```python

# --- Main Execution Block for a local, working example ---
if __name__ == "__main__":
    # Example for JSON input
    json_message = json.dumps({
        "fromEmailAddress": "johndoe@example.com",
        "subject": "Urgent: My laptop is not turning on",
        "body": "Hi, my laptop is not turning on. I've tried charging it and pressing the power button multiple times."
    }, indent=2)

    # Example for plain string input for a software issue
    string_message_software = "My web browser keeps crashing when I open a new tab."

    # Example for plain string input for a hardware issue
    string_message_hardware = "My mouse isn't working at all."

    # Choose which message to run based on command-line argument
    # Default to the JSON message if no argument is provided
    user_message = sys.argv[1] if len(sys.argv) > 1 else json_message

    final_state_json = asyncio.run(call_agent_async(user_message))
    print(final_state_json)
```

This will allow the agent to run as a simple invocable script and not use a REST API to drive it.

```bash
    rm -r .venv
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    export GOOGLE_API_KEY=<YourKey>

    python3 adk/agent.py
    {
        "email_source": "Hi, I need help with my laptop that won't turn on. I've tried charging it and pressing the power button multiple times. Can you help me draft an email to tech support?",
        "email_draft": "Subject: Re: Urgent: Laptop is not turning on\n\nDear John Doe,\n\nThank you for reaching out to IT support. I understand your laptop is not turning on, and you've already tried charging it and pressing the power button. I'll do my best to assist you.\n\nTo help me diagnose the problem, could you please provide the following information:\n\n1.  **Laptop Model:** Please provide the exact model number of your laptop (e.g., Dell XPS 13, Lenovo ThinkPad T480). This is usually found on a sticker on the bottom of the laptop.\n2.  **Power Adapter:** Is the charging indicator light on the laptop lighting up when the adapter is plugged in?\n3.  **External Display:** If possible, can you connect your laptop to an external monitor to see if there is any display output?\n4.  **Battery Removal:** If your laptop has a removable battery, please remove it, hold the power button for 30 seconds, reinsert the battery, and try turning it on again.\n5.  **Recent Events:** Were there any recent events, such as a power surge, liquid spill, or physical damage, that might have caused this issue?\n\nOnce I have this information, I can provide more specific troubleshooting steps.\n\nIf the issue persists and we cannot resolve it quickly, I will create an IT support ticket for you with the following details:\n\n*   **Summary:** Laptop not powering on.\n*   **Description:** User reports laptop is not turning on despite being charged and power button pressed multiple times. Further troubleshooting steps will be attempted.\n*   **Priority:** High\n*   **Classification:** Hardware\n\nThank you for your patience.\n\nSincerely,\n\nHelpBot\nIT Support\n",
        "email_sentiment": "negative",
        "email_review_comments": "No further comments."
    }

    python3 adk/agent.py \
        "Hi, My laptop is making clunking noises when I boot it up and it then starts to whine. I think the fan or HD has a problem. How should I proceed? This is urgent. Thanks, Jim"
    {
        "email_source": "Hi, My laptop is making clunking noises when I boot it up and it then starts to whine. I think the fan or HD has a problem. How should I proceed? This is urgent. Thanks, Jim",
        "email_draft": "Subject: Re: a new support request - Laptop Noise Issue\n\nDear Jim,\n\nThank you for reaching out to IT Support. I understand that you're experiencing unusual noises (clunking and whining) from your laptop upon startup, which you suspect may be related to the fan or hard drive. I'll do my best to assist you.\n\nGiven the symptoms you describe, there are a couple of potential causes:\n\n1.  **Hard Drive Issues:** Clunking sounds are often indicative of a mechanical hard drive failing. The read/write head may be malfunctioning, causing the noise.\n2.  **Fan Problems:** A failing fan can produce whining or grinding noises, especially if a bearing is worn out or the fan is obstructed.\n\n**Troubleshooting Steps:**\n\nTo help me diagnose the issue more effectively, could you please try the following and provide the results?\n\n1.  **Listen Carefully:** Try to pinpoint the location of the noise. Is it coming from the area around the fan vents or from the main body of the laptop where the hard drive is usually located?\n2.  **Check the System's Temperature:** After the laptop has been running for a few minutes (if it remains stable enough to do so), check the system temperature. You can often do this through system monitoring software or the BIOS. High temperatures can confirm fan issues. (Instructions on how to check temperature via BIOS vary by manufacturer but generally require pressing DEL, F2, F12, or ESC keys repeatedly as the system boots.)\n3.  **Run a Disk Check:** If the system is stable enough, run a disk check utility (e.g., `chkdsk` in Windows) to check for file system errors or bad sectors on your hard drive.\n    *   In Windows, open Command Prompt as administrator, and type `chkdsk /f /r` and press Enter. You will be prompted to schedule the check on the next restart. Type `Y` and press Enter, then restart your computer.\n\n**Important Note:** If you suspect a failing hard drive, immediately back up any critical data if possible to prevent data loss.\n\nIf the problem persists or you are uncomfortable performing these steps, I will create an IT support ticket for you.\n\n**IT Ticket Details (If needed):**\n\n*   **Summary:** Laptop making clunking and whining noises on startup.\n*   **Description:** The user reports that their laptop is making clunking noises during boot-up, followed by a whining sound. The user suspects a failing hard drive or fan. Urgent due to potential data loss or hardware failure.\n*   **Priority:** High\n*   **Classification:** Hardware\n\nPlease provide the requested information so I can assist you further.\n\nThank you,\n\nIT Support\n",
        "email_sentiment": "negative",
        "email_review_comments": "No further comments."
    }

    python3 adk/agent.py \
        '{"fromEmailAddress":"jdoe@example.com", "subject":"Laptop issues", "body":"Urgent: I need help! My laptop has bluescreened and will not longer boot up. I have work I need to do and I am blocked without my machine. I need assistance ASAP! Please contact me! Thanks, Joe"}'
    {
        "email_source": "Urgent: I need help! My laptop has bluescreened and will not longer boot up. I have work I need to do and I am blocked without my machine. I need assistance ASAP! Please contact me! Thanks, Joe",
        "email_draft": "Subject: Re: Laptop issues\n\nDear Joe,\n\nI understand your laptop is experiencing a blue screen error and is preventing you from working. I'll do my best to assist you in resolving this issue quickly.\n\nA blue screen error (also known as a \"Stop Error\") generally indicates a critical system error in Windows. Since the system is not booting, here are some steps we can try:\n\n1.  **Attempt to boot into Safe Mode:**\n    *   Restart your computer.\n    *   As it restarts (before the Windows logo appears), repeatedly press the F8 key. This should bring up the Advanced Boot Options menu.\n    *   Select \"Safe Mode\" using the arrow keys and press Enter.\n    *   If you can boot into Safe Mode, it indicates that the core Windows services are functioning, and the issue may be related to a driver or software.\n\n2.  **If Safe Mode Fails, try Last Known Good Configuration:**\n    *   As with Safe Mode, access the Advanced Boot Options menu (repeatedly press F8 during startup).\n    *   Select \"Last Known Good Configuration (advanced)\" and press Enter. This will attempt to boot using the last registry and driver configuration that worked.\n\n3.  **Check Hardware Connections (If comfortable):** While less likely with a laptop, ensure that the RAM modules are properly seated. Consult your laptop's manual for instructions on how to access the RAM.\n\nIf you are able to boot into Safe Mode, please provide the following information:\n\n*   When did the blue screen issue start occurring?\n*   Were there any recent software or driver updates installed before the issue started?\n*   What is the exact blue screen error message (if you can recall it)? This can help pinpoint the cause.\n*   What were you doing when the blue screen occurred?\n\nIf neither Safe Mode nor Last Known Good Configuration works, I will need to create a ticket for further investigation.\n\nIn that case the ticket will have the following details:\n\n*   **Summary:** Laptop experiencing blue screen and unable to boot.\n*   **Description:** User's laptop is encountering a blue screen error during startup, preventing normal operation. Attempts to boot into Safe Mode and Last Known Good Configuration have failed. User is blocked from work.\n*   **Priority:** High\n*   **Classification:** OS\n\nPlease let me know the results of trying Safe Mode and Last Known Good Configuration.\n\nRegards,\n\nHelpBot\n",
        "email_sentiment": "negative",
        "email_review_comments": "No further comments."
    }

    python3 adk/agent.py "What experience level is expected for a Senior DevOps role?"
    {
        "email_source": "What experience level is expected for a Senior DevOps role?",
        "email_draft": "Subject: Re: a new support request\n\nDear Customer,\n\nThank you for your inquiry regarding the expected experience level for a Senior DevOps role.\n\nTypically, a Senior DevOps role, which may also be titled Senior Platform Engineer (Cloud DevOps), requires a motivated technology professional with significant practical IT experience in cloud technologies, infrastructure, and operations. Candidates should possess knowledge of cloud-native tools, languages, and methods across a broad spectrum of technologies, with a demonstrated specialization in one or two areas such as containers, CI/CD pipelines, or Infrastructure as Code (IaC).\n\nIn addition to technical skills, experience in mentoring and training junior engineers is also expected. Holding a professional-level certification with a Cloud Service Provider is preferred, or candidates should be actively working towards obtaining one.\n\nKey responsibilities and expected skills for this role commonly include:\n\n*   **Cloud Solution Design and Implementation:** Designing and implementing scalable, reliable, and cost-effective cloud solutions using platforms like Google Cloud Platform (GCP) services and products. This involves analyzing business requirements and recommending appropriate cloud technologies and architectures.\n*   **Infrastructure Management and Automation:** Managing and automating the deployment, scaling, and management of cloud infrastructure using tools such as Kubernetes or Google Cloud Deployment Manager. This also includes optimizing infrastructure costs and implementing infrastructure-as-code practices for consistency and version control.\n*   **Security and Compliance:** Implementing and maintaining security controls and policies to ensure the confidentiality, integrity, and availability of cloud infrastructure and data. Monitoring and responding to security incidents and vulnerabilities, performing regular security assessments and audits, and ensuring compliance with industry standards like GDPR, HIPAA, and PCI DSS are also part of the role.\n*   **Monitoring and Troubleshooting:** Monitoring cloud infrastructure and services for performance, availability, and security issues using tools like Stackdriver or Prometheus. This includes performing root cause analysis, troubleshooting issues, and implementing corrective and preventive measures. Continuous improvement of reliability and resilience through best practices like fault-tolerance, redundancy, and disaster recovery is also expected.\n*   **Technical Proficiency:** Excellent understanding of Google Cloud Platform architecture and services, including Compute Engine, Kubernetes Engine, and Cloud Build, is crucial. Experience with infrastructure automation tools such as Terraform and Ansible, and containerization tools like Docker, is also required. The ability to code using Python, Go, Bash, or similar scripting languages is essential. Understanding of networking, security, and compliance in a cloud environment and/or on Linux distribution systems is also necessary.\n*   **Leadership and Mentorship:** Senior Platform Engineers are expected to mentor teams and collaborate with others to find the best way to progress. They drive cloud automation and Kubernetes projects and attract, encourage, and develop engineers. They also orchestrate and lead scrum teams that leverage DevSecOps or SRE approaches.\n*   **Strategic Contribution:** Contributing ideas and opinions on the latest industry trends is encouraged. The role involves transforming developers' experiences and enabling organizations to make the most of cloud-native technologies. Senior Platform Engineers are responsible for ensuring some of the world's most demanding applications are available and are involved in developing for tomorrow's needs.\n\nFor your reference, within Capgemini's Cloud Infrastructure Services business area in the UK, this role typically aligns with an I7-I8 level/grade. Other companies, such as Qodea, offer development paths for their Platform Engineering teams ranging from Core to Lead or Principal.\n\nI hope this information is helpful. Please let me know if you have any further questions.\n\nSincerely,\n\nHelpBot\n",
        "email_sentiment": "Informative",
        "email_intention": "FAQ Request",
        "tool_called_message": "A Senior DevOps role, often titled Senior Platform Engineer (Cloud DevOps), requires a motivated tech professional with practical IT experience in cloud technologies, infrastructure, and operations. Candidates should have knowledge of cloud-native tools, languages, and methods across a broad spectrum of technologies, demonstrating specialization in one or two areas such as containers, CI/CD pipelines, or Infrastructure as Code (IaC). Experience mentoring and training junior engineers is also expected. Professional-level certification with a Cloud Service Provider is preferred, or candidates should be working towards one.\n\nKey responsibilities and expected skills for this role include:\n*   **Cloud Solution Design and Implementation**: Designing and implementing scalable, reliable, and cost-effective cloud solutions using platforms like Google Cloud Platform (GCP) services and products. This involves analyzing business requirements and recommending appropriate cloud technologies and architectures.\n*   **Infrastructure Management and Automation**: Managing and automating the deployment, scaling, and management of cloud infrastructure using tools such as Kubernetes or Google Cloud Deployment Manager. This also includes optimizing infrastructure costs and implementing infrastructure-as-code practices for consistency and version control.\n*   **Security and Compliance**: Implementing and maintaining security controls and policies to ensure the confidentiality, integrity, and availability of cloud infrastructure and data. Monitoring and responding to security incidents and vulnerabilities, performing regular security assessments and audits, and ensuring compliance with industry standards like GDPR, HIPAA, and PCI DSS are also part of the role.\n*   **Monitoring and Troubleshooting**: Monitoring cloud infrastructure and services for performance, availability, and security issues using tools like Stackdriver or Prometheus. This includes performing root cause analysis, troubleshooting issues, and implementing corrective and preventive measures. Continuous improvement of reliability and resilience through best practices like fault-tolerance, redundancy, and disaster recovery is also expected.\n*   **Technical Proficiency**: Excellent understanding of Google Cloud Platform architecture and services, including Compute Engine, Kubernetes Engine, and Cloud Build, is crucial. Experience with infrastructure automation tools such as Terraform and Ansible, and containerization tools like Docker, is also required. The ability to code using Python, Go, Bash, or similar scripting languages is essential. Understanding of networking, security, and compliance in a cloud environment and/or on Linux distribution systems is also necessary.\n*   **Leadership and Mentorship**: Senior Platform Engineers are expected to mentor teams and collaborate with others to find the best way to progress. They drive cloud automation and Kubernetes projects and attract, encourage, and develop engineers. They also orchestrate and lead scrum teams that leverage DevSecOps or SRE approaches.\n*   **Strategic Contribution**: Contributing ideas and opinions on the latest industry trends is encouraged. The role involves transforming developers' experiences and enabling organizations to make the most of cloud-native technologies. Senior Platform Engineers are responsible for ensuring some of the world's most demanding applications are available and are involved in developing for tomorrow's needs.\n\nThe role is at an I7-I8 level/grade within Capgemini's Cloud Infrastructure Services business area in the UK. Qodea, another company, offers a development path for their Platform Engineering team, ranging from Core to Lead or Principal.",
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

## Building Docker Image for Cloud Deployment

To build the docker image, you will need to do the following.

```bash
    docker build . -t adkagent
```

To run the docker image locally, you will need to do the following.

````bash
    gcloud auth application-default login
    docker run --rm -it -v ~/.config/gcloud:/root/.config/gcloud \
        -e PROJECT_ID=<projectId> \
        -e GOOGLE_API_KEY=<apiKey> \
        -e AGENTSPACE_AI_URL=https://<region>>-discoveryengine.googleapis.com/v1alpha/projects/<projectId>/locations/<region>/collections/default_collection/engines/<agentspaceAgent>/servingConfigs/default_search:search \
        -e GOOGLE_GENAI_USE_VERTEXAI=false \
        -p 8080:8080 \
        adkagent
    curl http://localhost:8080/query \
        -H "Content-Type: application/json" \
        -d '{
                "query": {
                    "fromEmailAddress": "johndoe@example.com",
                    "subject": "Policy query",
                    "body": "Hi, I am from HR and I need to know about the policy for hiring new recruits, thanks."
                }
            }'
        {
            "response": {
                "answer": {
                "email_draft": "```html\n<html>\n<body>\n<p>Dear John Doe,</p>\n\n<p>Thank you for reaching out to us. I understand you're looking for information regarding our company's hiring policies for new recruits.</p>\n\n<p>Our policy is to be an **equal opportunity employer**. We do not unlawfully discriminate against employees or applicants based on race, color, religion, creed, sex, national origin, age, disability, marital status, veteran status, or any other status protected by applicable law. This applies to all aspects of employment, including recruitment, hiring, placement, compensation, promotion, discipline, and termination.</p>\n\n<p>We are committed to providing reasonable accommodations for qualified individuals with disabilities, as required by law. If an employee needs a reasonable accommodation, they should contact [enter authorized person\u2019s name].</p>\n\n<p>We also strictly prohibit discrimination or harassment based on any protected characteristic. We aim to create a professional environment that promotes equal employment opportunities and is free from discriminatory practices.</p>\n\n<p>For more detailed information, please refer to the **Employee Handbook**, which outlines our policies and procedures in detail. It is located [state location of handbook, e.g., on the company intranet under HR Resources].</p>\n\n<p>I hope this addresses your query. If you need further clarification or have more specific questions, please do not hesitate to ask.</p>\n\n<p>Best regards,</p>\n<p>HelpBot</p>\n<p>IT Support</p>\n</body>\n</html>\n```",
                "tool_results": "This company is an equal opportunity employer and does not unlawfully discriminate against employees or applicants for employment based on an individual’s race, color, religion, creed, sex, national origin, age, disability, marital status, veteran status, or any other status protected by applicable law. This policy applies to all terms, conditions, and privileges of employment, including recruitment, hiring, placement, compensation, promotion, discipline, and termination. The company makes reasonable accommodations for qualified individuals with disabilities to the extent required by law whenever possible. Employees who wish to request a reasonable accommodation should contact [enter authorized person’s name].\n\nThe company prohibits discrimination or harassment based on race, color, religion, creed, sex, national origin, age, disability, marital status, veteran status, or any other status protected by applicable law. Every individual has the right to work in a professional atmosphere that promotes equal employment opportunities and is free from discriminatory practices, including harassment. Discrimination includes, but is not limited to, making any employment decision or employment-related action based on race, color, religion, creed, age, sex, disability, national origin, marital or veteran status, or any other status protected by applicable law. Harassment is generally defined as unwelcome verbal or non-verbal conduct, based upon a person’s protected characteristic, that denigrates or shows hostility or aversion toward the person because of the characteristic, and which affects the person’s employment opportunities or benefits, has the purpose or effect of unreasonably interfering with the person’s work performance, or has the purpose or effect of creating an intimidating, hostile or offensive working environment. Harassing conduct includes, but is not limited to, epithets and slurs. Violations of this policy will not be tolerated.\n\nAn employee handbook's purpose is to orient new employees with the company and provide answers to frequently asked employee questions. It informs new employees about company policy, emphasizes the at-will nature of employment, and outlines the company’s disciplinary and termination rights. Most importantly, it is a declaration of the employer’s rights and expectations. To prepare a handbook, companies should review their policies, decide which are fundamental, which need adjustment, and which should be removed. This model handbook is intended to help in that review process and may include policies that a company does not have. For example, if a company does not offer health insurance, it would not include a section on health insurance or COBRA.\n\nAt a minimum, an employee handbook should contain:\n* An employment at-will disclaimer (section 1.3).\n* A statement regarding equal employment opportunity (section 2.1).\n* A policy prohibiting unlawful discrimination and harassment (section 2.2).\n* A section describing the policy for use of company property, social media, and privacy rules (section 3).\n* A section on employment classification and overtime rules (section 4).\n* A policy on Family and Medical Leave if the company has 50 or more employees (section 6.3).\n* A section on Safety (section 9).\nCompanies should also consider including a disciplinary guideline (section 8).\n\nThis handbook has been prepared to inform new employees of the company’s policies and procedures and to establish the company’s expectations. It is not all-inclusive or intended to provide strict interpretations of policies; rather, it offers an overview of the work environment. This handbook is not a contract, expressed or implied, guaranteeing employment for any length of time, and is not intended to induce an employee to accept employment with the company. The company reserves the right to unilaterally revise, suspend, revoke, terminate, or change any of its policies, in whole or in part, whether described within this handbook or elsewhere, in its sole discretion. If any discrepancy between this handbook and current company policy arises, current company policy should be conformed to. Every effort will be made to keep employees informed of the company’s policies, however, notice of revisions cannot be guaranteed. Employees are encouraged to ask questions about any information within this handbook. This handbook supersedes and replaces any and all personnel policies and manuals previously distributed, made available, or applicable to employees.\n\nEmployment at this company is at-will. An at-will employment relationship can be terminated at any time, with or without reason or notice by either the employer or the employee. The at-will employment status of each employee cannot be altered by any verbal statement or alleged verbal agreement of company personnel. It can only be changed by a legally binding, written contract covering employment status, such as a written employment agreement for a specific duration of time. Sections 1.2 and 1.3 are essential items for a handbook. Employers are vulnerable to lawsuits if they do not provide statements regarding the non-contractual nature of the handbook or at-will employment. Some states limit the terms of at-will employment or have additional requirements for effectively disclaiming the existence of a contract (e.g., requiring that the disclaimer be conspicuous by underlining it or placing it in bold text). The National Labor Relations Board (NLRB) has recently questioned the legality of at-will employment disclaimers in employee handbooks, arguing that such provisions may restrict an employee’s Section 7 rights under the National Labor Relations Act. Specifically, the NLRB contends that typical at-will disclaimers may lead employees to conclude that they cannot alter their employment relationship, even through collective bargaining. Therefore, it is advisable to consult with an employment attorney regarding state laws and federal issues.\n\nCompanies should include an equal opportunity statement and a disability statement to demonstrate observance of relevant laws. Companies should also be aware of state and/or local laws that provide greater protection than federal discrimination laws, such as recognizing additional protected classes beyond those protected by federal statute. The Americans with Disabilities Act requires employers to provide reasonable accommodations to qualified individuals with disabilities unless doing so would cause an undue hardship to the company."
                },
                "email_data": {
                "body": "{\"fromEmailAddress\": \"johndoe@example.com\", \"subject\": \"Policy query\", \"body\": \"Hi, I am from HR and I need to know about the policy for hiring new recruits, thanks.\", \"dateTime\": null}",
                "fromEmailAddress": "a customer",
                "subject": "a new support request"
                },
                "metadata": {
                "email_intention": "Policy Question",
                "email_review_comments": "The email is well-written and informative, but replacing \"[enter authorized person’s name]\" with an actual name would improve its clarity and demonstrate attention to detail; also, specifying the exact location of the Employee Handbook, rather than providing an example, would make it even more helpful.\nNo further comments.",
                "email_sentiment": "Neutral",
                "email_urgency": "Normal"
                }
            }
        }
````

To deploy to CloudRun, you will need to run the following.

Create an environment file in `/tmp/file.txt`

Populate this file with the variables you need.

```bash
    PROJECT_ID:<projectId>
    GOOGLE_API_KEY:<apiKey>
    AGENTSPACE_AI_URL:https://<region>>-discoveryengine.googleapis.com/v1alpha/projects/<projectId>/locations/<region>/collections/default_collection/engines/<agentspaceAgent>/servingConfigs/default_search:search
    GOOGLE_GENAI_USE_VERTEXAI:false
```

Then run the below command

```bash
    gcloud run deploy emailprocessor \
        --source . \
        --region us-central1 \
        --platform managed \
        --description "CloudRun for Comms Assist" \
        --allow-unauthenticated \
        --execution-environment gen2 \
        --ingress all \
        --port 8080 \
        --env-vars-file=/tmp/file.txt
```

## Notes

- For notes on ADK agents - see https://google.github.io/adk-docs/agents/
