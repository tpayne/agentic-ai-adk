"""Generates a structured, ISO-formatted Word document from the master
process or design-document JSON. Ported from the ADK sample's
process_agents/common/doc_generation_agent.py -- both
`_build_process_document` and `_build_design_document` (+
`_add_part_divider`/`_renumber_design_document_headings`).

Also dropped: the ADK original's getProperty("modelSleep")-based random
jitter sleep at the top of this function, which existed purely to spread
out this app's own ADK-side LLM rate-limit retries -- not relevant here,
since neuro-san's own LLM call path isn't this port's concern.
"""

import os
import re
import json
import traceback
import logging
from datetime import datetime
from typing import Optional

import docx
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

from process_toolkit import paths
from process_toolkit.filenames import safe_filename_component
from process_toolkit.schema.process_json import PROCESS_JSON_FILENAME, detect_schema_type_from_disk
from process_toolkit.schema.process_json import DESIGN_JSON_FILENAME
from process_toolkit.schema.requirements_json import REQUIREMENTS_SUMMARY_FILENAME
from process_toolkit.schema.test_specification_json import TEST_SPECIFICATION_FILENAME
from process_toolkit.schema.proposal_response_json import PROPOSAL_RESPONSE_FILENAME
from process_toolkit.schema.design_json import DESIGN_TEMPLATE
from process_toolkit.schema.togaf_json import TOGAF_JSON_FILENAME
from process_toolkit.docgen.themes import apply_theme
from process_toolkit.docgen.structure import (
    _add_version_history_table,
    _add_table_of_contents,
    _label_from_key,
    add_iso_page_break,
)
from process_toolkit.docgen.content import (
    _add_overview_section,
    _add_design_overview_section,
    _add_stakeholders_section,
    _add_process_steps_section,
    _render_generic_value,
)
from process_toolkit.docgen.technical import (
    _add_tools_section_from_summary,
    _add_metrics_section,
    _add_system_requirements,
    _add_flowchart_section,
    _add_simulation_report,
)
from process_toolkit.docgen.governance import (
    _add_governance_requirements_section,
    _add_risks_and_controls_section,
    _add_process_triggers_section,
    _add_process_end_conditions_section,
    _add_change_management_section,
    _add_continuous_improvement_section,
    _add_appendix_from_json,
    _add_additional_data_section,
    _add_glossary,
    _add_critical_success_factors_section,
    _add_critical_failure_factors_section,
    _add_reporting_and_analytics,
)
from process_toolkit.docgen.design_sections import (
    _add_requirements_section,
    _add_system_context_section,
    _add_quality_attributes_section,
    _add_compliance_and_standards_section,
    _add_risk_register_section,
    _add_architecture_analysis,
    _add_architecture_decisions_section,
    _add_viewpoints_and_views_section,
    _add_hld_components_section,
    _add_integration_points_table,
    _add_technology_stack_table,
    _add_low_level_design_section,
    _add_operational_readiness_section,
    _add_review_governance_checklist_section,
    _add_glossary_and_references_section,
)
from process_toolkit.docgen.requirements_sections import (
    _add_requirements_overview_section,
    _add_business_context_section,
    _add_scope_section,
    _add_requirements_register_section,
    _add_traceability_section,
    _add_requirement_priorities_section,
    _add_conflicting_requirements_section,
    _add_requirements_needing_clarification_section,
    _add_inferred_requirements_section,
    _add_coverage_gaps_section,
    _add_dependency_register_section,
    _add_glossary_section,
)
from process_toolkit.docgen.test_specification_sections import (
    _add_test_specification_overview_section,
    _add_test_cases_register_section,
    _add_coverage_summary_section,
    _add_test_dependency_register_section,
    _add_test_specification_glossary_section,
)
from process_toolkit.docgen.togaf_sections import (
    _add_architecture_vision_section,
    _add_architecture_requirements_section,
    _add_architecture_principles_section,
    _add_business_architecture_section,
    _add_data_architecture_section,
    _add_application_architecture_section,
    _add_technology_architecture_section,
    _add_opportunities_and_solutions_section,
    _add_migration_planning_section,
    _add_architecture_compliance_assessment_section,
    _add_glossary_and_references_section as _add_togaf_glossary_and_references_section,
)
from process_toolkit.docgen.proposal_response_sections import (
    _add_executive_summary_section,
    _add_win_themes_section,
    _add_proposed_solution_section,
    _add_solution_architecture_section,
    _add_scope_of_work_section,
    _add_compliance_matrix_section,
    _add_delivery_approach_section,
    _add_governance_section,
    _add_team_profiles_section,
    _add_success_stories_section,
    _add_qualifications_section,
    _add_future_roadmap_section,
    _add_assumptions_dependencies_section,
    _add_commercial_proposal_section,
    _add_open_questions_section,
    _add_unaddressed_items_section,
)

logger = logging.getLogger("ProcessArchitect.DocGen")

SIM_RESULTS_FILENAME = "simulation_results.json"


# ============================================================
# LOAD SUBPROCESSES
# ============================================================

def _load_subprocesses() -> dict:
    """Loads all subprocess JSON files from output/subprocesses/."""
    logger.debug("Loading subprocess JSON files...")
    subprocess_dir = paths.output_dir("subprocesses")
    subprocesses = {}

    if not os.path.isdir(subprocess_dir):
        return subprocesses

    for filename in os.listdir(subprocess_dir):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(subprocess_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            parent = data.get("parent_step_name") or data.get("step_name")
            if parent:
                data["step_name"] = parent
                subprocesses[parent] = data

        except Exception:
            logger.exception(f"Failed to load subprocess file: {path}")

    logger.debug("Subprocesses loaded.")
    return subprocesses


# ============================================================
# GLOBAL DOCUMENT STYLE SETUP (fallback when no theme is applied)
# ============================================================

def _apply_global_styles(doc: docx.Document):
    """Apply ISO-style global typography and spacing."""
    styles = doc.styles

    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = 1.15

    h1 = styles["Heading 1"]
    h1.font.name = "Calibri"
    h1.font.size = Pt(16)
    h1.font.bold = True
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(12)

    h2 = styles["Heading 2"]
    h2.font.name = "Calibri"
    h2.font.size = Pt(14)
    h2.font.bold = True
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(6)

    h3 = styles["Heading 3"]
    h3.font.name = "Calibri"
    h3.font.size = Pt(12)
    h3.font.bold = True
    h3.paragraph_format.space_before = Pt(6)
    h3.paragraph_format.space_after = Pt(3)

    h4 = styles["Heading 4"]
    h4.font.name = "Calibri"
    h4.font.size = Pt(11)
    h4.font.bold = True
    h4.paragraph_format.space_before = Pt(6)
    h4.paragraph_format.space_after = Pt(3)

    for section in doc.sections:
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)


# ============================================================
# MAIN DOCUMENT GENERATION
# ============================================================

