# process_agents/agent.py
#
# Compatibility shim: the implementation now lives in
# process_agents.common.agent. This file stays at the original path so
# `python -m process_agents.agent`, `adk run process_agents`, and `adk web`
# (which expects `agent.py` with a `root_agent` at the app's top level)
# keep working exactly as before the process/design/common/cloudarch split.
#
# The `__main__`/import branches are mutually exclusive so the target
# module's top-level code (agent construction, etc.) runs exactly once
# either way, not twice.

if __name__ == "__main__":
    import runpy
    runpy.run_module("process_agents.common.agent", run_name="__main__")
else:
    from process_agents.common.agent import *  # noqa: F401,F403
    from process_agents.common.agent import root_agent  # noqa: F401
