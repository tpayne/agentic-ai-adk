import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.cloudarch.attack_simulation import simulate_cloudarch_attack


class SimulateCloudarchAttackCodedTool(CodedTool):
    """Runs an adversarial attack-path simulation (unauthenticated access,
    lateral movement, privilege escalation, data exfiltration, credential
    compromise) against the current cloud architecture diagram. Loads the
    diagram itself if no xml_content is passed."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return simulate_cloudarch_attack(args.get("xml_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
