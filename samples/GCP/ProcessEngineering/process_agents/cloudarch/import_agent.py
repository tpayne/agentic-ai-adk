# process_agents/cloudarch/import_agent.py
#
# Restores an ALREADY-EXISTING cloud architecture diagram -- an already-
# exported drawio/mxGraph XML file, typically one previously downloaded from
# this same toolkit via GET /artifacts/cloudarch/download and re-attached to
# resume work on it -- directly into output/cloudarch_drawio.xml, VERBATIM.
# Mirrors process/import_agent.py and design/import_agent.py's own reasoning
# (standalone agent, same STEP structure), but simpler: unlike a process/
# design document, there is no meaningful "extract a diagram from prose"
# case worth supporting here -- drawio/mxGraph XML is either already a real
# diagram to restore as-is, or it isn't a diagram at all. A request to BUILD
# a new diagram from a directory of background material is a DIFFERENT,
# already-existing capability (cloudarch_agent.py's own directory-context
# path), not this one. Mirrors the neuro-san port's registries/
# cloudarch_import.hocon.

from ..common.utils import load_directory_context, load_drawio, restore_drawio_xml
from ..common.agent_wrappers import ProcessLlmAgent

cloudarch_import_agent = ProcessLlmAgent(
    name="CloudArch_Import_Agent",
    description=(
        "Restores an already-existing cloud architecture diagram -- a drawio/mxGraph XML file, "
        "typically one previously downloaded from this same toolkit -- as the active diagram, "
        "VERBATIM, with no re-interpretation. Not for building a new diagram from a written "
        "description (that's the regular cloud-architecture generation path)."
    ),
    instruction_file="cloudarch/import_agent.txt",
    tools=[load_directory_context, load_drawio, restore_drawio_xml],
)
