import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_interface.itsm.simulation import simulate_itsm_risk_and_coverage


class SimulateItsmRiskCodedTool(CodedTool):
    """Runs the structural risk/coverage analysis over the current ITSM
    process document (role-concentration bottlenecks, missing escalation
    paths, missing SLA measurement fields, outsized CI blast radius,
    RACI coverage gaps). Loads the current baseline itself -- no argument
    needed."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return simulate_itsm_risk_and_coverage()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
