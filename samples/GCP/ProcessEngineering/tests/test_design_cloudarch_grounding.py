"""Regression coverage for a real production bug: asked to "create an HLD
based on this cloud architecture" (an uploaded drawio diagram with no
stated business purpose, just infrastructure), Design_Doc_Agent fabricated
an entirely unrelated business domain ("Global Inventory & Order
Management System") out of nothing -- confirmed via a live trace on the
Neuro-San sibling port (which shares this same design-pipeline logic and
schema) showing the orchestrator DID pass accurate infrastructure detail
through, and the design-generation agent still invented a business
narrative to fill business_context/document_metadata.

Two independent problems, fixed together here, mirroring the sibling
Neuro-San port's registries/design.hocon fix:
1. Design_Doc_Analysis_Agent had no tool at all to read an existing cloud
   architecture diagram -- `load_drawio` is now wired in, following the
   same opt-in, explicitly-requested cross-pipeline read already used by
   CloudArch_Consultant_Agent/CloudArch_FinOps_Agent/etc. (design and
   cloud-architecture stay isolated by default; a diagram is only loaded
   when the request actually references one).
2. Even with accurate infrastructure detail in hand, nothing stopped the
   design-generation agent inventing a business domain to satisfy the
   schema's business_context/document_metadata fields. `business_purpose_
   stated` (set by Design_Doc_Analysis_Agent) plus the new "INFRASTRUCTURE-
   ONLY INPUT CHECK" instructions block this -- business_context.purpose
   must explicitly say no business purpose was stated instead of
   fabricating one.

IMPORTANT: a plain "create an HLD" (not "Combined") request on THIS port
routes to Design_Doc_HLD_Agent's own first pass for its INITIAL
construction, not Design_Doc_Agent -- Design_Doc_Agent is only reused for
the Create pipeline's later refinement/grounding instances (see
design_doc_create_agent.py's Refinement_Instance/Simulation_Refinement_
Instance/Grounding_Instance, all built from design_doc_agent). The fix
above alone would have left a fresh HLD-only request fabricating a
business domain exactly as before; design_doc_hld_agent.txt needed the
same INFRASTRUCTURE-ONLY INPUT CHECK fix independently.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "design" / "design_doc_analysis_agent.txt"
DESIGN_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "design" / "design_doc_agent.txt"
HLD_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "design" / "design_doc_hld_agent.txt"
LLD_INSTRUCTIONS = PROJECT_ROOT / "instructions" / "design" / "design_doc_lld_agent.txt"


def test_design_doc_analysis_agent_can_load_the_existing_diagram():
    from process_agents.common.utils import load_drawio
    from process_agents.design.design_doc_analysis_agent import design_doc_analysis_agent

    assert load_drawio in design_doc_analysis_agent.tools

    text = ANALYSIS_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "load_drawio" in text
    assert "cloud architecture diagram" in text


def test_design_doc_analysis_agent_tracks_whether_a_business_purpose_was_stated():
    text = ANALYSIS_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "business_purpose_stated" in text
    assert "NEVER set this true by inferring or guessing" in text


def test_design_doc_agent_refuses_to_fabricate_a_business_domain():
    text = DESIGN_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "INFRASTRUCTURE-ONLY INPUT CHECK" in text
    assert "Do NOT invent one (no" in text
    assert "business_context.purpose: state plainly that no business purpose was provided" in text


def test_design_doc_hld_agent_also_refuses_to_fabricate_a_business_domain():
    # The agent that actually handles a FRESH, HLD-only request's initial
    # build -- Design_Doc_Agent above is only reused for this pipeline's
    # later refinement passes, so this needed the identical fix
    # independently or a plain "create an HLD" request would still fabricate.
    text = HLD_INSTRUCTIONS.read_text(encoding="utf-8")
    assert "INFRASTRUCTURE-ONLY INPUT CHECK" in text
    assert "e-commerce platform" in text
    assert "business_context.purpose: state plainly that no business purpose was provided" in text


def test_design_generators_persist_unconditionally_on_a_fresh_generation():
    # Regression for a second real bug hit live: Compliance_Agent auditing
    # the same empty template on every pass because the generator's own
    # "persist only if changed" instruction gave it room to build a fresh
    # document in-memory and never actually write it.
    for instructions_path in (DESIGN_INSTRUCTIONS, HLD_INSTRUCTIONS, LLD_INSTRUCTIONS):
        text = instructions_path.read_text(encoding="utf-8")
        assert "this call is UNCONDITIONAL" in text, instructions_path
        assert "always persist" in text, instructions_path
