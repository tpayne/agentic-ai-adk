import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.cloudarch.simulation import simulate_cloudarch_architecture


class SimulateCloudarchArchitectureCodedTool(CodedTool):
    """Runs structural resilience (Monte Carlo blast-radius), scalability
    (fan-in bottleneck), and latency (deepest dependency chain) analysis
    against the current cloud architecture diagram. Loads the diagram
    itself if no xml_content is passed."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return simulate_cloudarch_architecture(args.get("xml_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
