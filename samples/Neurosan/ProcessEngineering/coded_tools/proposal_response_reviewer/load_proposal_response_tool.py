"""Re-export: neuro-san resolves a HOCON "class" entry relative to
coded_tools/<network_name>/, so each network referencing this tool needs its
own module path even though the real implementation is shared and lives in
coded_tools/proposal_response_pipeline/ (the network that also writes it).
"""

from coded_tools.proposal_response_pipeline.load_proposal_response_tool import (
    LoadProposalResponseCodedTool,
)

__all__ = ["LoadProposalResponseCodedTool"]
