# process_agents/helpers/__init__.py

"""
Doc Generation Helpers Package
Organizes Word document construction logic into functional modules.
"""

from .doc_structure import (
    _add_header,
    _add_bullet,
    _add_version_history_table,
    _add_table_of_contents
)

from .doc_content import (
    _add_overview_section,
    _add_stakeholders_section,
    _add_process_steps_section,
    _add_tools_section_from_summary
)

from .doc_technical import (
    _add_metrics_section,
    _add_system_requirements,
    _add_flowchart_section,
    _add_simulation_report
)

from .doc_governance import (
    _add_critical_success_factors_section,
    _add_critical_failure_factors_section,
    _add_reporting_and_analytics,
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