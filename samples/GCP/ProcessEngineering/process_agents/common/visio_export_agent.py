# process_agents/visio_export_agent.py
#
# Standalone, on-demand-only action -- export whatever process/design flow
# diagram, or cloud architecture diagram, is ALREADY saved on disk as a
# real Visio (.vsdx) file. NO re-analysis, NO regeneration, and the saved
# data itself is never modified. Mirrors samples/Neurosan/ProcessEngineering's
# own process_visio_export.hocon / cloudarch_visio_export.hocon networks --
# this is their domain-agnostic standalone-agent counterpart on the ADK
# side, the same way doc_creation_agent.py's own Create_Doc_Agent instance
# is the ADK counterpart to regenerate_document.hocon's own
# Regenerate_Document_Agent.
#
# Two separate agents (not one), since the cloudarch domain needs no
# schema_type determination at all -- same split as the two separate
# Neuro-San networks.

from process_interface.docgen.vsdx_export import build_cloudarch_vsdx, build_process_design_vsdx

from .agent_wrappers import ProcessAgent


def export_process_design_vsdx(schema_type: str) -> str:
    """Exports the current saved process or design flow/architecture diagram as a real Visio (.vsdx) file, from whatever is already saved on disk. Never re-runs analysis, generation, or review, and never modifies the saved process_data.json/design_data.json itself. schema_type ("process" or "design") must be set -- determine it from the user's own request wording."""
    return build_process_design_vsdx(schema_type)


def export_cloudarch_vsdx() -> str:
    """Exports the current saved cloud architecture diagram as a real Visio (.vsdx) file, from whatever is already saved on disk (output/cloudarch_drawio.xml). Never re-runs the cloudarch generate/review loop, and never modifies the saved diagram itself. Takes no arguments."""
    return build_cloudarch_vsdx()


visio_export_agent = ProcessAgent(
    name="Visio_Export_Agent",
    description=(
        "Exports the current process or design flow/architecture diagram as a Visio (.vsdx) file, "
        "from whatever is already saved on disk -- no re-analysis, no regeneration. Use ONLY on an "
        "explicit request naming Visio/.vsdx."
    ),
    instruction_file="common/visio_export_agent.txt",
    tools=[export_process_design_vsdx],
)

cloudarch_visio_export_agent = ProcessAgent(
    name="Cloudarch_Visio_Export_Agent",
    description=(
        "Exports the current cloud architecture diagram as a Visio (.vsdx) file, from whatever is "
        "already saved on disk -- no re-analysis, no regeneration. Use ONLY on an explicit request "
        "naming Visio/.vsdx for the cloud architecture."
    ),
    instruction_file="common/cloudarch_visio_export_agent.txt",
    tools=[export_cloudarch_vsdx],
)
