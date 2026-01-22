# process_agents/doc_generation_agent.py

from google.adk.agents import Agent
import docx
from docx.shared import Inches, Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


from .utils import load_instruction, getProperty

import os
import json

from datetime import datetime
import traceback

import logging
import random
import time

logger = logging.getLogger("ProcessArchitect.DocGen")

# process_agents/doc_generation_agent.py

from .helpers import (
    _add_header,
    _add_bullet,
    _add_version_history_table,
    _add_table_of_contents,
    _add_overview_section,
    _add_stakeholders_section,
    _add_process_steps_section,
    _add_tools_section_from_summary,
    _add_metrics_section,
    _add_critical_success_factors_section,
    _add_critical_failure_factors_section,
    _add_reporting_and_analytics,
    _add_system_requirements,
    _add_flowchart_section,
    _add_simulation_report,
    _add_governance_requirements_section,
    _add_risks_and_controls_section,
    _add_process_triggers_section,
    _add_process_end_conditions_section,
    _add_change_management_section,
    _add_continuous_improvement_section,
    _add_appendix_from_json,
    _add_additional_data_section,
    _add_glossary
)

# -----------------------------------
# Subprocess support
# -----------------------------------

def _load_subprocesses() -> dict:
    """
    Loads all subprocess JSON files from output/subprocesses/.
    Returns a dict: { step_name: subprocess_json }
    """
    logger.debug("Loading subprocess JSON files...")
    subprocess_dir = "output/subprocesses"
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

    logger.debug("Subprocesses loaded...")
    return subprocesses

# ---------------------------------------------------
# Main: Structured process document generation logic
# ---------------------------------------------------

def create_standard_doc_from_file(process_name: str) -> str:
    """
    Generate a structured, professional process document from process_data.json.

    EXPECTATION:
    - process_data.json contains normalized, document-ready JSON as described
      at the top of this file.
    - This function is schema-aware for that normalized format and will:
      * Build a professional title page.
      * Add document control + TOC.
      * Render overview, stakeholders, workflow, tools, metrics, reporting,
        system requirements, flow diagram, and appendices.
    """
    time.sleep(float(getProperty("modelSleep")) + random.random() * 0.75)
    print(f"Creating document for process: {process_name}...")
    logger.debug(f"Creating document for process: {process_name}...")
    try:
        logger.debug(f"Loading process data from output/process_data.json...")
        with open("output/process_data.json", 'r', encoding="utf-8") as f:
            try:
                raw_data = json.load(f)
            except Exception:
                traceback.print_exc()
                return "ERROR: Failed to parse process_data.json"

        if isinstance(raw_data, dict) and "process_design" in raw_data and isinstance(raw_data["process_design"], dict):
            data = raw_data["process_design"]
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            data = {"root": raw_data}

        # Attach subprocesses to steps (if any)
        subprocesses = _load_subprocesses()
        for step in data.get("process_steps", []):
            if isinstance(step, dict):
                name = step.get("step_name")
                if name in subprocesses:
                    step["subprocess"] = subprocesses[name]

        name = str(data.get("process_name", process_name))
        description = data.get("description") or data.get("process_description") or data.get("introduction")
        version = str(data.get("version", "1.0"))
        sector = data.get("industry_sector", data.get("business_unit", data.get("sector", ""))) or "N/A"

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
            "appendix",
            "assumptions",
            "business_unit", 
            "change_management",
            "constraints",
            "continuous_improvement",
            "critical_failure_factors", 
            "critical_success_factors",
            "description", 
            "governance_requirements",
            "industry_sector", 
            "introduction", 
            "metrics",
            "process_description", 
            "process_end_conditions",
            "process_name", 
            "process_steps", 
            "process_triggers",
            "reporting_and_analytics", 
            "risks_and_controls",
            "stakeholders", 
            "success_metrics", 
            "system_requirements", 
            "tools_summary", 
            "version", 
        }

#         for key in consumed_keys:
#             value = data.get(key)
#             print(f"\n=== {key} ===")

#             if value is None:
#                 print("  (missing)")
#                 continue

#             # Show type
#             print(f"  type: {type(value).__name__}")

