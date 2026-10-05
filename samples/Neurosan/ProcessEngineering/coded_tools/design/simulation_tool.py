import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.design.simulation import perform_design_sensitivity_analysis, simulate_design_architecture


class SimulateDesignArchitectureCodedTool(CodedTool):
    """Runs the composite resilience/scalability/security/latency
    simulation over the current design document. Loads the current
    baseline itself if no design_json is passed."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return simulate_design_architecture(args.get("design_json"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class PerformDesignSensitivityAnalysisCodedTool(CodedTool):
    """Ranks components by how much making them fully redundant would
    reduce the design's average blast radius."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return perform_design_sensitivity_analysis(args.get("design_json"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
