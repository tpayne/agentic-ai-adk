import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.subprocess_json import load_process_steps, save_subprocess_flow


class LoadProcessStepsCodedTool(CodedTool):
    """Loads the parent process's top-level process_steps, for the
    front-man to iterate over when expanding each into a subprocess."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return {"process_steps": load_process_steps()}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class SaveSubprocessFlowCodedTool(CodedTool):
    """Persists a generated subprocess flow for one top-level process step
    to its own file under output/subprocesses/."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        step_name = args.get("step_name")
        flow = args.get("subprocess_flow")
        if not step_name or not isinstance(flow, dict):
            return {"status": "ERROR", "error": "step_name and subprocess_flow are both required."}
        return save_subprocess_flow(step_name, flow)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
