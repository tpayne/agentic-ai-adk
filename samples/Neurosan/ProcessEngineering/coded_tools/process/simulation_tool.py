import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.process.simulation import perform_sensitivity_analysis, simulate_process_performance


class SimulateProcessPerformanceCodedTool(CodedTool):
    """Runs a PERT-style Monte Carlo cycle-time simulation over the process
    JSON's declared steps and dependencies. Loads the current baseline
    itself if no process_json is passed."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return simulate_process_performance(args.get("process_json"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class PerformSensitivityAnalysisCodedTool(CodedTool):
    """Ranks process steps by how much cutting their duration 10% would
    improve overall cycle time."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return perform_sensitivity_analysis(args.get("process_json"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
