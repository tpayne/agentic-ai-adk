"""Re-export: neuro-san resolves a HOCON "class" entry relative to
coded_tools/<network_name>/, so each network referencing this tool needs its
own module path even though the real implementation is shared and lives in
coded_tools/requirements_summary/ (the network that also writes it).
"""

from coded_tools.requirements_summary.update_requirements_summary_tool import (
    UpdateRequirementsSummaryCodedTool,
)

__all__ = ["UpdateRequirementsSummaryCodedTool"]
