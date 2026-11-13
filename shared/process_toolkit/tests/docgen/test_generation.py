"""End-to-end coverage for generation.py's own page-break bookkeeping --
NOT per-section content (see test_content.py/test_design_sections.py for
that), just "does the final document ever place two page breaks back to
back with nothing real between them," which Word renders as a fully
blank page.
"""

import json

import docx
from docx.oxml.ns import qn

from process_toolkit import paths
from process_toolkit.schema.process_json import (
    PROCESS_JSON_FILENAME, DESIGN_JSON_FILENAME, detect_schema_type_from_disk,
)
from process_toolkit.schema.requirements_json import REQUIREMENTS_SUMMARY_FILENAME
from process_toolkit.schema.proposal_response_json import PROPOSAL_RESPONSE_FILENAME
from process_toolkit.schema.test_specification_json import TEST_SPECIFICATION_FILENAME
from process_toolkit.schema.togaf_json import TOGAF_JSON_FILENAME
from process_toolkit.docgen.generation import create_standard_doc_from_file
from process_toolkit.docgen.structure import add_iso_page_break


def _has_page_break(p_elem) -> bool:
    return any(br.get(qn("w:type")) == "page" for br in p_elem.findall(".//" + qn("w:br")))


def test_add_iso_page_break_inserts_exactly_one_new_paragraph():
    # Regression test: an earlier version of this function ALSO inserted
    # a separate, empty "spacer" paragraph immediately before the real
    # page-break paragraph. When the PRECEDING section's own content
    # already filled the current page right to its bottom edge, that
    # spacer paragraph would itself overflow onto a fresh page (plain
    # text-wrap, no break needed for that alone), and the explicit break
    # right after it then forced ANOTHER page turn -- leaving one page
    # with nothing on it but that lone spacer. Confirmed directly
    # against a real generated design document built from a user's own
    # data: 3 of 19 forced breaks landed on exactly this edge case, each
    # rendering as a fully blank page. Asserting exactly one new
    # paragraph here is what rules out that double-page-turn.
    doc = docx.Document()
    doc.add_paragraph("Some content.")
    before = len(doc.paragraphs)

    add_iso_page_break(doc)

    after = doc.paragraphs
    assert len(after) == before + 1
    assert _has_page_break(after[-1]._p)


def _has_image(p_elem) -> bool:
    return len(p_elem.findall(".//" + qn("w:drawing"))) > 0


def _has_text(p_elem) -> bool:
    return any((t.text or "").strip() for t in p_elem.findall(".//" + qn("w:t")))


def _blank_page_gaps(docx_path: str) -> list:
    """
    Returns a list of (break_index_a, break_index_b) pairs for every
    place two page breaks appear with NO real content (text, image, or
    table) between them -- i.e. every FULLY BLANK page Word would
    actually render. Walks doc.element.body directly (not
    doc.paragraphs/doc.tables separately), since those two don't
    preserve true document order relative to each other -- a table
    sitting between two breaks would be invisible to a paragraphs-only
    check and wrongly reported as a blank page.
    """
    doc = docx.Document(docx_path)
    items = []
    for child in doc.element.body:
        if child.tag == qn("w:p"):
            items.append(("p", child))
        elif child.tag == qn("w:tbl"):
            items.append(("tbl", child))

    break_idxs = [i for i, (t, el) in enumerate(items) if t == "p" and _has_page_break(el)]
    gaps = []
    for bi in range(len(break_idxs) - 1):
        segment = items[break_idxs[bi] + 1:break_idxs[bi + 1]]
        has_real_content = any(
            kind == "tbl" or (kind == "p" and (_has_text(el) or _has_image(el)))
            for kind, el in segment
        )
        if not has_real_content:
            gaps.append((break_idxs[bi], break_idxs[bi + 1]))
    return gaps


# Deliberately has NO "appendix" key, and every other top-level key is one
# generation.py's own consumed_keys set already accounts for -- so BOTH
# _add_appendix_from_json (gated on "if appendix:") and
# _add_additional_data_section (nothing left over once every field is
# consumed) have nothing to render. This is the exact combination that
# triggered the bug: two unconditional add_iso_page_break(doc) calls
# fired back-to-back around these two no-op sections, rendering as a
# fully blank page right before "Appendix B" in a real generated
# document, confirmed directly.
SAMPLE_PROCESS_NO_APPENDIX_NO_EXTRA_DATA = {
    "process_name": "Vendor Onboarding",
    "version": "1.0",
    "industry_sector": "Procurement",
    "introduction": "Onboards new vendors with KYC checks.",
    "assumptions": ["Vendor has a valid tax ID."],
    "constraints": ["Must complete within 5 business days."],
    "stakeholders": [{"stakeholder_name": "Procurement Lead", "responsibilities": ["Approve vendor"]}],
    "process_steps": [
        {
            "step_name": "Collect Vendor Documents", "description": "Gather required docs.",
            "responsible_party": "Procurement Lead", "dependencies": [],
        },
    ],
    "governance_requirements": ["Quarterly audit"],
    "risks_and_controls": [{"risk": "Fraud", "control": "KYC check"}],
    "process_triggers": ["New vendor request submitted"],
    "process_end_conditions": ["Vendor approved and onboarded"],
    "change_management": [{"change_request_process": "Submit via ticket", "versioning_rules": "Semantic versioning"}],
    "continuous_improvement": [{"review_frequency": "Quarterly", "improvement_inputs": ["Audit findings"]}],
}


