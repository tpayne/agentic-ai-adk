# Requirements and Proposal Response Test Samples

These are fictional, text-searchable PDF documents for exercising the
Requirements Summary and Proposal Response workflows. Names, organizations,
dates, and procurement details are invented; the samples are not live tenders
or real supplier credentials.

## Requirements Summary

Each folder is an independent input set. The requirements reader processes
files directly inside the selected folder; do not summarize the parent
`RequirementsManagement` directory, which contains separate scenarios.

- `RequirementsManagement/MetroLink_RFP_Package/` contains a public-sector
  procurement RFP and a clarifications addendum. The addendum explicitly
  changes some requirements and leaves a recovery-point conflict unresolved.
- `RequirementsManagement/Healthcare_Referral_Baseline/` contains a draft
  healthcare interoperability requirements baseline with measurable targets,
  open decisions, and clinical-safety boundaries.

Example request from the ProcessEngineering project directory:

> Read the files in `./examples/TestSamples/RequirementsManagement/MetroLink_RFP_Package` and summarize the requirements. Identify conflicts, priorities, and questions that need clarification.

Repeat with the healthcare folder to test a different sector and document
style.

## Proposal Response

First summarize the MetroLink RFP package and save its requirements summary.
Then use `ResponseToProposal/04_Bidder_Offering_Brief_Harborlight_Digital.pdf`
as source material for the bidder's fictional capabilities. The proposal
response workflow uses the saved requirements summary plus the offering
description supplied in the request; include the relevant facts in that
request rather than relying on the response workflow to ingest the PDF.

Example request:

> Respond to the MetroLink solicitation using the saved requirements summary. Our fictional offering is Harborlight Digital's configurable supplier onboarding portal with resumable applications, configurable review and approval workflows, expiry alerts, audit history, and integration to a finance platform using an API or scheduled encrypted file transfer. We propose deployment in a customer-controlled UK cloud subscription, subject to discovery and architecture review. Discovery, configuration, integration, migration of active supplier records, testing, training, and launch are in scope. Pricing, service targets, certifications, and customer references are not provided; do not invent them. Identify assumptions, exceptions, and the unresolved recovery-point conflict.

The bidder brief deliberately omits prices, certifications, customer
references, and binding service-level commitments so the response can be
checked for unsupported claims.