def create_standard_doc_from_file(
    process_name: str = "Process", schema_type: Optional[str] = None, design_variant: Optional[str] = None,
    togaf_variant: Optional[str] = None,
) -> str:
    """
    Generate a structured, ISO-formatted Word document from the master
    JSON (output/process_data.json, output/design_data.json,
    output/requirements_summary.json, output/proposal_response.json, or
    output/togaf_data.json).
    `schema_type` defaults to auto-detecting from which master file exists
    on disk (detect_schema_type_from_disk) -- note that auto-detect NEVER
    resolves to "requirements"/"proposal_response"/"togaf": detect_schema_
    type_from_disk() only ever returns "process"/"design", by design (none
    of the other three is ever the thing someone wants rendered often
    enough to guess at from whichever file happens to exist). A
    requirements, proposal-response, or TOGAF document is only ever built
    when schema_type is passed explicitly.

    `design_variant` ("hld"|"lld"|"both", default "both") is only
    meaningful when `resolved_type == "design"` -- see
    _build_design_documents's own docstring. `togaf_variant`
    ("vision"|"definition"|"both", default "both") is only meaningful when
    `resolved_type == "togaf"` -- see _build_togaf_documents's own
    docstring. Each is ignored for every other schema type.
    """
    logger.debug(f"Creating document for process: {process_name}...")

    try:
        resolved_type = schema_type or detect_schema_type_from_disk()
        if resolved_type == "requirements":
            data_filename = REQUIREMENTS_SUMMARY_FILENAME
        elif resolved_type == "proposal_response":
            data_filename = PROPOSAL_RESPONSE_FILENAME
        elif resolved_type == "test_specification":
            data_filename = TEST_SPECIFICATION_FILENAME
        elif resolved_type == "design":
            data_filename = DESIGN_JSON_FILENAME
        elif resolved_type == "togaf":
            data_filename = TOGAF_JSON_FILENAME
        else:
            data_filename = PROCESS_JSON_FILENAME

        data_path = paths.output_path(data_filename)
        if not os.path.exists(data_path):
            # A routine, fully-expected condition (nothing has been
            # created/saved yet for this schema type -- the standard
            # "regenerate before anything exists" case) -- return the
            # same "ERROR: ... No such file ..." shape callers already
            # match on, without the traceback.print_exc() below, which
            # is reserved for genuinely unexpected failures.
            return f"ERROR: No such file or directory: '{data_path}'"

        with open(data_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        data = raw_data.get("process_design") if isinstance(raw_data, dict) and "process_design" in raw_data else raw_data

        # Design and TOGAF documents build their own Document()/apply_
        # theme() per file (one or two), unlike every other schema type
        # below, which share a single document -- see
        # _build_design_documents/_build_togaf_documents.
        if resolved_type == "design":
            return _build_design_documents(data, process_name, design_variant)
        if resolved_type == "togaf":
            return _build_togaf_documents(data, process_name, togaf_variant)

        doc = docx.Document()
        apply_theme(doc)

        if resolved_type == "requirements":
            out_path = _build_requirements_document(doc, data, process_name)
        elif resolved_type == "proposal_response":
            out_path = _build_proposal_response_document(doc, data, process_name)
        elif resolved_type == "test_specification":
            out_path = _build_test_specification_document(doc, data, process_name)
        else:
            out_path = _build_process_document(doc, data, process_name)

        return f"SUCCESS: Professional document saved at {out_path}"

    except Exception as e:
        traceback.print_exc()
        return f"ERROR: {str(e)}"


def _build_process_document(doc: docx.Document, data: dict, process_name: str) -> str:
    """Builds the full ISO-formatted process document into `doc` and saves
    it. Returns the saved file path."""
    # Attach subprocesses
    subprocesses = _load_subprocesses()
    for step in data.get("process_steps", []):
        if isinstance(step, dict):
            name = step.get("step_name")
            if name in subprocesses:
                step["subprocess"] = subprocesses[name]

    # Extract metadata
    name = str(data.get("process_name", process_name))
    version = str(data.get("version", "1.0"))
    sector = data.get("industry_sector", data.get("business_unit", "N/A"))

    stakeholders = data.get("stakeholders")
    process_steps = data.get("process_steps")
    tools_summary = data.get("tools_summary")
    critical_success_factors = data.get("critical_success_factors")
    critical_failure_factors = data.get("critical_failure_factors")
    metrics = data.get("metrics") or data.get("success_metrics")
    reporting_and_analytics = data.get("reporting_and_analytics")
    system_requirements = data.get("system_requirements")
    appendix = data.get("appendix") if isinstance(data.get("appendix"), dict) else None

    governance_requirements = data.get("governance_requirements")
    process_end_conditions = data.get("process_end_conditions")
    change_management = data.get("change_management")
    process_triggers = data.get("process_triggers")
    continuous_improvement = data.get("continuous_improvement")
    risks_and_controls = data.get("risks_and_controls")

    consumed_keys = {
        "appendix", "assumptions", "business_unit", "change_management",
        "constraints", "continuous_improvement", "critical_failure_factors",
        "critical_success_factors", "description", "governance_requirements",
        "industry_sector", "introduction", "metrics", "process_description",
        "process_end_conditions", "process_name", "process_steps",
        "process_triggers", "reporting_and_analytics", "risks_and_controls",
        "stakeholders", "success_metrics", "system_requirements",
        "tools_summary", "version",
        # "purpose"/"scope" ARE rendered (in _add_overview_section's own
        # "ordered" loop) but were missing here, so they rendered correctly
        # in 1.0 Overview and then ALSO reappeared, duplicated, in Appendix
        # B's leftover-data catch-all below. "process_owner"/"owner"
        # likewise (see _add_overview_section's own fix for why both keys
        # are checked).
        "purpose", "scope", "process_owner", "owner",
    }

    # ---- COVER PAGE ----
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(name)
    run.bold = True
    run.font.size = Pt(28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Process Model Document").font.size = Pt(18)

    doc.add_paragraph()
    doc.add_paragraph(f"Industry / Domain: {sector}")
    doc.add_paragraph(f"Version: {version}")
    doc.add_paragraph(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    add_iso_page_break(doc)

    # ---- DOCUMENT CONTROL + TOC ----
    _add_version_history_table(doc, version=version, author="Process Architect")

    add_iso_page_break(doc)
    doc.add_heading("Table of Contents", level=1)
    _add_table_of_contents(doc)

    add_iso_page_break(doc)

    # ---- MAIN SECTIONS ----
    _add_overview_section(doc, data)
    add_iso_page_break(doc)

    _add_stakeholders_section(doc, stakeholders)
    add_iso_page_break(doc)

    if process_steps:
        _add_process_steps_section(
            doc, process_steps,
            top_level_risks_and_controls=risks_and_controls,
            top_level_change_management=change_management,
            top_level_continuous_improvement=continuous_improvement,
        )
        add_iso_page_break(doc)

    if tools_summary:
        _add_tools_section_from_summary(doc, tools_summary)
        add_iso_page_break(doc)

    if isinstance(metrics, list) and metrics:
        _add_metrics_section(doc, metrics)
        add_iso_page_break(doc)

    if isinstance(critical_success_factors, list) and critical_success_factors:
        _add_critical_success_factors_section(doc, critical_success_factors)
        add_iso_page_break(doc)

    if isinstance(critical_failure_factors, list) and critical_failure_factors:
        _add_critical_failure_factors_section(doc, critical_failure_factors)
        add_iso_page_break(doc)

    if reporting_and_analytics:
        _add_reporting_and_analytics(doc, reporting_and_analytics)
        add_iso_page_break(doc)

    if system_requirements:
        _add_system_requirements(doc, system_requirements)
        add_iso_page_break(doc)

    _add_flowchart_section(doc, name, generate_diagram=True, schema_type="process")
    add_iso_page_break(doc)

    # Simulation results
    simulation_results = None
    try:
        sim_path = paths.output_path(SIM_RESULTS_FILENAME)
        if os.path.exists(sim_path):
            with open(sim_path, "r", encoding="utf-8") as sf:
                simulation_results = json.load(sf)
    except Exception:
        traceback.print_exc()

    if simulation_results:
        _add_simulation_report(doc, simulation_results)
        add_iso_page_break(doc)

    if governance_requirements:
        _add_governance_requirements_section(doc, governance_requirements)
        add_iso_page_break(doc)

    if risks_and_controls:
        _add_risks_and_controls_section(doc, risks_and_controls)
        add_iso_page_break(doc)

    if process_triggers:
        _add_process_triggers_section(doc, process_triggers)
        add_iso_page_break(doc)

    if process_end_conditions:
        _add_process_end_conditions_section(doc, process_end_conditions)
        add_iso_page_break(doc)

    if change_management:
        _add_change_management_section(doc, change_management)
        add_iso_page_break(doc)

    if continuous_improvement:
        _add_continuous_improvement_section(doc, continuous_improvement)
        add_iso_page_break(doc)

    # Appendices
    # Both of the next two sections are genuine maybe-render-maybe-not
    # calls (unlike every section above, which is already guarded by an
    # "if <source data field>:" precondition) -- each one's OWN return
    # value (True if it actually added content, False on a documented
    # silent no-op) is what must gate the page break that follows it, not
    # an unconditional call. Confirmed directly against a real generated
    # document: with "appendix" absent from the source JSON (the common
    # case) and _add_additional_data_section finding nothing left over
    # once every other section had already consumed its own fields (also
    # the common case -- see that function's own docstring), the OLD
    # unconditional add_iso_page_break(doc) calls here fired back-to-back
    # with zero real content between them, rendering as a fully blank
    # page in the final document, right before "Appendix B".
    if appendix:
        _add_appendix_from_json(doc, appendix)
        consumed_keys.add("appendix")
        add_iso_page_break(doc)

    if _add_additional_data_section(doc, data, consumed_keys):
        add_iso_page_break(doc)

    _add_glossary(doc)

    # Save
    out_path = paths.output_path(f"{safe_filename_component(name)}.docx")
    doc.save(out_path)
    return out_path


def _build_requirements_document(doc: docx.Document, data: dict, process_name: str) -> str:
    """
    Builds the requirements-tracking document into `doc` and saves it.
    Requirements-schema counterpart to _build_process_document/
    _build_design_document -- renders requirements_summary.json's own
    fields directly (see requirements_sections.py). No diagram section (a
    requirements register has no flow/architecture diagram, unlike
    process/design). Glossary IS rendered here (unlike the deliberate
    no-fabrication exclusion this docstring used to describe) -- but only
    when "glossary" is actually populated, and only with terms the
    agent's own drafted content introduced, not a fabricated section with
    no backing data; same conditional convention as every other optional
    section here.

    requirements_summary.json's own "name" field wins when present (set by
    the drafting agent from the source material/description) -- `process_name`
    is only a fallback for legacy data saved before this field existed.
    Same precedence _build_process_document already gives "process_name"
    and _build_design_document gives "document_metadata.title" -- without
    it, a later standalone "regenerate the document" request (a fresh
    agent turn with no memory of the original drafting conversation) has
    no way to recover the original title.
    """
    name = str(data.get("name") or process_name)
    sector = data.get("industry_sector") or "N/A"

    stakeholders = data.get("stakeholders")
    requirement_priorities = data.get("requirement_priorities")
    conflicting_requirements = data.get("conflicting_requirements")
    requirements_needing_clarification = data.get("requirements_needing_clarification")
    inferred_requirements = data.get("inferred_requirements")
    coverage_gaps = data.get("coverage_gaps")
    dependencies = data.get("dependencies")
    glossary = data.get("glossary")

    consumed_keys = {
        "name", "source_directory", "source_files", "summary", "industry_sector",
        "current_state", "future_state", "success_measures", "scope_in", "scope_out",
        "stakeholders", "assumptions", "risks", "open_questions",
        "requirements_register", "requirement_priorities",
        "conflicting_requirements", "requirements_needing_clarification",
        "inferred_requirements", "coverage_gaps", "dependencies", "glossary",
        # Legacy old-format fields (is_old_format_requirements_summary) --
        # already rendered by _add_requirements_register_section's own
        # old-format branch when present, so they must not also reappear
        # via the Appendix B leftover-data catch-all below.
        "functional_requirements", "non_functional_requirements",
        "goals_or_objectives", "constraints",
    }

    # ---- COVER PAGE ----
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(name)
    run.bold = True
    run.font.size = Pt(28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Requirements Specification").font.size = Pt(18)

    doc.add_paragraph()
    doc.add_paragraph(f"Industry / Domain: {sector}")
    doc.add_paragraph(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    add_iso_page_break(doc)

    # ---- DOCUMENT CONTROL + TOC ----
    _add_version_history_table(
        doc, version="1.0", author="Requirements Analyst",
        description="Initial generated requirements summary",
    )

    add_iso_page_break(doc)
    doc.add_heading("Table of Contents", level=1)
    _add_table_of_contents(doc)

    add_iso_page_break(doc)

    # ---- MAIN SECTIONS ----
    # Section numbers are intentionally left un-normalized here, same
    # reasoning as _build_design_document: _renumber_design_document_
    # headings fixes them all in one pass from the final actual set of
    # headings, right before saving, since which sections render depends
    # on what's actually present in the source JSON.
    rendered = True  # Introduction and Purpose always renders unconditionally.
    _add_requirements_overview_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_business_context_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_scope_section(doc, data)

    if stakeholders:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_stakeholders_section(
            doc, stakeholders, heading="4.0 Stakeholders", subject_noun="requirements effort",
        )

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_requirements_register_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_traceability_section(doc, data)

    if requirement_priorities:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_requirement_priorities_section(doc, requirement_priorities)

    if conflicting_requirements:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_conflicting_requirements_section(doc, conflicting_requirements)

    if requirements_needing_clarification:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_requirements_needing_clarification_section(
            doc, requirements_needing_clarification,
        )

    if inferred_requirements:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_inferred_requirements_section(doc, inferred_requirements)

    if coverage_gaps:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_coverage_gaps_section(doc, coverage_gaps)

    if dependencies:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_dependency_register_section(doc, dependencies)

    if glossary:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_glossary_section(doc, glossary)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_additional_data_section(doc, data, consumed_keys)

    # Fix up section numbers from the final set of headings that actually
    # rendered above -- same mechanism _build_design_document already
    # uses, needed for the same reason (conditional sections mean fixed
    # literal numbers would collide/gap).
    _renumber_design_document_headings(doc)

    # Save
    out_path = paths.output_path(f"{safe_filename_component(name)}.docx")
    doc.save(out_path)
    return out_path


def _build_test_specification_document(doc: docx.Document, data: dict, process_name: str) -> str:
    """
    Builds the test-specification document into `doc` and saves it.
    Requirements-schema sibling of _build_requirements_document -- renders
    test_specification.json's own fields directly (see
    test_specification_sections.py). No diagram section, same reasoning as
    the requirements document (a test register has no flow/architecture
    diagram of its own).

    test_specification.json's own "name" field wins when present (set by
    the drafting agent from whichever source artifacts it read) --
    `process_name` is only a fallback, same precedence
    _build_requirements_document already gives its own "name" field.
    """
    name = str(data.get("name") or process_name)

    dependencies = data.get("dependencies")
    glossary = data.get("glossary")

    consumed_keys = {
        "name", "source_requirements_used", "source_design_used", "source_cloudarch_used",
        "summary", "test_approach", "test_environment", "test_cases", "coverage_summary",
        "risks", "open_questions", "dependencies", "glossary",
    }

    # ---- COVER PAGE ----
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(name)
    run.bold = True
    run.font.size = Pt(28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Test Specification").font.size = Pt(18)

    doc.add_paragraph()
    doc.add_paragraph(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    add_iso_page_break(doc)

    # ---- DOCUMENT CONTROL + TOC ----
    _add_version_history_table(
        doc, version="1.0", author="QA/Test Analyst",
        description="Initial generated test specification",
    )

    add_iso_page_break(doc)
    doc.add_heading("Table of Contents", level=1)
    _add_table_of_contents(doc)

    add_iso_page_break(doc)

    # ---- MAIN SECTIONS ----
    # Section numbers are intentionally left un-normalized here, same
    # reasoning as _build_requirements_document: _renumber_design_
    # document_headings fixes them all in one pass from the final actual
    # set of headings, right before saving, since which sections render
    # depends on what's actually present in the source JSON.
    rendered = True  # Introduction and Purpose always renders unconditionally.
    _add_test_specification_overview_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_test_cases_register_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_coverage_summary_section(doc, data)

    if dependencies:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_test_dependency_register_section(doc, dependencies)

    if glossary:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_test_specification_glossary_section(doc, glossary)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_additional_data_section(doc, data, consumed_keys)

    _renumber_design_document_headings(doc)

    # Save
    out_path = paths.output_path(f"{safe_filename_component(name)}.docx")
    doc.save(out_path)
    return out_path


def _build_proposal_response_document(doc: docx.Document, data: dict, process_name: str) -> str:
    """
    Builds the proposal-response document into `doc` and saves it.
    Proposal-response-schema counterpart to _build_requirements_document
    -- renders proposal_response.json's own fields directly (see
    proposal_response_sections.py). Embeds a generated solution-
    architecture diagram when "architecture_components" is present
    (see proposal_architecture_diagram.py) -- unlike the requirements
    document, a proposal response genuinely benefits from a system-
    design visual, so this is NOT the same "never fabricate" exclusion
    requirements_sections.py applies to its own Glossary; it's simply
    conditional on the agent having actually populated the field, same
    as every other optional section here. Still NO fabricated Glossary.
    Also renders a much fuller enterprise-RTP table of contents: Why We
    Are Best Placed to Deliver (a consolidated "win themes" section),
    Scope of Work & Boundaries, Delivery & Engagement Approach (now
    including a visual mobilisation-roadmap diagram and a Transition-to-
    BAU subsection), Governance Model, Indicative Profiles & Team
    Structure, Relevant Success Stories & References, a restructured
    multi-subsection Qualifications section, and Future Roadmap &
    Innovation are each a single container section holding several
    independently-optional Heading-2 subsections (see
    proposal_response_sections.py's own `_add_scope_of_work_section` and
    siblings) -- structural patterns consistently present in real
    competitive RFP responses that pure narrative alone doesn't capture.

    proposal_response.json's own "name" field wins when present (set by
    the drafting agent from the RFP/requirements summary it drafted
    against) -- `process_name` is only a fallback for legacy data saved
    before this field existed. Same precedence _build_process_document
    already gives "process_name" -- without it, a later standalone
    "regenerate the document" request (a fresh agent turn with no memory
    of the original drafting conversation) has no way to recover the
    original title, and produces a differently-named file that reads as
    a brand-new document rather than an update to the existing one.
    """
    name = str(data.get("name") or process_name)

    architecture_components = data.get("architecture_components")
    compliance_matrix = data.get("compliance_matrix")
    open_questions_for_client = data.get("open_questions_for_client")
    unaddressed_items = data.get("unaddressed_items")

    consumed_keys = {
        "name", "summary", "our_understanding", "expected_outcomes", "benefits_realisation",
        "solution_summary", "proposed_solution", "architecture_components",
        "services_in_scope", "environments_covered", "deliverables", "out_of_scope",
        "technical_constraints", "differentiators", "compliance_matrix",
        "domain_expertise", "domain_accelerators", "core_delivery_approach",
        "platform_approach", "quality_validation_approach", "automation_approach",
        "environment_setup", "tooling_stack", "slas_and_kpis", "implementation_plan",
        "transition_to_bau", "governance_framework", "raci_matrix", "escalation_path",
        "meeting_cadence", "team_structure", "key_personnel", "skills_and_certifications",
        "case_studies", "measurable_outcomes",
        "qualifications", "company_overview", "relevant_experience",
        "certifications_overview", "delivery_capability", "future_roadmap",
        "assumptions", "client_dependencies", "risks_and_mitigations",
        "pricing_approach", "pricing_table", "ongoing_costs_approach",
        "rate_card_and_change_control", "open_questions_for_client", "unaddressed_items",
    }

    # ---- COVER PAGE ----
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(name)
    run.bold = True
    run.font.size = Pt(28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Response to Proposal").font.size = Pt(18)

    doc.add_paragraph()
    doc.add_paragraph(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    add_iso_page_break(doc)

    # ---- DOCUMENT CONTROL + TOC ----
    _add_version_history_table(
        doc, version="1.0", author="Proposal Response",
        description="Initial generated proposal response",
    )

    add_iso_page_break(doc)
    doc.add_heading("Table of Contents", level=1)
    _add_table_of_contents(doc)

    add_iso_page_break(doc)

    # ---- MAIN SECTIONS ----
    # Section numbers are intentionally left un-normalized here, same
    # reasoning as _build_requirements_document/_build_design_document:
    # _renumber_design_document_headings fixes them all in one pass from
    # the final actual set of headings, right before saving, since which
    # sections render depends on what's actually present in the source
    # JSON.
    rendered = True  # Executive Summary always renders unconditionally.
    _add_executive_summary_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_win_themes_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_proposed_solution_section(doc, data)

    if architecture_components:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_solution_architecture_section(doc, architecture_components, name)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_scope_of_work_section(doc, data)

    if compliance_matrix:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_compliance_matrix_section(doc, compliance_matrix)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_delivery_approach_section(doc, data, name)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_governance_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_team_profiles_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_success_stories_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_qualifications_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_future_roadmap_section(doc, data.get("future_roadmap"))

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_assumptions_dependencies_section(doc, data)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_commercial_proposal_section(doc, data)

    if open_questions_for_client:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_open_questions_section(doc, open_questions_for_client)

    if unaddressed_items:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_unaddressed_items_section(doc, unaddressed_items)

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_additional_data_section(doc, data, consumed_keys)

    # Fix up section numbers from the final set of headings that actually
    # rendered above -- same mechanism _build_requirements_document/
    # _build_design_document already use.
    _renumber_design_document_headings(doc)

    # Save
    out_path = paths.output_path(f"{safe_filename_component(name)}.docx")
    doc.save(out_path)
    return out_path


# A document_metadata.title/system_name sometimes bakes in a doc-type label
# the generator/import agent chose for itself -- e.g. "High-Level Design:
# Checkout Service" or "Returns Processing Service High-Level Design".
# Harmless when there was only one combined file; now that this SAME name is
# shared as the cover-page title AND the filename stem for BOTH the HLD and
# LLD documents, a baked-in label is actively misleading on whichever of the
# two it doesn't belong to (e.g. an "...LLD.docx" file titled "High-Level
# Design: ..."). Strip it from either end before use.
# Deliberately does NOT include bare "combined design" -- that phrase alone
# is plausible as an intentional, non-redundant title (confirmed against a
# real pre-existing test fixture titled "Checkout Combined Design"); only
# "combined" wording that explicitly ALSO names HLD/LLD is unambiguously a
# doc-type label rather than part of the name itself.
_DESIGN_DOC_TYPE_LABEL = r"(?:high[- ]level design|low[- ]level design|combined hld/?lld design|hld|lld)"
_DESIGN_TITLE_LEADING_LABEL_RE = re.compile(
    rf"^\s*{_DESIGN_DOC_TYPE_LABEL}\s*(?:document)?\s*[:\-]?\s*", re.IGNORECASE
)
_DESIGN_TITLE_TRAILING_LABEL_RE = re.compile(
    rf"\s*[:\-]?\s*{_DESIGN_DOC_TYPE_LABEL}\s*(?:document)?\s*$", re.IGNORECASE
)


def _strip_design_doc_type_label(title: str) -> str:
    stripped = _DESIGN_TITLE_LEADING_LABEL_RE.sub("", title, count=1)
    stripped = _DESIGN_TITLE_TRAILING_LABEL_RE.sub("", stripped, count=1)
    stripped = stripped.strip(" :-")
    return stripped or title


class _DesignMeta:
    """Small bag of cover-page/title fields derived from document_metadata,
    shared by both _build_hld_document and _build_lld_document so the two
    can never silently diverge on how they compute a design's own title."""

    __slots__ = ("name", "system_label", "version", "doc_type", "sector")

    def __init__(self, data: dict, process_name: str):
        metadata = data.get("document_metadata") or {}
        raw_name = str(metadata.get("title") or metadata.get("system_name") or process_name)
        self.name = _strip_design_doc_type_label(raw_name)
        # Short system name for diagram hub labels -- "name" above is the
        # full document TITLE (a whole sentence), fine for a cover page but
        # unreadable as a diagram node label. "system_name" is the short
        # form meant for exactly this.
        self.system_label = _strip_design_doc_type_label(str(metadata.get("system_name") or self.name))
        self.version = str(metadata.get("version", "1.0"))
        self.doc_type = str(metadata.get("document_type", "Design"))
        self.sector = metadata.get("industry_sector", "N/A")


# Every top-level design_data.json key this renderer knows how to handle,
# across BOTH the HLD and LLD documents -- reused verbatim, unmodified, by
# both _build_hld_document and _build_lld_document. This is deliberate:
# each document only RENDERS its own half of this set, but both must keep
# the FULL set out of their own "Additional Data" catch-all, or else e.g.
# low_level_design would wrongly dump as raw JSON into the HLD document
# (and vice versa) instead of simply not appearing there at all.
_DESIGN_CONSUMED_KEYS = {
    "document_metadata", "business_context", "architecture_description",
    "architecture_decisions", "requirements", "system_context",
    "high_level_design", "low_level_design", "quality_attributes",
    "compliance_and_standards", "risk_register", "governance_requirements",
    "continuous_improvement", "operational_readiness",
    "glossary_and_references", "review_and_governance", "appendix",
}

# Field names that only belong NESTED under high_level_design/
# low_level_design per DESIGN_TEMPLATE (e.g. "availability_and_resilience"
# with its own "rto"/"rpo") -- derived from the template itself rather
# than hardcoded, so it stays in sync with it. Confirmed as a real bug via
# a live-generated document: a generating agent persisted
# availability_and_resilience a SECOND time as its own stray TOP-LEVEL
# key, duplicating the exact same RTO/RPO/backup-strategy content already
# rendered in 5.2 Architecture Detail -- _DESIGN_CONSUMED_KEYS alone
# didn't catch this (the stray key's NAME was never a real top-level
# schema field, so it was never in that set either), and the Additional
# Data appendix then dumped it a second time since it looked, by the
# top-level-only consumed-keys check, like genuinely novel leftover data.
# A top-level key sharing a name that ONLY makes schema sense nested is,
# by definition, not novel data -- it's a stray duplicate, so it's
# excluded here too (unlike a genuinely new top-level key, which still
# correctly reaches Additional Data -- this never drops real content).
_DESIGN_NESTED_ONLY_KEYS = (
    set(DESIGN_TEMPLATE.get("high_level_design", {}).keys())
    | set(DESIGN_TEMPLATE.get("low_level_design", {}).keys())
) - _DESIGN_CONSUMED_KEYS


def _add_design_cover_and_toc(doc: docx.Document, meta: _DesignMeta, subtitle: str) -> None:
    """Cover page + Document Control (version history) + Table of
    Contents -- identical structure for the HLD and LLD documents, just a
    different subtitle (e.g. "High-Level Design Document")."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(meta.name)
    run.bold = True
    run.font.size = Pt(28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(subtitle).font.size = Pt(18)

    doc.add_paragraph()
    doc.add_paragraph(f"Industry / Domain: {meta.sector}")
    doc.add_paragraph(f"Version: {meta.version}")
    doc.add_paragraph(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    add_iso_page_break(doc)

    _add_version_history_table(
        doc, version=meta.version, author="Design Architect",
        description="Initial generated design specification",
    )

    add_iso_page_break(doc)
    doc.add_heading("Table of Contents", level=1)
    _add_table_of_contents(doc)

    add_iso_page_break(doc)


def _add_design_trailing_sections(doc: docx.Document, data: dict, rendered: bool) -> bool:
    """Glossary and References, Appendix, and Additional Data -- the
    sections common to BOTH the HLD and LLD documents, duplicated into
    each so either one is genuinely self-contained/standalone-usable on
    its own. Returns the updated `rendered` flag."""
    glossary_and_references = data.get("glossary_and_references")
    appendix = data.get("appendix") if isinstance(data.get("appendix"), dict) else None

    if glossary_and_references:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_glossary_and_references_section(
            doc, glossary_and_references, heading="11.0 Glossary and References"
        )

    if appendix:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_appendix_from_json(doc, appendix, subject_noun="architecture")

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_additional_data_section(doc, data, _DESIGN_CONSUMED_KEYS | _DESIGN_NESTED_ONLY_KEYS)

    # _add_glossary is the process document's fallback glossary (four
    # hardcoded process-specific terms) -- not called here at all. A
    # design document with no glossary_and_references data of its own
    # should simply have no glossary section, the same way every diagram/
    # table renderer elsewhere in this pipeline withholds a section rather
    # than fabricating one.
    return rendered


def _build_hld_document(doc: docx.Document, data: dict, process_name: str, has_lld_companion: bool) -> str:
    """
    Builds the High-Level Design document: business context, requirements,
    stakeholders, system context, architecture description/detail, the
    architecture flow diagram, quality attributes, compliance, risk
    register, governance, and continuous improvement -- everything a
    reader needs to review and approve the design, as a standalone
    document. `has_lld_companion` controls whether the opening overview
    mentions a separate Low-Level Design document exists alongside it.
    """
    meta = _DesignMeta(data, process_name)

    architecture_description = data.get("architecture_description") or {}
    stakeholders = architecture_description.get("stakeholders")

    requirements = data.get("requirements")
    system_context = data.get("system_context")
    high_level_design = data.get("high_level_design") or {}
    low_level_design = data.get("low_level_design") or {}
    quality_attributes = data.get("quality_attributes")
    compliance_and_standards = data.get("compliance_and_standards")
    risk_register = data.get("risk_register")
    governance_requirements = data.get("governance_requirements")
    continuous_improvement = data.get("continuous_improvement")
    operational_readiness = data.get("operational_readiness")

    _add_design_cover_and_toc(doc, meta, "High-Level Design Document")

    # Every section below is only page-broken from the NEXT one if it
    # actually rendered something (see `rendered` tracking) -- an
    # unconditional break both after a no-op section and before the next
    # one stacks two explicit page breaks with nothing between them, which
    # Word renders as a genuinely blank page.
    #
    # Section numbers are intentionally left un-normalized here;
    # _renumber_design_document_headings fixes them all in one pass from
    # the final actual set of headings, right before saving.

    rendered = True  # Document Overview always renders unconditionally.
    _add_design_overview_section(doc, data, has_lld_companion=has_lld_companion)

    if stakeholders:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_stakeholders_section(doc, stakeholders, subject_noun="architecture")

    if requirements:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_requirements_section(
            doc, requirements, heading="3.0 Requirements",
            high_level_design=high_level_design, low_level_design=low_level_design,
        )

    if system_context:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_system_context_section(
            doc, system_context, heading="4.0 System Context", system_name=meta.system_label
        )

    if architecture_description:
        if rendered:
            add_iso_page_break(doc)
        doc.add_heading("5.0 Architecture Description", level=1)
        doc.add_paragraph(
            "The following describes the architecture viewpoints and views "
            "for this design (ISO/IEC/IEEE 42010), and the analysis behind "
            "the recommended approach."
        )
        concerns = architecture_description.get("concerns")
        if concerns:
            _render_generic_value(doc, concerns, label="Concerns", system_name=meta.system_label)

        # Dedicated renderer (not the generic fallback) -- groups each
        # view under the viewpoint it actually references via
        # viewpoint_ref, making the correlation structural rather than
        # two independently-rendered, uncorrelated lists.
        _add_viewpoints_and_views_section(
            doc, architecture_description.get("viewpoints"), architecture_description.get("views"), level=3,
            system_name=meta.system_label, high_level_design=high_level_design,
        )

        architecture_analysis = architecture_description.get("architecture_analysis")
        if architecture_analysis:
            _add_architecture_analysis(doc, architecture_analysis, level=3)

        architecture_decisions = data.get("architecture_decisions")
        if architecture_decisions:
            _add_architecture_decisions_section(doc, architecture_decisions, heading="5.1 Architecture Decisions")

        rendered = True

    # high_level_design's own architectural detail -- components,
    # integration points, deployment topology, security/scalability/
    # availability characteristics, and architecture-level risks.
    # components/integration_points/technology_stack each have a
    # dedicated renderer (consistent field order for components; a real
    # table for the other two, since they're the same few fields repeated
    # per entry) -- confirmed as a real readability gap via a
    # live-generated document where all three fell through to the generic
    # fallback and rendered as inconsistently-ordered/non-tabular prose.
    # Every other key here has no bespoke renderer and goes through
    # _render_generic_value (the same generic fallback every other
    # schema-conforming-but-not-specially-handled section in this
    # document uses), labeled so a reader can tell which schema field
    # each came from.
    if isinstance(high_level_design, dict) and high_level_design:
        bespoke_hld_renderers = {
            "components": lambda: _add_hld_components_section(doc, high_level_design["components"], level=3),
            "integration_points": lambda: _add_integration_points_table(
                doc, high_level_design["integration_points"], level=3
            ),
            "technology_stack": lambda: _add_technology_stack_table(
                doc, high_level_design["technology_stack"], level=3
            ),
        }
        hld_sections = [
            ("solution_overview", "Solution Overview"),
            ("architecture_style", "Architecture Style"),
            ("components", "Components"),
            ("integration_points", "Integration Points"),
            ("data_flow_overview", "Data Flow Overview"),
            ("technology_stack", "Technology Stack"),
            ("deployment_topology", "Deployment Topology"),
            ("security_architecture", "Security Architecture"),
            ("scalability_and_performance", "Scalability and Performance"),
            ("availability_and_resilience", "Availability and Resilience"),
            ("risks_and_mitigations", "Architecture-Level Risks and Mitigations"),
        ]
        present = [(key, label) for key, label in hld_sections if high_level_design.get(key)]
        if present:
            if rendered:
                add_iso_page_break(doc)
            doc.add_heading("5.2 Architecture Detail", level=2)
            doc.add_paragraph(
                "The following elaborates the high-level design's own components, "
                "integration points, deployment topology, and cross-cutting "
                "security, scalability, and availability characteristics."
            )
            for key, label in present:
                if key in bespoke_hld_renderers:
                    bespoke_hld_renderers[key]()
                else:
                    _render_generic_value(
                        doc, high_level_design[key], label=label, level=3, system_name=meta.system_label
                    )
            rendered = True

    # Generate and embed the architecture/component diagram directly from
    # design_data.json so this document does not depend on an earlier tool
    # call having created the image. HLD-only -- it diagrams
    # high_level_design's own components/integration points.
    if rendered:
        add_iso_page_break(doc)
    rendered = _add_flowchart_section(
        doc, meta.name, heading="6.0 Architecture Flow Diagram",
        caption=(
            "This section provides a high-level visualization of the "
            "architecture and the flow between its major components."
        ),
        generate_diagram=True,
        schema_type="design",
    )

    if quality_attributes:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_quality_attributes_section(doc, quality_attributes, heading="7.0 Quality Attributes")

    if compliance_and_standards:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_compliance_and_standards_section(
            doc, compliance_and_standards, heading="8.0 Compliance and Standards"
        )

    if risk_register:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_risk_register_section(doc, risk_register, heading="9.0 Risk Register")

    if governance_requirements:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_governance_requirements_section(
            doc, governance_requirements, subject_noun="architecture"
        )

    if continuous_improvement:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_continuous_improvement_section(
            doc, continuous_improvement, subject_noun="architecture"
        )

    if operational_readiness:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_operational_readiness_section(
            doc, operational_readiness, heading="18.0 Operational Readiness"
        )

    review_and_governance = data.get("review_and_governance")
    if review_and_governance:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_review_governance_checklist_section(
            doc, review_and_governance, heading="19.0 Review and Governance"
        )

    # review_and_governance's OTHER fields (review_history/change_log/
    # approval_workflow) are deliberately NOT rendered above -- they're
    # fabricated by the generating LLM with no grounding (invented reviewer
    # names, invented dates) and add no value. review_and_governance stays
    # in _DESIGN_CONSUMED_KEYS so those fields don't
    # reappear via the Appendix B leftover-data catch-all below.

    rendered = _add_design_trailing_sections(doc, data, rendered)

    _renumber_design_document_headings(doc)

    out_path = paths.output_path(f"{safe_filename_component(meta.name + ' HLD')}.docx")
    doc.save(out_path)
    return out_path


def _build_lld_document(doc: docx.Document, data: dict, process_name: str, has_hld_companion: bool) -> str:
    """
    Builds the Low-Level Design document: implementation-ready component
    detail (interfaces, data models, sequence flows, configuration,
    operations) for an implementing engineer, as a standalone document.
    `has_hld_companion` controls whether the Low-Level Design section's
    own intro mentions a separate High-Level Design document exists
    alongside it. Caller guarantees `data.get("low_level_design")` is
    truthy before calling this (see _resolve_design_variant).
    """
    meta = _DesignMeta(data, process_name)
    low_level_design = data.get("low_level_design")

    _add_design_cover_and_toc(doc, meta, "Low-Level Design Document")

    rendered = _add_low_level_design_section(
        doc, low_level_design, heading="1.0 Low-Level Design", system_name=meta.system_label,
        has_hld_companion=has_hld_companion,
    )

    rendered = _add_design_trailing_sections(doc, data, rendered)

    _renumber_design_document_headings(doc)

    out_path = paths.output_path(f"{safe_filename_component(meta.name + ' LLD')}.docx")
    doc.save(out_path)
    return out_path


def _resolve_design_variant(design_variant: Optional[str], data: dict):
    """
    Resolves which design document(s) to build: {"hld"}, {"lld"}, or
    {"hld", "lld"} -- or an "ERROR: ..." string for an invalid/unsatisfiable
    request. `design_variant` is "hld"|"lld"|"both", case-insensitive;
    None/"" is treated as "both".

    "both" (the default) means "whichever of the two the data actually
    supports" -- the same implicit behavior the single combined document
    used to express via in-file section gating, now expressed as file
    selection. If neither high_level_design nor low_level_design has any
    real content, falls back to building the HLD document alone (an
    effectively-empty design still gets a Document Overview/Cover, same
    as today).

    An explicitly-requested "lld" with no low_level_design content present
    is a hard error -- a document titled "Low-Level Design" with nothing
    in it would be actively misleading, not just thin. "hld" has no
    equivalent hard-empty case: Document Overview/Cover always render.
    """
    variant = (design_variant or "both").strip().lower()
    if variant not in ("hld", "lld", "both"):
        return f"ERROR: Unrecognized design_variant '{design_variant}' -- expected 'hld', 'lld', or 'both'."

    has_hld = bool(data.get("high_level_design")) or bool((data.get("architecture_description") or {}))
    has_lld = bool(data.get("low_level_design"))

    if variant == "hld":
        return {"hld"}
    if variant == "lld":
        if not has_lld:
            return "ERROR: Cannot build a Low-Level Design document -- no low_level_design content is present in the saved design data."
        return {"lld"}

    # "both": whichever of the two the data actually supports.
    result = set()
    if has_hld or not has_lld:
        # Always include "hld" unless the data is LLD-only (has_lld but
        # genuinely nothing HLD-shaped) -- mirrors today's "Document
        # Overview always renders" fallback for an otherwise-empty design.
        result.add("hld")
    if has_lld:
        result.add("lld")
    return result or {"hld"}


def _format_design_build_result(results: dict) -> str:
    """Formats the SUCCESS string for _build_design_documents. A single
    file keeps today's exact "SUCCESS: Professional document saved at
    {path}" shape (so every existing "parse the one path out of a SUCCESS
    string" instruction convention on both ports keeps working unchanged).
    A two-file result uses a deliberately distinct shape -- plural
    "documents", a different separator -- so it can never be silently
    mis-parsed by something expecting the singular phrase."""
    if set(results) == {"hld", "lld"}:
        return f"SUCCESS: Professional documents saved -- HLD: {results['hld']}; LLD: {results['lld']}"
    if results:
        return f"SUCCESS: Professional document saved at {next(iter(results.values()))}"
    return "ERROR: No document variant was selected to build."  # unreachable given the resolver above


def _build_design_documents(data: dict, process_name: str, design_variant: Optional[str]) -> str:
    """
    Builds and saves the HLD document, the LLD document, or both,
    depending on `design_variant` -- the design-schema counterpart to
    _build_process_document, except it may produce one OR two .docx files
    (whereas every other schema type in this module produces exactly one).
    Deliberately foundation-level, not a full bespoke renderer for every
    nested design_document_schema.json section the way the process
    document has hand-crafted, data-shape-specific renderers for every
    field: most sections go through _render_generic_value. Sections with
    a bespoke renderer (requirements, system context, quality attributes,
    compliance and standards, risk register, architecture analysis,
    low-level design, glossary and references) live in design_sections.py.
    """
    variant = _resolve_design_variant(design_variant, data)
    if isinstance(variant, str):
        return variant  # already an "ERROR: ..." string

    results = {}
    if "hld" in variant:
        doc = docx.Document()
        apply_theme(doc)
        results["hld"] = _build_hld_document(doc, data, process_name, has_lld_companion=("lld" in variant))
    if "lld" in variant:
        doc = docx.Document()
        apply_theme(doc)
        results["lld"] = _build_lld_document(doc, data, process_name, has_hld_companion=("hld" in variant))

    return _format_design_build_result(results)


# ============================================================
# TOGAF ARCHITECTURE VISION / ARCHITECTURE DEFINITION DOCUMENTS
# ============================================================

# "Architecture Vision Document"/"Architecture Definition Document"/"TOGAF"
# must never leak into document_metadata.system_name/.title and from there
# into the saved filename -- the exact confirmed-bug precedent as design's
# own _strip_design_doc_type_label (a title like "Combined HLD/LLD for X"
# produced a saved file literally named "..._LLD.docx" with the composition
# description baked in).
_TOGAF_DOC_TYPE_LABEL = r"(?:architecture vision document|architecture definition document|togaf)"
_TOGAF_TITLE_LEADING_LABEL_RE = re.compile(
    rf"^\s*{_TOGAF_DOC_TYPE_LABEL}\s*(?:for)?\s*[:\-]?\s*", re.IGNORECASE
)
_TOGAF_TITLE_TRAILING_LABEL_RE = re.compile(
    rf"\s*[:\-]?\s*{_TOGAF_DOC_TYPE_LABEL}\s*$", re.IGNORECASE
)


def _strip_togaf_doc_type_label(title: str) -> str:
    stripped = _TOGAF_TITLE_LEADING_LABEL_RE.sub("", title, count=1)
    stripped = _TOGAF_TITLE_TRAILING_LABEL_RE.sub("", stripped, count=1)
    stripped = stripped.strip(" :-")
    return stripped or title


class _TogafMeta:
    """Small bag of cover-page/title fields derived from document_metadata
    -- shared by both _build_architecture_vision_document and
    _build_architecture_definition_document so the two can never silently
    diverge on how they compute the system's own name."""

    __slots__ = ("name", "version")

    def __init__(self, data: dict, process_name: str):
        metadata = data.get("document_metadata") or {}
        raw_name = str(metadata.get("title") or metadata.get("system_name") or process_name)
        self.name = _strip_togaf_doc_type_label(raw_name)
        self.version = str(metadata.get("version", "1.0"))


# Every top-level togaf_data.json key this renderer knows how to handle,
# across BOTH documents -- same reasoning as design's own
# _DESIGN_CONSUMED_KEYS: each document only renders its own half, but both
# must keep the full set out of their own Additional Data catch-all.
_TOGAF_CONSUMED_KEYS = {
    "document_metadata", "architecture_vision", "architecture_requirements_specification",
    "architecture_principles", "business_architecture", "data_architecture",
    "application_architecture", "technology_architecture", "opportunities_and_solutions",
    "migration_planning", "architecture_compliance_assessment", "glossary_and_references",
    "appendix",
}


def _add_togaf_cover_and_toc(doc: docx.Document, meta: _TogafMeta, subtitle: str) -> None:
    """Cover page + Document Control (version history) + Table of
    Contents -- identical structure for both TOGAF documents, just a
    different subtitle."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(meta.name)
    run.bold = True
    run.font.size = Pt(28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(subtitle).font.size = Pt(18)

    doc.add_paragraph()
    doc.add_paragraph(f"Version: {meta.version}")
    doc.add_paragraph(f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    add_iso_page_break(doc)

    _add_version_history_table(
        doc, version=meta.version, author="Enterprise Architect",
        description="Initial generated TOGAF architecture artifact",
    )

    add_iso_page_break(doc)
    doc.add_heading("Table of Contents", level=1)
    _add_table_of_contents(doc)

    add_iso_page_break(doc)


def _add_togaf_trailing_sections(doc: docx.Document, data: dict, rendered: bool) -> bool:
    """Glossary and References, Appendix, and Additional Data -- common to
    BOTH TOGAF documents, duplicated into each so either one is genuinely
    standalone-usable on its own."""
    glossary_and_references = data.get("glossary_and_references")
    appendix = data.get("appendix") if isinstance(data.get("appendix"), dict) else None

    if glossary_and_references:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_togaf_glossary_and_references_section(doc, glossary_and_references)

    if appendix:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_appendix_from_json(doc, appendix, subject_noun="architecture")

    if rendered:
        add_iso_page_break(doc)
    rendered = _add_additional_data_section(doc, data, _TOGAF_CONSUMED_KEYS)

    return rendered


def _build_architecture_vision_document(
    doc: docx.Document, data: dict, process_name: str, has_definition_companion: bool,
) -> str:
    """Builds the Architecture Vision Document: ADM Phase A, the
    Architecture Requirements Specification, and Architecture Principles
    -- everything a stakeholder needs to understand WHY this architecture
    exists and WHAT it must satisfy, as a standalone document."""
    meta = _TogafMeta(data, process_name)

    _add_togaf_cover_and_toc(doc, meta, "Architecture Vision Document")

    rendered = True
    doc.add_heading("Document Overview", level=1)
    overview = (
        "This document presents the Architecture Vision for "
        f"{meta.name}, including its formal requirements and the "
        "architecture principles guiding it."
    )
    if has_definition_companion:
        overview += (
            " A companion Architecture Definition Document elaborates the "
            "business, data, application, and technology architecture "
            "derived from this vision."
        )
    doc.add_paragraph(overview)

    architecture_vision = data.get("architecture_vision")
    if architecture_vision:
        add_iso_page_break(doc)
        rendered = _add_architecture_vision_section(doc, architecture_vision, heading="1.0 Architecture Vision")

    ars = data.get("architecture_requirements_specification")
    if ars:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_architecture_requirements_section(
            doc, ars, heading="2.0 Architecture Requirements Specification",
        )

    architecture_principles = data.get("architecture_principles")
    if architecture_principles:
        if rendered:
            add_iso_page_break(doc)
        rendered = _add_architecture_principles_section(
            doc, architecture_principles, heading="3.0 Architecture Principles",
        )

    rendered = _add_togaf_trailing_sections(doc, data, rendered)

    _renumber_design_document_headings(doc)

    out_path = paths.output_path(f"{safe_filename_component(meta.name + ' Architecture Vision')}.docx")
    doc.save(out_path)
    return out_path


def _build_architecture_definition_document(
    doc: docx.Document, data: dict, process_name: str, has_vision_companion: bool,
) -> str:
    """Builds the Architecture Definition Document: Business, Data,
    Application, and Technology Architecture, Opportunities and Solutions,
    Migration Planning, and the Architecture Compliance Assessment --
    everything a reader needs to understand HOW this architecture is
    structured and the plan to get there, as a standalone document."""
    meta = _TogafMeta(data, process_name)

    _add_togaf_cover_and_toc(doc, meta, "Architecture Definition Document")

    rendered = True
    doc.add_heading("Document Overview", level=1)
    overview = (
        f"This document presents the Architecture Definition for {meta.name}: "
        "its business, data, application, and technology architecture, the "
        "gaps between its current and target state, the plan to migrate "
        "toward it, and its compliance against known standards and "
        "requirements."
    )
    if has_vision_companion:
        overview += (
            " A companion Architecture Vision Document states the business "
            "goals and formal requirements this architecture satisfies."
        )
    doc.add_paragraph(overview)

    sections = (
        ("business_architecture", "4.0 Business Architecture", _add_business_architecture_section),
        ("data_architecture", "5.0 Data Architecture", _add_data_architecture_section),
        ("application_architecture", "6.0 Application Architecture", _add_application_architecture_section),
        ("technology_architecture", "7.0 Technology Architecture", _add_technology_architecture_section),
        ("opportunities_and_solutions", "8.0 Opportunities and Solutions", _add_opportunities_and_solutions_section),
        ("migration_planning", "9.0 Migration Planning", _add_migration_planning_section),
        (
            "architecture_compliance_assessment", "10.0 Architecture Compliance Assessment",
            _add_architecture_compliance_assessment_section,
        ),
    )
    for key, heading, renderer in sections:
        value = data.get(key)
        if value:
            if rendered:
                add_iso_page_break(doc)
            rendered = renderer(doc, value, heading=heading)

    rendered = _add_togaf_trailing_sections(doc, data, rendered)

    _renumber_design_document_headings(doc)

    out_path = paths.output_path(f"{safe_filename_component(meta.name + ' Architecture Definition')}.docx")
    doc.save(out_path)
    return out_path


def _resolve_togaf_variant(togaf_variant: Optional[str], data: dict):
    """
    Resolves which TOGAF document(s) to build: {"vision"}, {"definition"},
    or {"vision", "definition"} -- or an "ERROR: ..." string for an
    invalid/unsatisfiable request. `togaf_variant` is
    "vision"|"definition"|"both", case-insensitive; None/"" is treated as
    "both". Mirrors _resolve_design_variant's own contract exactly.

    Unlike design's LLD (which has a hard-empty case -- a document titled
    "Low-Level Design" with nothing in it would be actively misleading),
    the Architecture Vision Document has no equivalent: Document Overview
    always renders, and architecture_vision/architecture_requirements_
    specification/architecture_principles are foundational content
    TOGAF_Agent always populates. An explicitly-requested "definition"
    with NONE of its own content present is the one hard-empty case here.
    """
    variant = (togaf_variant or "both").strip().lower()
    if variant not in ("vision", "definition", "both"):
        return f"ERROR: Unrecognized togaf_variant '{togaf_variant}' -- expected 'vision', 'definition', or 'both'."

    has_definition = any(
        data.get(key) for key in (
            "business_architecture", "data_architecture", "application_architecture",
            "technology_architecture", "opportunities_and_solutions", "migration_planning",
            "architecture_compliance_assessment",
        )
    )

    if variant == "vision":
        return {"vision"}
    if variant == "definition":
        if not has_definition:
            return (
                "ERROR: Cannot build an Architecture Definition Document -- no business, data, "
                "application, or technology architecture content is present in the saved TOGAF data."
            )
        return {"definition"}

    # "both": whichever the data actually supports -- always include
    # "vision" (foundational, always has something), include "definition"
    # only if it has real content.
    result = {"vision"}
    if has_definition:
        result.add("definition")
    return result


def _format_togaf_build_result(results: dict) -> str:
    """Formats the SUCCESS string for _build_togaf_documents. Mirrors
    _format_design_build_result's own two-shape convention exactly."""
    if set(results) == {"vision", "definition"}:
        return f"SUCCESS: Professional documents saved -- Vision: {results['vision']}; Definition: {results['definition']}"
    if results:
        return f"SUCCESS: Professional document saved at {next(iter(results.values()))}"
    return "ERROR: No document variant was selected to build."  # unreachable given the resolver above


def _build_togaf_documents(data: dict, process_name: str, togaf_variant: Optional[str]) -> str:
    """
    Builds and saves the Architecture Vision Document, the Architecture
    Definition Document, or both, depending on `togaf_variant` -- the
    TOGAF-schema counterpart to _build_design_documents.
    """
    variant = _resolve_togaf_variant(togaf_variant, data)
    if isinstance(variant, str):
        return variant  # already an "ERROR: ..." string

    results = {}
    if "vision" in variant:
        doc = docx.Document()
        apply_theme(doc)
        results["vision"] = _build_architecture_vision_document(
            doc, data, process_name, has_definition_companion=("definition" in variant),
        )
    if "definition" in variant:
        doc = docx.Document()
        apply_theme(doc)
        results["definition"] = _build_architecture_definition_document(
            doc, data, process_name, has_vision_companion=("vision" in variant),
        )

    return _format_togaf_build_result(results)


# ============================================================
# HEADING RENUMBERING (design document)
# ============================================================

_LEADING_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\s+")
_APPENDIX_PREFIX_RE = re.compile(r"^Appendix\s+[A-Za-z]:\s*", re.IGNORECASE)
_SUBSECTION_NUMBER_RE = re.compile(r"^\d+\.(\d+)\s+(.*)$")


def _set_paragraph_text(paragraph, new_text: str) -> None:
    """Replaces a heading paragraph's visible text while keeping its
    existing run formatting. doc.add_heading() always creates the heading
    text in a single run, so this only needs to touch runs[0]."""
    if not paragraph.runs:
        paragraph.add_run(new_text)
        return
    paragraph.runs[0].text = new_text
    for extra_run in paragraph.runs[1:]:
        extra_run.text = ""


def _renumber_design_document_headings(doc: docx.Document) -> None:
    """
    Re-derives every top-level section number and appendix letter from
    the FINAL, actual set of Heading 1 paragraphs in the document, in the
    order they were really rendered -- rather than trusting the literal
    "N.0 ..."/"Appendix X: ..." text each section-adding function
    hardcodes when it writes its own heading.

    This is necessary because several section renderers here carry fixed
    numbers that assume every earlier optional section always renders,
    which is not the normal case -- which sections render depends on
    what's actually present in the source JSON. Renumbering after the
    fact sidesteps collisions/gaps: a section that didn't render is
    simply not there to be numbered.

    Heading 2 subsections (e.g. "12.1 Runtime Processing and Sequence
    Flows") are also corrected: their trailing ".Y title" is kept as-is,
    and only the leading section number is swapped for whatever
    `section_no` its enclosing Heading 1 was actually just corrected to.
    """
    section_no = 0
    appendix_idx = 0
    for paragraph in doc.paragraphs:
        if paragraph.style is None:
            continue

        if paragraph.style.name == "Heading 2":
            match = _SUBSECTION_NUMBER_RE.match(paragraph.text)
            if match and section_no:
                subsection_idx, rest = match.groups()
                _set_paragraph_text(paragraph, f"{section_no}.{subsection_idx} {rest}")
            continue

        if paragraph.style.name != "Heading 1":
            continue
        text = paragraph.text

        if _APPENDIX_PREFIX_RE.match(text):
            rest = _APPENDIX_PREFIX_RE.sub("", text).strip()
            letter = chr(ord("A") + appendix_idx)
            appendix_idx += 1
            _set_paragraph_text(paragraph, f"Appendix {letter}: {rest}")
        elif _LEADING_NUMBER_RE.match(text):
            rest = _LEADING_NUMBER_RE.sub("", text).strip()
            section_no += 1
            _set_paragraph_text(paragraph, f"{section_no}.0 {rest}")
        # else: unnumbered heading (Document Control, Table of Contents) -- leave as-is.
