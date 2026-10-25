import asyncio
import os
from typing import Any, Dict, Union

from neuro_san.interfaces.coded_tool import CodedTool

from process_toolkit import paths

from coded_tools.common.artifact_downloads import (
    CLOUDARCH_FILENAME,
    copy_artifact_to_destination,
    list_output_documents,
    resolve_artifact_target,
)


class DownloadArtifactCodedTool(CodedTool):
    """Saves a copy of a generated artifact (the cloud architecture
    diagram, or a generated Word document) to a local filesystem path on
    the machine this agent process is running on.

    Call this when the user explicitly asks to download/save/export/copy
    a generated artifact to a specific location (e.g. "download the cloud
    architecture diagram to /tmp", "save the design doc to my Desktop").
    Do NOT call this just because a document/diagram was generated --
    only on an explicit request to save a copy somewhere.

    IMPORTANT: this writes a file to the filesystem of whatever machine is
    actually running this agent process. On a purely local CLI session
    that's the user's own machine, exactly as if they'd copied the file
    themselves. If this agent is ever served remotely (e.g. via --flask)
    to a client that is NOT the same person operating the server, this
    tool would write to the SERVER's own filesystem at a remote user's
    request -- a meaningfully different trust boundary. Do not widen this
    agent's remote exposure without reconsidering this tool's own access
    first.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        target = args.get("target")
        destination = args.get("destination")
        if not destination:
            return {
                "status": "ERROR",
                "message": "A destination path is required -- ask the user where to save it.",
            }

        filename = resolve_artifact_target(target)
        if filename is None:
            return {"status": "ERROR", "message": self._not_found_message(target)}

        try:
            dest_path = copy_artifact_to_destination(filename, destination)
        except (ValueError, OSError) as e:
            return {"status": "ERROR", "message": f"Could not save '{filename}' to '{destination}': {e}"}

        return {
            "status": "OK",
            "filename": filename,
            "destination": dest_path,
            "message": f"Saved '{filename}' to {dest_path}.",
        }

    def _not_found_message(self, target: Any) -> str:
        available = [doc["filename"] for doc in list_output_documents()]
        if os.path.isfile(os.path.join(paths.output_dir(), CLOUDARCH_FILENAME)):
            available.insert(0, "the cloud architecture diagram (cloudarch_drawio.xml)")
        listing = ", ".join(available) if available else "nothing has been generated yet"
        target_desc = f"'{target}'" if target else "(no target specified)"
        return f"Could not find a generated artifact matching {target_desc}. Available: {listing}."

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Union[Dict[str, Any], str]:
        return await asyncio.to_thread(self.invoke, args, sly_data)
