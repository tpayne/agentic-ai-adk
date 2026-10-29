"""CodedTools for CloudArch_IaC_Pipeline: persisting the IaC files
CloudArch_IaC_Agent writes, validating their syntax, and zipping the
result into a single downloadable archive.

The actual generation/validation/zip logic all lives in
process_toolkit.iac (generation.py/validation.py) -- shared with the ADK
port -- these classes are purely the neuro-san CodedTool adapters around
it, same division of labor as every other coded_tools/*/*.py module in
this project.
"""

import asyncio
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit.iac.generation import load_iac_files, save_iac_files, zip_iac_files
from process_toolkit.iac.validation import validate_iac_files

from coded_tools.common.pipeline_lock import PIPELINE_LOCK_TOKEN_KEY
from process_toolkit.run_lock import release_pipeline_lock, stop_pipeline_lock_heartbeat


class SaveIacFilesCodedTool(CodedTool):
    """Persists the IaC files CloudArch_IaC_Agent just wrote. "files" is
    {relative_filename: content} -- the COMPLETE set for this pass, not a
    diff; each call replaces whatever was saved by the previous one (see
    save_iac_files's own docstring for why)."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        files = args.get("files")
        if not isinstance(files, dict) or not files:
            return {"status": "ERROR", "message": "'files' must be a non-empty object of {filename: content}."}
        written = save_iac_files(files)
        return {"status": "OK", "files_written": sorted(written.keys())}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class ValidateIacFilesCodedTool(CodedTool):
    """Re-reads whatever is currently persisted (never trusts a tool-call
    argument echoed back to it -- always validates what was ACTUALLY
    written) and checks each file's syntax."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        files = load_iac_files()
        if not files:
            return {"status": "ERROR", "message": "No IaC files have been saved yet -- nothing to validate."}
        result = validate_iac_files(files)
        return {"status": "OK", **result}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)


class ZipIacFilesCodedTool(CodedTool):
    """Zips the currently-saved IaC files into output/<session>/
    cloudarch_iac.zip. This is CloudArch_IaC_Pipeline's own genuine last
    guaranteed step (reset_loop_state -> generate/validate loop -> THIS)
    -- on success, also releases the shared output/ directory's pipeline
    lock (see process_toolkit.run_lock), same pattern as design.hocon's
    own GenerateDesignDocumentCodedTool. release_pipeline_lock(None) is a
    safe no-op for any other caller that never acquired a lock."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        try:
            zip_path = zip_iac_files()
        except FileNotFoundError as e:
            return {"status": "ERROR", "message": str(e)}
        token = sly_data.get(PIPELINE_LOCK_TOKEN_KEY)
        stop_pipeline_lock_heartbeat(token)
        release_pipeline_lock(token)
        return {"status": "OK", "zip_path": zip_path}

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
