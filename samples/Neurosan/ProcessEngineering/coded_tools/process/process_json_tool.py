import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.process_json import (
    load_master_process_json,
    load_process_template,
    persist_final_json,
    validate_process_json,
)


class LoadMasterProcessJsonCodedTool(CodedTool):
    """Loads the existing process JSON baseline, or the empty template if
    none exists yet. ALWAYS returns a valid object -- never None."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_master_process_json()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class LoadProcessTemplateCodedTool(CodedTool):
    """Loads the empty process JSON schema template, for completeness checks."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_process_template()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class ValidateProcessJsonCodedTool(CodedTool):
    """Validates a process JSON object against the minimal structural rules."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return validate_process_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class PersistFinalJsonCodedTool(CodedTool):
    """Validates and writes the final process JSON to output/process_data.json."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return persist_final_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
