"""Re-export: neuro-san resolves a HOCON "class" entry relative to
coded_tools/<network_name>/, so each network referencing this tool needs its
own module path even though the real implementation is shared and lives in
coded_tools/regenerate_document/ (RegenerateDocumentCodedTool is already
domain-agnostic -- schema_type="requirements" works unchanged).
"""

from coded_tools.regenerate_document.doc_generation_tool import (
    RegenerateDocumentCodedTool,
)

__all__ = ["RegenerateDocumentCodedTool"]
