"""sly_data key + helper for scoping output/cloudarch_drawio.xml to the
chat session that's using it, so a diagram left behind by an earlier,
unrelated session is never silently presented as "the current
architecture."

Two different CloudArch-family entry points call
claim_cloudarch_drawio_for_session on this session's first touch of the
subsystem, with different consequences:
  - coded_tools.cloudarch.reset_loop_state_tool.ResetLoopStateCodedTool
    (the generate/refine pipeline's own reset step): if THIS call is the
    first touch, whatever's on disk could only be a stale leftover from
    a different session, so it resets (deletes) it before generation/
    refinement starts.
  - coded_tools.cloudarch.load_drawio_tool.LoadDrawioCodedTool (shared by
    all five read-only query agents -- consultant/simulation/attack-
    simulation/finops, plus CloudArch_Agent/CloudArch_Reviewer_Agent
    themselves): if THIS call is the first touch, a read-only question
    must never destroy data just because the session hasn't looked at
    it yet, so it simply adopts whatever is on disk as this session's
    own, without deleting anything.

Whichever of the two is called FIRST in a given session wins -- sly_data
is scoped to the whole chat session (see
coded_tools.common.pipeline_lock's own docstring), so this is a
per-session one-shot regardless of which CloudArch-family tool makes it
first.
"""

CLOUDARCH_DRAWIO_SESSION_OWNED_KEY = "_cloudarch_drawio_session_owned"


def claim_cloudarch_drawio_for_session(sly_data) -> bool:
    """Returns True only the first time this is called for the current
    chat session; every later call in that same session returns False."""
    if sly_data is None or sly_data.get(CLOUDARCH_DRAWIO_SESSION_OWNED_KEY):
        return False
    sly_data[CLOUDARCH_DRAWIO_SESSION_OWNED_KEY] = True
    return True
