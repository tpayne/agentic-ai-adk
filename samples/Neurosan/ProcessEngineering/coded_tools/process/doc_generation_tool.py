import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.docgen.generation import create_standard_doc_from_file


class GenerateProcessDocumentCodedTool(CodedTool):
    """Generates a structured, ISO-formatted Word document from the current
    process design JSON. "process_name" is an optional fallback title --
    the design JSON's own "process_name" field takes precedence."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        process_name = args.get("process_name") or "Process"
        return create_standard_doc_from_file(process_name, schema_type="process")

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