#             # Pretty-print lists and dicts
#             if isinstance(value, dict):
#                 for k, v in value.items():
#                     print(f"    {k}: {v}")
#             elif isinstance(value, list):
#                 for i, item in enumerate(value):
#                     print(f"    [{i}] {item}")
#             else:
#                 print(f"  value: {value}")

        doc = docx.Document()
        try:
            doc.core_properties.title = name
            doc.core_properties.subject = "Business Process Specification"
            doc.core_properties.category = sector
            doc.core_properties.author = "Process Architect"
        except Exception:
            traceback.print_exc()

        # TITLE PAGE
        try:
            title = doc.add_heading(name, 0)
            if title.runs:
                title.runs[0].font.size = Pt(24)
        except Exception:
            traceback.print_exc()

        if description:
            doc.add_paragraph(str(description))

        p = doc.add_paragraph()
        p.add_run("Industry / Domain: ").bold = True
        p.add_run(str(sector))

        p = doc.add_paragraph()
        p.add_run("Version: ").bold = True
        p.add_run(str(version))

        p = doc.add_paragraph()
        p.add_run("Generated On: ").bold = True
        p.add_run(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        doc.add_page_break()

        # DOCUMENT CONTROL + TOC
        _add_version_history_table(doc, version=version, author="Process Architect")

        doc.add_page_break()
        doc.add_heading("Table of Contents", level=1)
        _add_table_of_contents(doc)
        doc.add_page_break()

        # 1.0 Overview
        _add_overview_section(doc, data)
        doc.add_page_break()

        # 2.0 Stakeholders
        _add_stakeholders_section(doc, stakeholders)
        doc.add_page_break()

        # 3.0 Process Steps
        if process_steps:
            _add_process_steps_section(doc, process_steps)
            doc.add_page_break()

        # 4.0 Tools / Systems (from tools_summary)
        if tools_summary:
            _add_tools_section_from_summary(doc, tools_summary)
            doc.add_page_break()
            
        # 5.0 Metrics
        if isinstance(metrics, list) and metrics:
            _add_metrics_section(doc, metrics)
            doc.add_page_break()

        # 6.0 Metrics
        if isinstance(critical_success_factors, list) and critical_success_factors:
            _add_critical_success_factors_section(doc, critical_success_factors)
            doc.add_page_break()

        # 7.0 Metrics
        if isinstance(critical_failure_factors, list) and critical_failure_factors:
            _add_critical_failure_factors_section(doc, critical_failure_factors)
            doc.add_page_break()

        # 8.0 Reporting & Analytics
        if reporting_and_analytics:
            _add_reporting_and_analytics(doc, reporting_and_analytics)
            doc.add_page_break()

        # 9.0 System Requirements
        if system_requirements:
            _add_system_requirements(doc, system_requirements)
            doc.add_page_break()

        # 10.0 Flow Diagram
        _add_flowchart_section(doc, name)
        doc.add_page_break()

        # Load simulation results if present
        simulation_results = None
        try:
            sim_path = "output/simulation_results.json"
            if os.path.exists(sim_path):
                with open(sim_path, "r", encoding="utf-8") as sf:
                    simulation_results = json.load(sf)
        except Exception:
            traceback.print_exc()
            simulation_results = None

        # 11.0 Process Performance Report (if we have metrics)
        if simulation_results:
            _add_simulation_report(doc, simulation_results)
            doc.add_page_break()

        # 12.0
        if governance_requirements: 
            _add_governance_requirements_section(doc, governance_requirements) 
            doc.add_page_break() 

        # 13.0
        if risks_and_controls: 
            _add_risks_and_controls_section(doc, risks_and_controls) 
            doc.add_page_break() 

        # 14.0
        if process_triggers: 
            _add_process_triggers_section(doc, process_triggers) 
            doc.add_page_break() 

        # 15.0
        if process_end_conditions: 
            _add_process_end_conditions_section(doc, process_end_conditions) 
            doc.add_page_break()

        # 16.0
        if change_management: 
            _add_change_management_section(doc, change_management) 
            doc.add_page_break() 

        # 17.0
        if continuous_improvement: 
            _add_continuous_improvement_section(doc, continuous_improvement) 
            doc.add_page_break()

        # Appendix A: Structured appendix from JSON
        if appendix:
            _add_appendix_from_json(doc, appendix)
            consumed_keys.add("appendix")

        # Appendix B: Remaining JSON
        doc.add_page_break()
        _add_additional_data_section(doc, data, consumed_keys)

        # Appendix C: Glossary
        doc.add_page_break()
        _add_glossary(doc)

        try:
            out_path = f"output/{name.replace(' ', '_')}.docx"
            doc.save(out_path)
            return f"SUCCESS: Professional document saved at {out_path}"
        except Exception:
            traceback.print_exc()
            return "ERROR: Failed to save Word document"

    except Exception as e:
        traceback.print_exc()
        return f"ERROR: {str(e)}"


# --------------------------
# Agent definition
# --------------------------
doc_generation_agent = Agent(
    name="Document_Generation_Agent",
    description="Generates a professional Word document from normalized JSON.",
    instruction=load_instruction("doc_generation_agent.txt"),
    tools=[create_standard_doc_from_file],
)

# ---------------------------------------------------
# Standalone execution for local testing
# ---------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python doc_generation_agent.py <path_to_process_json>")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    logger.debug(f"[Standalone] Loading process JSON from {input_path}...")
    # Load the JSON file the same way the ADK pipeline would
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {e}")
        sys.exit(1)

    # Determine process name
    if isinstance(data, dict) and "process_design" in data:
        process_data = data["process_design"]
    else:
        process_data = data

    process_name = str(process_data.get("process_name", "Process_Document"))

    # Save to output/process_data.json so the generator can use it
    os.makedirs("output", exist_ok=True)
    with open("output/process_data.json", "w", encoding="utf-8") as f:
        json.dump(process_data, f, indent=2, ensure_ascii=False)

    print(f"[Standalone] Saved normalized JSON to output/process_data.json")

    # Call the generator directly
    result = create_standard_doc_from_file(process_name)
    print(f"[Standalone] {result}")