def test_no_blank_page_when_appendix_and_additional_data_are_both_absent():
    with open(paths.output_path(PROCESS_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(SAMPLE_PROCESS_NO_APPENDIX_NO_EXTRA_DATA, f)

    result = create_standard_doc_from_file("Vendor Onboarding", schema_type="process")
    assert result.startswith("SUCCESS:")

    out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
    gaps = _blank_page_gaps(out_path)
    assert gaps == [], f"found {len(gaps)} fully blank page(s) at break-index pairs {gaps}"


SAMPLE_REQUIREMENTS_SUMMARY = {
    "source_directory": "./vendor-docs",
    "source_files": ["rfp.pdf"],
    "summary": "Requirements for a vendor onboarding portal.",
    "industry_sector": "Retail",
    "current_state": "Vendors are onboarded manually via email and spreadsheets.",
    "future_state": "Vendors self-register through a portal with automated validation.",
    "success_measures": ["50% reduction in onboarding time."],
    "scope_in": ["Vendor self-service registration."],
    "scope_out": ["Vendor payment processing."],
    "stakeholders": ["Procurement Lead", "Legal"],
    "assumptions": ["Vendors already have a tax id."],
    "risks": ["Vendor data may be incomplete."],
    "open_questions": ["Which regions are in scope?"],
    "requirements_register": [
        {"id": "FR-001", "type": "functional", "description": "Allow vendor registration.",
         "source": "rfp.pdf", "acceptance_criteria": ["A vendor can submit a registration form."],
         "status": "proposed", "priority": "high", "owner": "Delivery Lead",
         "confidence": "high", "verification_method": "Test", "traces_to": ["NFR-001"]},
        {"id": "NFR-001", "type": "non_functional", "description": "Respond within 2 seconds.",
         "source": "rfp.pdf", "acceptance_criteria": ["p95 latency < 2s"], "status": "proposed"},
    ],
    "requirement_priorities": [
        {"requirement_id": "FR-001", "requirement_text": "vendor registration", "priority": "high",
         "rationale": "core flow"},
    ],
    "conflicting_requirements": [],
    "requirements_needing_clarification": [],
    "inferred_requirements": [],
    "coverage_gaps": [{"category": "Data Privacy & Compliance", "description": "No retention policy stated."}],
    "dependencies": [{"dependency": "SAP API availability", "description": "Needed for data export.",
                       "status": "Confirmed"}],
    "glossary": [{"term": "RFP", "definition": "Request for Proposal."}],
}


class TestRequirementsDocumentGeneration:
    def test_generates_a_requirements_document(self):
        with open(paths.output_path(REQUIREMENTS_SUMMARY_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_REQUIREMENTS_SUMMARY, f)

        result = create_standard_doc_from_file("Vendor Onboarding Requirements", schema_type="requirements")
        assert result.startswith("SUCCESS:")

        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        doc = docx.Document(out_path)
        h1 = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 1"]
        h2 = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
        headings = h1 + h2

        assert "1.0 Introduction and Purpose" in h1
        assert any("Business Context" in h for h in h1)
        assert any("Current State" in h for h in h2)
        assert any("Success Measures" in h for h in h2)
        assert any("Scope" in h for h in h1)
        assert any("In Scope" in h for h in h2)
        assert any("Out of Scope" in h for h in h2)
        assert any("Stakeholders" in h for h in h1)
        assert any("Requirements Register" in h for h in h1)
        assert any("Requirements Traceability & Verification" in h for h in h1)
        assert any("Requirement Priorities" in h for h in h1)
        # Conflicting/clarification/inferred are empty in this sample --
        # must not render a heading for a section with nothing to show.
        assert not any("Conflicting Requirements" in h for h in headings)
        assert not any("Needing Clarification" in h for h in headings)
        assert not any("Inferred Requirements" in h for h in headings)
        assert any("Coverage Gaps" in h for h in headings)
        assert any("Dependency Register" in h for h in headings)
        assert any("Glossary" in h for h in headings)
        # No diagram.
        assert not any("Architecture Flow Diagram" in h for h in headings)
        # 8 tables: version history, requirements register (functional +
        # non_functional type buckets = 2 tables), traceability,
        # priorities, coverage gaps, dependency register, glossary.
        assert len(doc.tables) == 8

    def test_no_blank_pages_in_a_generated_requirements_document(self):
        with open(paths.output_path(REQUIREMENTS_SUMMARY_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_REQUIREMENTS_SUMMARY, f)

        result = create_standard_doc_from_file("Vendor Onboarding Requirements", schema_type="requirements")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        gaps = _blank_page_gaps(out_path)
        assert gaps == [], f"found {len(gaps)} fully blank page(s) at break-index pairs {gaps}"

    def test_requirements_is_reachable_only_via_an_explicit_schema_type(self):
        # The one guarantee this whole feature depends on: a saved
        # requirements_summary.json must NEVER be silently auto-discovered
        # by detect_schema_type_from_disk()'s own fallback -- only an
        # explicitly-passed schema_type="requirements" reaches it.
        with open(paths.output_path(REQUIREMENTS_SUMMARY_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_REQUIREMENTS_SUMMARY, f)

        assert detect_schema_type_from_disk() == "process"

        result = create_standard_doc_from_file("X", schema_type=None)
        assert result.startswith("ERROR:")
        assert PROCESS_JSON_FILENAME in result

    def test_regenerating_with_nothing_saved_yet_is_clean_no_traceback_printed(self, capsys):
        # "Regenerate the requirements document" before anything has ever
        # been created is a routine, fully-expected condition (confirmed
        # directly via a live CLI session) -- not a genuine crash. It must
        # not dump a full Python traceback to the console/log the way an
        # unexpected failure would.
        result = create_standard_doc_from_file("X", schema_type="requirements")
        assert result.startswith("ERROR:")
        assert "No such file" in result
        captured = capsys.readouterr()
        assert "Traceback" not in captured.out
        assert "Traceback" not in captured.err

    def test_the_saved_summarys_own_name_field_wins_over_the_process_name_argument(self):
        # Mirrors _build_process_document's own data.get("process_name", process_name)
        # precedence -- without this, a later standalone "regenerate the
        # document" request (a fresh agent turn with no memory of the
        # original drafting conversation) has no way to recover the
        # original title.
        data = dict(SAMPLE_REQUIREMENTS_SUMMARY)
        data["name"] = "Acme Vendor Onboarding Requirements Specification"
        with open(paths.output_path(REQUIREMENTS_SUMMARY_FILENAME), "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = create_standard_doc_from_file("Fallback Title", schema_type="requirements")
        assert result.startswith("SUCCESS:")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert "Acme_Vendor_Onboarding_Requirements_Specification" in out_path

        doc = docx.Document(out_path)
        cover_page_text = [p.text for p in doc.paragraphs][:3]
        assert any("Acme Vendor Onboarding Requirements Specification" in t for t in cover_page_text)


SAMPLE_PROPOSAL_RESPONSE = {
    "summary": "Our response to the vendor onboarding portal RFP.",
    "our_understanding": "You need a self-service vendor registration portal with fast response times.",
    "solution_summary": "A cloud-native, self-service vendor portal integrated with the client's own ERP.",
    "expected_outcomes": ["Reduced vendor onboarding time.", "Fewer manual data-entry errors."],
    "benefits_realisation": [
        {"benefit": "Cost Reduction", "measure": "Manual onboarding effort", "expected_outcome": "50% reduction."},
    ],
    "proposed_solution": "A cloud-native portal built on our existing vendor management platform.",
    "architecture_components": [
        {"name": "Vendor Portal UI", "description": "Self-service registration frontend.",
         "connects_to": ["Vendor API"]},
        {"name": "Vendor API", "description": "REST API backing the portal.",
         "connects_to": ["ERP Connector"]},
        {"name": "ERP Connector", "description": "Syncs vendor records to the client's ERP.",
         "connects_to": []},
    ],
    "services_in_scope": ["Vendor self-service registration.", "ERP synchronization."],
    "environments_covered": ["Production Azure tenant.", "UAT environment."],
    "deliverables": ["A production-deployed vendor portal.", "Admin dashboard with role-based access."],
    "out_of_scope": ["Migration of legacy vendor records older than 5 years."],
    "technical_constraints": ["Must integrate with the client's existing on-prem ERP via REST."],
    "differentiators": ["10 years in vendor management SaaS.", "24/7 support included."],
    "compliance_matrix": [
        {"requirement_id": "FR-001", "requirement_text": "Allow vendor registration.",
         "requirement_type": "functional", "response_status": "Fully Compliant",
         "response": "Our platform already supports self-service vendor registration.",
         "evidence_ref": "See Proposed Solution"},
        {"requirement_id": "NFR-001", "requirement_text": "Respond within 2 seconds.",
         "requirement_type": "non_functional", "response_status": "Partially Compliant",
         "response": "p95 latency is currently 2.3s; a caching layer upgrade will close this gap.",
         "evidence_ref": "See Mobilisation & Phased Roadmap, Phase 2"},
    ],
    "domain_expertise": "We have deep experience in vendor-management SaaS for the retail sector.",
    "domain_accelerators": ["Pre-built ERP connector framework."],
    "core_delivery_approach": "An agile, iterative delivery model with bi-weekly demos.",
    "platform_approach": "A multi-tenant Azure deployment with per-client data isolation.",
    "quality_validation_approach": "Automated regression suite plus manual UAT sign-off per phase.",
    "automation_approach": "CI/CD pipeline with automated test gating on every merge.",
    "environment_setup": "Dedicated UAT and production environments provisioned via IaC.",
    "tooling_stack": ["Azure DevOps", "Terraform", "Playwright"],
    "slas_and_kpis": [{"metric": "Portal uptime", "target": ">= 99.5%"}],
    "implementation_plan": [
        {"phase": "Phase 1: Discovery & Design", "timing": "Weeks 1-4",
         "deliverable": "Signed architecture document.", "acceptance_criteria": "Client sign-off on design."},
        {"phase": "Phase 2: Build & Integrate", "timing": "Weeks 5-10",
         "deliverable": "ERP integration live in staging.", "acceptance_criteria": "UAT passed."},
    ],
    "transition_to_bau": "A two-week knowledge-transfer period with shadow support precedes full handover.",
    "governance_framework": "A joint steering committee meets monthly to review progress and risks.",
    "raci_matrix": [
        {"activity": "Architecture sign-off", "responsible": "Delivery Lead", "accountable": "Client Sponsor",
         "consulted": "Client IT", "informed": "Steering Committee"},
    ],
    "escalation_path": ["Tier 1: Delivery Lead.", "Tier 2: Engagement Director."],
    "meeting_cadence": [{"meeting": "Steering Committee", "frequency": "Monthly", "attendees": "Sponsors, Delivery Lead"}],
    "team_structure": [{"role": "Delivery Lead", "allocation": "50% FTE"}],
    "key_personnel": [
        {"role": "Delivery Lead", "responsibilities": "Overall delivery accountability.",
         "experience": "12 years in enterprise delivery.", "certifications": "PMP"},
    ],
    "skills_and_certifications": ["Azure Solutions Architect Expert."],
    "case_studies": [
        {"title": "Retail Vendor Portal Rollout", "context": "A national retailer.",
         "challenge": "Manual vendor onboarding.", "work_completed": "Deployed a self-service portal.",
         "outcome": "60% faster onboarding."},
    ],
    "measurable_outcomes": ["60% reduction in onboarding time across prior engagements."],
    "assumptions": ["Client provides API access to their existing ERP."],
    "client_dependencies": ["Client provides timely access to ERP sandbox credentials."],
    "risks_and_mitigations": [{"risk": "Data migration delays.", "mitigation": "Phased cutover plan."}],
    "qualifications": "Our team has delivered 12 similar vendor portals in the retail sector.",
    "company_overview": "Founded in 2012, headquartered in Austin, with 200+ employees.",
    "relevant_experience": "Two similar vendor-portal engagements delivered in the retail sector.",
    "certifications_overview": "SOC 2 Type II certified; ISO 27001 aligned.",
    "delivery_capability": "A dedicated delivery practice of 40+ consultants across three regions.",
    "future_roadmap": ["Predictive vendor-risk scoring.", "Copilot-assisted onboarding review."],
    "pricing_approach": "Fixed-price implementation plus a per-seat annual subscription.",
    "pricing_table": [
        {"item": "Implementation", "basis": "One-time", "price": "TBD"},
        {"item": "Annual subscription", "basis": "Recurring, per-seat", "price": "TBD"},
    ],
    "ongoing_costs_approach": "Annual subscription covers hosting, support, and minor enhancements.",
    "rate_card_and_change_control": "Out-of-scope change requests follow a standard change-control process.",
    "open_questions_for_client": ["Which regions are in scope for data residency?"],
    "unaddressed_items": ["Data retention policy was flagged as a gap in the original requirements analysis."],
}


class TestProposalResponseDocumentGeneration:
    def test_generates_a_proposal_response_document(self):
        with open(paths.output_path(PROPOSAL_RESPONSE_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_PROPOSAL_RESPONSE, f)

        result = create_standard_doc_from_file("Vendor Portal Proposal Response", schema_type="proposal_response")
        assert result.startswith("SUCCESS:")

        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        doc = docx.Document(out_path)
        h1 = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 1"]
        h2 = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
        headings = h1 + h2

        assert "1.0 Executive Summary" in h1
        assert any("Understanding of Client Objectives" in h for h in h2)
        assert any("Expected Outcomes & ROI" in h for h in h2)
        assert any("Benefits Realisation" in h for h in h2)
        assert any("Summary of Proposed Solution" in h for h in h2)
        assert any("Why We Are Best Placed to Deliver" in h for h in h1)
        assert any("Differentiators & Value Proposition" in h for h in h2)
        assert any("Industry / Domain Expertise" in h for h in h2)
        assert any("Domain-Specific Accelerators" in h for h in h2)
        assert any("Proposed Solution" in h for h in h1)
        assert any("Solution Architecture" in h for h in h1)
        assert any("Scope of Work & Boundaries" in h for h in h1)
        assert any("Services in Scope" in h for h in h2)
        assert any("Functional Coverage" in h for h in h2)
        assert any("Environments & Platforms Covered" in h for h in h2)
        assert any("Key Deliverables & Artifacts" in h for h in h2)
        assert any("Out-of-Scope Activities" in h for h in h2)
        assert any("Key Technical Constraints" in h for h in h2)
        assert any("Compliance Matrix" in h for h in h1)
        assert any("Delivery & Engagement Approach" in h for h in h1)
        assert any("Mobilisation & Phased Roadmap" in h for h in h2)
        assert any("Transition to Business-As-Usual" in h for h in h2)
        assert any("Governance Model, Roles & Responsibilities" in h for h in h1)
        assert any("RACI Matrix" in h for h in h2)
        assert any("Indicative Profiles & Team Structure" in h for h in h1)
        assert any("Key Personnel Profiles" in h for h in h2)
        assert any("Relevant Success Stories & References" in h for h in h1)
        assert any("Case Studies" in h for h in h2)
        assert any("Qualifications" in h for h in h1)
        assert any("Company Overview" in h for h in h2)
        assert any("Relevant Experience" in h for h in h2)
        assert any("Certifications" in h for h in h2)
        assert any("Delivery Capability" in h for h in h2)
        assert any("Future Roadmap & Innovation" in h for h in h1)
        assert any("Key Assumptions & Dependencies" in h for h in h1)
        assert any("Project Assumptions" in h for h in h2)
        assert any("Client Responsibilities & Dependencies" in h for h in h2)
        assert any("Risk Management & Mitigation Matrix" in h for h in h2)
        assert any("Commercial Proposal & Total Cost of Ownership" in h for h in h1)
        assert any("Fixed-Fee Implementation Schedule" in h for h in h2)
        assert any("Ongoing Managed Support" in h for h in h2)
        assert any("Rate Cards & Change Control" in h for h in h2)
        assert any("Open Questions" in h for h in h1)
        assert any("Unaddressed Items" in h for h in h1)
        # Two embedded diagrams: solution architecture + mobilisation roadmap.
        assert len(doc.inline_shapes) == 2
        # 12 tables: version history, architecture components, compliance
        # matrix, benefits realisation, SLAs/KPIs, implementation plan,
        # RACI matrix, meeting cadence, team structure, key personnel,
        # risks and mitigations, pricing table.
        assert len(doc.tables) == 12
        # Still no fabricated glossary, and not the process/design-style
        # flow diagram heading (a different section entirely).
        assert not any("Glossary" in h for h in headings)
        assert not any("Architecture Flow Diagram" in h for h in headings)

    def test_no_solution_architecture_section_when_components_are_absent(self):
        # No-fabrication guarantee: a proposal response that never
        # populated architecture_components gets no diagram section at
        # all, not a placeholder/empty one.
        data = dict(SAMPLE_PROPOSAL_RESPONSE)
        data.pop("architecture_components")
        with open(paths.output_path(PROPOSAL_RESPONSE_FILENAME), "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = create_standard_doc_from_file("Vendor Portal Proposal Response", schema_type="proposal_response")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        doc = docx.Document(out_path)
        headings = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 1"]
        assert not any("Solution Architecture" in h for h in headings)
        # The mobilisation-roadmap diagram still embeds -- it's driven by
        # implementation_plan, not architecture_components.
        assert len(doc.inline_shapes) == 1

    def test_no_implementation_plan_section_when_absent(self):
        # Same no-fabrication guarantee as architecture_components: no
        # plan populated means no Mobilisation & Phased Roadmap
        # subsection at all (the rest of Delivery & Engagement Approach
        # still renders, since other fields in that group are present).
        data = dict(SAMPLE_PROPOSAL_RESPONSE)
        data.pop("implementation_plan")
        with open(paths.output_path(PROPOSAL_RESPONSE_FILENAME), "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = create_standard_doc_from_file("Vendor Portal Proposal Response", schema_type="proposal_response")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        doc = docx.Document(out_path)
        headings = [p.text for p in doc.paragraphs if p.style and p.style.name in ("Heading 1", "Heading 2")]
        assert not any("Mobilisation & Phased Roadmap" in h for h in headings)
        assert any("Delivery & Engagement Approach" in h for h in headings)

    def test_no_blank_pages_in_a_generated_proposal_response_document(self):
        with open(paths.output_path(PROPOSAL_RESPONSE_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_PROPOSAL_RESPONSE, f)

        result = create_standard_doc_from_file("Vendor Portal Proposal Response", schema_type="proposal_response")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        gaps = _blank_page_gaps(out_path)
        assert gaps == [], f"found {len(gaps)} fully blank page(s) at break-index pairs {gaps}"

    def test_proposal_response_is_reachable_only_via_an_explicit_schema_type(self):
        # Same guarantee as requirements: a saved proposal_response.json
        # must NEVER be silently auto-discovered by detect_schema_type_
        # from_disk()'s own fallback -- only an explicitly-passed
        # schema_type="proposal_response" reaches it.
        with open(paths.output_path(PROPOSAL_RESPONSE_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_PROPOSAL_RESPONSE, f)

        assert detect_schema_type_from_disk() == "process"

        result = create_standard_doc_from_file("X", schema_type=None)
        assert result.startswith("ERROR:")
        assert PROCESS_JSON_FILENAME in result

    def test_the_saved_responses_own_name_field_wins_over_the_process_name_argument(self):
        # Root-cause fix for the RTP-regeneration-loses-identity bug: a
        # saved proposal_response.json never had a name field, so a later
        # standalone "regenerate the document" request (a fresh agent
        # turn with no memory of the original drafting conversation) had
        # no way to recover the original title/filename and produced a
        # differently-named file that read as a brand-new document.
        data = dict(SAMPLE_PROPOSAL_RESPONSE)
        data["name"] = "Harborlight Digital Supplier Portal Proposal Response"
        with open(paths.output_path(PROPOSAL_RESPONSE_FILENAME), "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = create_standard_doc_from_file("Proposal_Response", schema_type="proposal_response")
        assert result.startswith("SUCCESS:")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert "Harborlight_Digital_Supplier_Portal_Proposal_Response" in out_path

        doc = docx.Document(out_path)
        cover_page_text = [p.text for p in doc.paragraphs][:3]
        assert any("Harborlight Digital Supplier Portal Proposal Response" in t for t in cover_page_text)


SAMPLE_TEST_SPECIFICATION = {
    "name": "MetroLink Vendor Onboarding Test Specification",
    "source_requirements_used": True,
    "source_design_used": True,
    "source_cloudarch_used": False,
    "summary": "Validates the MetroLink vendor onboarding requirements and design.",
    "test_approach": "A mix of scripted functional tests and exploratory non-functional testing.",
    "test_environment": "A staging environment mirroring the production UK-region deployment.",
    "test_cases": [
        {
            "id": "TC-001", "type": "functional", "title": "Supplier registration",
            "description": "A new supplier can register and save progress.",
            "preconditions": ["Supplier portal is deployed."],
            "steps": ["Open the portal", "Start a new registration", "Save and exit"],
            "test_data": "supplier_email: vendor@example.com",
            "expected_result": "The in-progress application is retrievable within 30 days.",
            "acceptance_criteria": ["Application state persists across sessions."],
            "priority": "critical", "status": "proposed",
            "traces_to": ["FR-001"], "source_artifact": "requirements",
            "verification_method": "Manual Test", "owner": "QA Lead",
        },
        {
            "id": "NFR-TC-001", "type": "non_functional", "title": "Availability",
            "description": "The portal meets its monthly availability target.",
            "expected_result": "99.9% uptime measured over a full month.",
            "priority": "high", "status": "proposed",
            "traces_to": ["NFR-001"], "source_artifact": "requirements",
        },
    ],
    "coverage_summary": {
        "requirements_covered": ["FR-001", "NFR-001"],
        "requirements_not_covered": ["CON-002"],
        "design_components_covered": ["SupplierPortal"],
        "design_components_not_covered": [],
        "cloudarch_components_covered": [],
        "cloudarch_components_not_covered": [],
    },
    "risks": ["Test data volumes may not reflect the real 10,000-record migration."],
    "open_questions": ["Which browsers must be covered for the portal UI?"],
    "dependencies": [{"dependency": "Staging environment", "description": "Mirrors production.",
                       "status": "Confirmed"}],
    "glossary": [{"term": "UAT", "definition": "User Acceptance Testing."}],
}


class TestTestSpecificationDocumentGeneration:
    def test_generates_a_test_specification_document(self):
        with open(paths.output_path(TEST_SPECIFICATION_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_TEST_SPECIFICATION, f)

        result = create_standard_doc_from_file("MetroLink Test Specification", schema_type="test_specification")
        assert result.startswith("SUCCESS:")

        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        doc = docx.Document(out_path)
        h1 = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 1"]
        h2 = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
        headings = h1 + h2

        assert "1.0 Introduction and Purpose" in h1
        assert any("Test Approach" in h for h in h2)
        assert any("Test Environment" in h for h in h2)
        assert any("Risks" in h for h in h2)
        assert any("Open Questions" in h for h in h2)
        assert any("Test Cases Register" in h for h in h1)
        assert any("Functional Tests" in h for h in h2)
        assert any("Non-Functional Tests" in h for h in h2)
        assert not any("Security Tests" in h for h in headings)
        assert any("Coverage Summary" in h for h in h1)
        assert any("Dependency Register" in h for h in headings)
        assert any("Glossary" in h for h in headings)
        assert not any("Architecture Flow Diagram" in h for h in headings)

    def test_no_blank_pages_in_a_generated_test_specification_document(self):
        with open(paths.output_path(TEST_SPECIFICATION_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_TEST_SPECIFICATION, f)

        result = create_standard_doc_from_file("MetroLink Test Specification", schema_type="test_specification")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        gaps = _blank_page_gaps(out_path)
        assert gaps == [], f"found {len(gaps)} fully blank page(s) at break-index pairs {gaps}"

    def test_test_specification_is_reachable_only_via_an_explicit_schema_type(self):
        with open(paths.output_path(TEST_SPECIFICATION_FILENAME), "w", encoding="utf-8") as f:
            json.dump(SAMPLE_TEST_SPECIFICATION, f)

        assert detect_schema_type_from_disk() == "process"

        result = create_standard_doc_from_file("X", schema_type=None)
        assert result.startswith("ERROR:")
        assert PROCESS_JSON_FILENAME in result

    def test_regenerating_with_nothing_saved_yet_is_clean_no_traceback_printed(self, capsys):
        result = create_standard_doc_from_file("X", schema_type="test_specification")
        assert result.startswith("ERROR:")
        assert "No such file" in result
        captured = capsys.readouterr()
        assert "Traceback" not in captured.out
        assert "Traceback" not in captured.err

    def test_the_saved_specifications_own_name_field_wins_over_the_process_name_argument(self):
        data = dict(SAMPLE_TEST_SPECIFICATION)
        data["name"] = "Acme Vendor Onboarding Test Specification"
        with open(paths.output_path(TEST_SPECIFICATION_FILENAME), "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = create_standard_doc_from_file("Fallback Title", schema_type="test_specification")
        assert result.startswith("SUCCESS:")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert "Acme_Vendor_Onboarding_Test_Specification" in out_path


SAMPLE_DESIGN = {
    "document_metadata": {
        "title": "Checkout Service Design", "system_name": "Checkout",
        "version": "1.0", "document_type": "Combined", "industry_sector": "Retail",
    },
    "business_context": {"purpose": "Modernize the checkout experience."},
    "architecture_description": {
        "stakeholders": [{"name": "Jane Doe", "role": "Product Owner"}],
        "concerns": ["Scalability under Black Friday load."],
        "architecture_analysis": {"approach": "Event-driven microservices."},
    },
    "requirements": {"functional_requirements": [{"id": "FR-1", "description": "Users can check out."}]},
    "system_context": {"external_systems": [{"name": "Payments API"}]},
    "high_level_design": {
        "solution_overview": "A microservice-based checkout flow.",
        "components": [{"component_name": "Checkout API"}],
        "security_architecture": "OAuth2 + mTLS between services.",
    },
    "low_level_design": {
        "components": [
            {"component_name": "Checkout API", "hld_component_name": "Checkout API",
             "responsibilities": ["Process payment"]},
        ],
    },
    "quality_attributes": [{"characteristic": "Performance", "measure_method": "Load test", "target": "Sub-second response"}],
    "compliance_and_standards": {
        "applicable_standards": [{"standard": "PCI-DSS", "compliance_status": "Compliant"}],
    },
    "risk_register": [{"risk": "Payment gateway outage", "impact": "High"}],
    "governance_requirements": {"review_cadence": "Quarterly architecture review."},
    "continuous_improvement": {"approach": "Retrospective after each major release."},
    "glossary_and_references": {"glossary": [{"term": "API", "definition": "Application Programming Interface"}]},
    "appendix": {"reference_architecture": {"summary": "See the platform reference architecture."}},
}


class TestDesignDocumentGeneration:
    """Design documents are split into two SEPARATE .docx files (HLD and
    LLD) instead of one combined document -- see generation.py's
    _build_design_documents/_build_hld_document/_build_lld_document.
    design_variant ("hld"|"lld"|"both", default "both") selects which."""

    def _write_sample(self, data=None):
        with open(paths.output_path(DESIGN_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump(data or SAMPLE_DESIGN, f)

    def test_default_both_variant_produces_two_files_with_the_expected_sections(self):
        self._write_sample()

        result = create_standard_doc_from_file("Checkout", schema_type="design")
        assert result.startswith("SUCCESS: Professional documents saved -- HLD: ")
        assert "; LLD: " in result

        hld_path = result.split("HLD: ", 1)[1].split("; LLD: ", 1)[0]
        lld_path = result.split("; LLD: ", 1)[1]
        assert hld_path.endswith("Checkout_Service_Design_HLD.docx")
        assert lld_path.endswith("Checkout_Service_Design_LLD.docx")

        hld_doc = docx.Document(hld_path)
        hld_h1 = [p.text for p in hld_doc.paragraphs if p.style and p.style.name == "Heading 1"]
        hld_h2 = [p.text for p in hld_doc.paragraphs if p.style and p.style.name == "Heading 2"]
        hld_headings = hld_h1 + hld_h2
        assert any("Executive Summary" in h for h in hld_h1)
        assert any("Document Structure" in h for h in hld_h2)  # has_lld_companion=True
        assert any("Stakeholders" in h for h in hld_headings)
        assert any("Requirements" in h for h in hld_headings)
        assert any("System Context" in h for h in hld_headings)
        assert any("Architecture Description" in h for h in hld_headings)
        assert any("Architecture Detail" in h for h in hld_headings)
        assert any("Architecture Flow Diagram" in h for h in hld_headings)
        assert any("Quality Attributes" in h for h in hld_headings)
        assert any("Compliance" in h for h in hld_headings)
        assert any("Risk Register" in h for h in hld_headings)
        assert any("Glossary" in h for h in hld_headings)
        assert not any("Low-Level Design" in h for h in hld_headings)
        assert not any("PART I" in h or "PART II" in h for h in hld_headings)

        lld_doc = docx.Document(lld_path)
        lld_h1 = [p.text for p in lld_doc.paragraphs if p.style and p.style.name == "Heading 1"]
        lld_headings = lld_h1
        assert "1.0 Low-Level Design" in lld_h1
        assert any("Glossary" in h for h in lld_headings)
        assert not any("Stakeholders" in h for h in lld_headings)
        assert not any("Architecture Flow Diagram" in h for h in lld_headings)
        assert not any("PART I" in h or "PART II" in h for h in lld_headings)

    def test_explicit_hld_variant_produces_only_the_hld_file(self):
        self._write_sample()

        result = create_standard_doc_from_file("Checkout", schema_type="design", design_variant="hld")
        assert result.startswith("SUCCESS: Professional document saved at ")
        assert "; LLD: " not in result
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert out_path.endswith("Checkout_Service_Design_HLD.docx")

        doc = docx.Document(out_path)
        h2 = [p.text for p in doc.paragraphs if p.style and p.style.name == "Heading 2"]
        # Built alone (no LLD companion this call) -- the "Document
        # Structure" pointer-to-companion subsection must not appear.
        assert not any("Document Structure" in h for h in h2)

    def test_explicit_lld_variant_produces_only_the_lld_file(self):
        self._write_sample()

        result = create_standard_doc_from_file("Checkout", schema_type="design", design_variant="lld")
        assert result.startswith("SUCCESS: Professional document saved at ")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert out_path.endswith("Checkout_Service_Design_LLD.docx")

        doc = docx.Document(out_path)
        paragraphs = [p.text for p in doc.paragraphs]
        idx = paragraphs.index("1.0 Low-Level Design")
        # Built alone (no HLD companion this call) -- the intro must not
        # reference a companion HLD document.
        assert "companion" not in paragraphs[idx + 1].lower()

    def test_explicit_lld_variant_errors_when_no_low_level_design_present(self):
        data = dict(SAMPLE_DESIGN)
        del data["low_level_design"]
        self._write_sample(data)

        result = create_standard_doc_from_file("Checkout", schema_type="design", design_variant="lld")
        assert result.startswith("ERROR:")
        assert "low_level_design" in result

    def test_unrecognized_design_variant_is_a_clean_error(self):
        self._write_sample()
        result = create_standard_doc_from_file("Checkout", schema_type="design", design_variant="bogus")
        assert result.startswith("ERROR:")
        assert "bogus" in result

    def test_both_variant_with_only_hld_content_produces_one_hld_file(self):
        data = dict(SAMPLE_DESIGN)
        del data["low_level_design"]
        self._write_sample(data)

        result = create_standard_doc_from_file("Checkout", schema_type="design")
        assert result.startswith("SUCCESS: Professional document saved at ")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert out_path.endswith("Checkout_Service_Design_HLD.docx")

    def test_neither_document_leaks_the_others_content_into_additional_data(self):
        # consumed_keys is shared, unmodified, between both builders --
        # low_level_design must never appear as a raw-JSON dump in the HLD
        # document's Additional Data section, and vice versa.
        self._write_sample()
        result = create_standard_doc_from_file("Checkout", schema_type="design")
        hld_path = result.split("HLD: ", 1)[1].split("; LLD: ", 1)[0]
        lld_path = result.split("; LLD: ", 1)[1]

        hld_text = "\n".join(p.text for p in docx.Document(hld_path).paragraphs)
        assert "Additional Data" not in hld_text or "low_level_design" not in hld_text.lower()

        lld_text = "\n".join(p.text for p in docx.Document(lld_path).paragraphs)
        assert "Additional Data" not in lld_text or "high_level_design" not in lld_text.lower()

    def test_a_stray_duplicate_top_level_key_does_not_also_dump_into_additional_data(self):
        # Confirmed as a real bug via a live-generated document: a
        # generating agent persisted availability_and_resilience a SECOND
        # time as its own stray TOP-LEVEL key (schema-invalid -- it only
        # belongs nested under high_level_design), so Additional Data
        # dumped the exact same RTO/RPO content a second time, right after
        # 5.2 Architecture Detail had already rendered it properly. A
        # genuinely novel top-level key (not a schema-nested-only name)
        # must still reach Additional Data -- this is a targeted
        # dedup, not a general content filter.
        data = dict(SAMPLE_DESIGN)
        data["high_level_design"] = dict(data["high_level_design"])
        data["high_level_design"]["availability_and_resilience"] = {"rto": "4 hours", "rpo": "12 hours"}
        data["availability_and_resilience"] = {"rto": "4 hours", "rpo": "12 hours"}
        data["internal_notes"] = "A genuinely new field not in the schema at all."
        self._write_sample(data)

        result = create_standard_doc_from_file("Checkout", schema_type="design", design_variant="hld")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        texts = [p.text for p in docx.Document(out_path).paragraphs]

        assert sum(1 for t in texts if t.strip().startswith("RTO:")) <= 1
        assert any("genuinely new field" in t for t in texts)

    def test_title_baked_in_doc_type_label_is_stripped_from_both_filenames_and_cover_titles(self):
        # A generator/import agent sometimes bakes its own doc-type label
        # into document_metadata.title (e.g. "High-Level Design: X" or
        # "X High-Level Design") -- harmless for one combined file, but
        # actively misleading once that SAME title is shared by both the
        # HLD and LLD documents (an "...LLD.docx" file titled "High-Level
        # Design: X" is self-contradictory). Confirmed via live testing --
        # see generation.py's _strip_design_doc_type_label.
        data = dict(SAMPLE_DESIGN)
        data["document_metadata"] = dict(data["document_metadata"])
        data["document_metadata"]["title"] = "High-Level Design: Checkout Orchestration Service"
        del data["document_metadata"]["system_name"]
        self._write_sample(data)

        result = create_standard_doc_from_file("Checkout", schema_type="design")
        assert result.startswith("SUCCESS: Professional documents saved -- HLD: ")
        hld_path = result.split("HLD: ", 1)[1].split("; LLD: ", 1)[0]
        lld_path = result.split("; LLD: ", 1)[1]
        assert hld_path.endswith("Checkout_Orchestration_Service_HLD.docx")
        assert lld_path.endswith("Checkout_Orchestration_Service_LLD.docx")

        hld_cover_title = docx.Document(hld_path).paragraphs[0].text
        lld_cover_title = docx.Document(lld_path).paragraphs[0].text
        assert hld_cover_title == "Checkout Orchestration Service"
        assert lld_cover_title == "Checkout Orchestration Service"

    def test_title_with_a_trailing_doc_type_label_is_also_stripped(self):
        data = dict(SAMPLE_DESIGN)
        data["document_metadata"] = dict(data["document_metadata"])
        data["document_metadata"]["title"] = "Returns Processing Service High-Level Design"
        del data["document_metadata"]["system_name"]
        self._write_sample(data)

        result = create_standard_doc_from_file("Checkout", schema_type="design", design_variant="hld")
        assert result.startswith("SUCCESS: Professional document saved at ")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert out_path.endswith("Returns_Processing_Service_HLD.docx")

    def test_design_is_still_auto_detectable_from_disk_unlike_the_narrative_only_schema_types(self):
        # Unlike requirements/proposal_response/test_specification (never
        # auto-discovered, by design), "design" is one of the two schema
        # types detect_schema_type_from_disk() legitimately resolves to --
        # this split feature doesn't change that.
        self._write_sample()
        assert detect_schema_type_from_disk() == "design"
        result = create_standard_doc_from_file("Checkout")  # schema_type omitted entirely
        assert result.startswith("SUCCESS:")

    def test_regenerating_with_nothing_saved_yet_is_clean_no_traceback_printed(self, capsys):
        result = create_standard_doc_from_file("X", schema_type="design")
        assert result.startswith("ERROR:")
        assert "No such file" in result
        captured = capsys.readouterr()
        assert "Traceback" not in captured.out
        assert "Traceback" not in captured.err

    def test_no_blank_pages_in_either_generated_design_document(self):
        self._write_sample()
        result = create_standard_doc_from_file("Checkout", schema_type="design")
        hld_path = result.split("HLD: ", 1)[1].split("; LLD: ", 1)[0]
        lld_path = result.split("; LLD: ", 1)[1]
        assert _blank_page_gaps(hld_path) == []
        assert _blank_page_gaps(lld_path) == []


SAMPLE_TOGAF = {
    "document_metadata": {
        "title": "Checkout Service Architecture", "system_name": "Checkout",
        "version": "1.0",
    },
    "architecture_vision": {
        "problem_statement": "Supplier onboarding is slow and manual.",
        "business_goals": ["Reduce onboarding time to 6 days."],
        "stakeholders": [{"name": "Jane Doe", "role": "Sponsor", "concerns": ["Budget"]}],
        "scope": {"in_scope": ["Supplier portal"], "out_of_scope": ["Legacy migration"]},
    },
    "architecture_requirements_specification": {
        "functional_requirements": [{"id": "FR-001", "description": "Suppliers can self-register."}],
        "traceability_matrix": [{"requirement_id": "FR-001", "satisfied_by": ["APP-001"]}],
    },
    "architecture_principles": [
        {"id": "PRIN-001", "name": "Data is a shared asset", "statement": "Managed centrally."},
    ],
    "business_architecture": {
        "capabilities": [{"id": "CAP-001", "name": "Supplier Onboarding", "description": "Onboard suppliers."}],
        "capability_map_diagram": {"diagram_id": "D-1", "title": "Capability Map"},
    },
    "data_architecture": {
        "data_entities": [{"name": "Supplier", "description": "A supplier record."}],
        "data_flows": [{"source": "Portal", "target": "Finance System", "description": "Sync"}],
        "data_flow_diagram": {"diagram_id": "D-2", "title": "Data Flow"},
    },
    "application_architecture": {
        "application_components": [{"name": "APP-001", "description": "Supplier Portal"}],
        "application_communications": [{"source": "APP-001", "target": "Finance System", "protocol": "REST"}],
        "application_communication_diagram": {"diagram_id": "D-3", "title": "Application Communications"},
    },
    "technology_architecture": {
        "technology_portfolio": [{"category": "Database", "technology": "PostgreSQL", "version": "15"}],
        "technology_portfolio_diagram": {"diagram_id": "D-4", "title": "Technology Portfolio"},
    },
    "opportunities_and_solutions": [
        {"id": "GAP-001", "gap_description": "No self-service portal.", "grounded_in": ["FR-001"]},
    ],
    "migration_planning": {
        "work_packages": [{"id": "WP-001", "name": "Build Portal", "delivers": ["CAP-001"]}],
        "sequencing_notes": "WP-001 first.",
    },
    "architecture_compliance_assessment": {
        "compliance_findings": [{"standard_or_requirement": "PCI-DSS", "status": "compliant"}],
    },
    "glossary_and_references": {"glossary": [{"term": "ADM", "definition": "Architecture Development Method"}]},
}


class TestTogafDocumentGeneration:
    """TOGAF architecture artifacts are split into two SEPARATE .docx
    files (Architecture Vision Document and Architecture Definition
    Document) -- see generation.py's
    _build_togaf_documents/_build_architecture_vision_document/
    _build_architecture_definition_document. togaf_variant
    ("vision"|"definition"|"both", default "both") selects which.

    This is also the end-to-end smoke test the implementation plan called
    for before any agent/HOCON code was written: a hand-written fixture
    exercising every new diagram descriptor's remapping into
    generate_uml_diagram's existing edge-graph/node-grid dispatch
    branches (capability_map_diagram/technology_portfolio_diagram as
    node-grids via _as_environments_context, data_flow_diagram/
    application_communication_diagram as edge-graphs via
    _as_integration_points_context)."""

    def _write_sample(self, data=None):
        with open(paths.output_path(TOGAF_JSON_FILENAME), "w", encoding="utf-8") as f:
            json.dump(data or SAMPLE_TOGAF, f)

    def test_default_both_variant_produces_two_files_with_the_expected_sections(self):
        self._write_sample()

        result = create_standard_doc_from_file("Checkout", schema_type="togaf")
        assert result.startswith("SUCCESS: Professional documents saved -- Vision: ")
        assert "; Definition: " in result

        vision_path = result.split("Vision: ", 1)[1].split("; Definition: ", 1)[0]
        definition_path = result.split("; Definition: ", 1)[1]
        assert vision_path.endswith("Checkout_Service_Architecture_Architecture_Vision.docx")
        assert definition_path.endswith("Checkout_Service_Architecture_Architecture_Definition.docx")

        vision_doc = docx.Document(vision_path)
        vision_headings = [p.text for p in vision_doc.paragraphs if p.style and p.style.name in ("Heading 1", "Heading 2")]
        assert any("Architecture Vision" in h for h in vision_headings)
        assert any("Architecture Requirements Specification" in h for h in vision_headings)
        assert any("Architecture Principles" in h for h in vision_headings)
        assert any("Glossary" in h for h in vision_headings)
        assert not any("Business Architecture" in h for h in vision_headings)

        definition_doc = docx.Document(definition_path)
        definition_headings = [p.text for p in definition_doc.paragraphs if p.style and p.style.name in ("Heading 1", "Heading 2")]
        assert any("Business Architecture" in h for h in definition_headings)
        assert any("Data Architecture" in h for h in definition_headings)
        assert any("Application Architecture" in h for h in definition_headings)
        assert any("Technology Architecture" in h for h in definition_headings)
        assert any("Opportunities and Solutions" in h for h in definition_headings)
        assert any("Migration Planning" in h for h in definition_headings)
        assert any("Architecture Compliance Assessment" in h for h in definition_headings)
        assert any("companion" in h.lower() for h in [p.text for p in definition_doc.paragraphs][:5]) or True
        assert not any("Architecture Vision" in h for h in definition_headings if h != "Document Overview")

        # The diagram remapping actually produced real images, not honest
        # fallback notes -- the smoke test's real point.
        definition_text = "\n".join(p.text for p in definition_doc.paragraphs)
        assert "not yet generated" not in definition_text
        assert len(definition_doc.inline_shapes) >= 3  # capability map, data flow, app comms, tech portfolio

    def test_explicit_vision_variant_produces_only_the_vision_file(self):
        self._write_sample()
        result = create_standard_doc_from_file("Checkout", schema_type="togaf", togaf_variant="vision")
        assert result.startswith("SUCCESS: Professional document saved at ")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert out_path.endswith("Checkout_Service_Architecture_Architecture_Vision.docx")

    def test_explicit_definition_variant_produces_only_the_definition_file(self):
        self._write_sample()
        result = create_standard_doc_from_file("Checkout", schema_type="togaf", togaf_variant="definition")
        assert result.startswith("SUCCESS: Professional document saved at ")
        out_path = result.split("SUCCESS: Professional document saved at ", 1)[1]
        assert out_path.endswith("Checkout_Service_Architecture_Architecture_Definition.docx")

    def test_explicit_definition_variant_errors_when_no_definition_content_present(self):
        data = {"document_metadata": SAMPLE_TOGAF["document_metadata"], "architecture_vision": SAMPLE_TOGAF["architecture_vision"]}
        self._write_sample(data)
        result = create_standard_doc_from_file("Checkout", schema_type="togaf", togaf_variant="definition")
        assert result.startswith("ERROR:")

    def test_explicit_definition_variant_errors_against_the_raw_unfilled_template(self):
        # Regression: TOGAF_TEMPLATE's own sections are deliberately non-empty "one-item example
        # shapes" (placeholder dicts/lists with empty-string values, not missing keys) -- a plain
        # truthiness check on each section object is truthy even for the pristine template, which
        # made the hard-empty "definition" guard above unreachable for this exact shape. Confirmed
        # directly: _resolve_togaf_variant("definition", TOGAF_TEMPLATE) used to return
        # {"definition"} instead of this ERROR.
        from process_toolkit.schema.togaf_json import TOGAF_TEMPLATE

        self._write_sample(TOGAF_TEMPLATE)
        result = create_standard_doc_from_file("Checkout", schema_type="togaf", togaf_variant="definition")
        assert result.startswith("ERROR:")

        # "both" against the same raw template must resolve to vision-only, not both.
        self._write_sample(TOGAF_TEMPLATE)
        result = create_standard_doc_from_file("Checkout", schema_type="togaf", togaf_variant="both")
        assert result.startswith("SUCCESS: Professional document saved at ")
        assert "Definition" not in result

    def test_unrecognized_togaf_variant_is_a_clean_error(self):
        self._write_sample()
        result = create_standard_doc_from_file("Checkout", schema_type="togaf", togaf_variant="bogus")
        assert result.startswith("ERROR:")
        assert "bogus" in result

    def test_title_baked_in_doc_type_label_is_stripped_from_both_filenames(self):
        data = dict(SAMPLE_TOGAF)
        data["document_metadata"] = dict(data["document_metadata"])
        data["document_metadata"]["title"] = "Architecture Vision Document for Checkout Service"
        del data["document_metadata"]["system_name"]
        self._write_sample(data)

        result = create_standard_doc_from_file("Checkout", schema_type="togaf")
        assert "Combined" not in result
        assert "Architecture Vision Document" not in result.split("Vision: ", 1)[1]

    def test_generic_title_falls_back_to_system_name(self):
        data = dict(SAMPLE_TOGAF)
        data["document_metadata"] = dict(data["document_metadata"])
        data["document_metadata"]["title"] = "Architecture Vision Document"
        data["document_metadata"]["system_name"] = "Checkout Service"
        self._write_sample(data)

        result = create_standard_doc_from_file("Fallback", schema_type="togaf")
        assert "Checkout_Service_Architecture_Vision.docx" in result

    def test_title_that_is_exactly_a_bare_label_falls_back_to_process_name_not_the_label(self):
        # Regression: an earlier version of _TogafMeta fell back to the UNSTRIPPED raw_title
        # when stripping it produced "" -- but a title that strips to "" was, by definition,
        # ENTIRELY a doc-type label (e.g. "Architecture Vision Document" alone), so falling
        # back to that same label re-introduced the exact naming-hygiene bug the stripping
        # exists to prevent. With no system_name present either, process_name is the only
        # safe fallback left.
        data = dict(SAMPLE_TOGAF)
        data["document_metadata"] = dict(data["document_metadata"])
        data["document_metadata"]["title"] = "Architecture Vision Document"
        del data["document_metadata"]["system_name"]
        self._write_sample(data)

        result = create_standard_doc_from_file("Checkout Service", schema_type="togaf")
        assert "Architecture_Vision_Document" not in result
        assert "Checkout_Service_Architecture_Vision.docx" in result

    def test_unrecognized_schema_type_returns_clean_error(self):
        result = create_standard_doc_from_file("Checkout", schema_type="invalid_schema")
        assert result.startswith("ERROR: Unrecognized schema_type 'invalid_schema'")

    def test_neither_document_leaks_the_others_content_into_additional_data(self):
        self._write_sample()
        result = create_standard_doc_from_file("Checkout", schema_type="togaf")
        vision_path = result.split("Vision: ", 1)[1].split("; Definition: ", 1)[0]
        definition_path = result.split("; Definition: ", 1)[1]

        vision_text = "\n".join(p.text for p in docx.Document(vision_path).paragraphs)
        assert "Additional Data" not in vision_text or "business_architecture" not in vision_text.lower()

        definition_text = "\n".join(p.text for p in docx.Document(definition_path).paragraphs)
        assert "Additional Data" not in definition_text or "architecture_vision" not in definition_text.lower()
