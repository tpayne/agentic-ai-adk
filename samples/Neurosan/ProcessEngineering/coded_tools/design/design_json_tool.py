import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.schema.design_json import (
    load_master_design_json,
    load_design_template,
    load_full_design_context,
    persist_final_design_json,
    validate_design_json,
)


class LoadMasterDesignJsonCodedTool(CodedTool):
    """Loads the existing design-document JSON baseline, or the empty
    template if none exists yet. ALWAYS returns a valid object -- never
    None."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_master_design_json()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class LoadDesignTemplateCodedTool(CodedTool):
    """Loads the empty design-document JSON template, for completeness checks."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_design_template()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class LoadFullDesignContextCodedTool(CodedTool):
    """Loads the existing design-document JSON baseline, pinned to the
    design schema (not auto-detected), for the consultant/scenario-tester/
    update-analyst agents."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return load_full_design_context()

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class ValidateDesignJsonCodedTool(CodedTool):
    """Validates a design-document JSON object against the minimal
    structural rules (document_metadata required fields, document_type
    enum, conditional high_level_design/low_level_design requirement)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return validate_design_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class PersistFinalDesignJsonCodedTool(CodedTool):
    """Validates and writes the final design-document JSON to
    output/design_data.json.

    NOTE: this is called mid-loop (by Design_Doc_Agent, on any iteration
    where it actually changed something) -- NOT only once at the true end
    of a run -- so it must NOT release the pipeline lock here; see
    doc_generation_tool.py's GenerateDesignDocumentCodedTool, which is
    this pipeline's actual last step, for where that happens instead."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return persist_final_design_json(args.get("json_content"))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
