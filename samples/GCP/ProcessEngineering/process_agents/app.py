# process_agents/app.py
#
# Compatibility shim: the implementation now lives in
# process_agents.common.app. This file stays at the original path so
# `python -m process_agents.app` keeps working unchanged.
#
# The `__main__`/import branches are mutually exclusive so the target
# module's top-level code runs exactly once either way, not twice.

if __name__ == "__main__":
    import runpy
    runpy.run_module("process_agents.common.app", run_name="__main__")
else:
    from process_agents.common.app import *  # noqa: F401,F403
    from process_agents.common.app import app  # noqa: F401
