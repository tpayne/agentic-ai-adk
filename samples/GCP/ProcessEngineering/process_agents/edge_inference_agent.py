# process_agents/edge_inference_agent.py
#
# Compatibility shim: the implementation now lives in
# process_agents.common.edge_inference_agent. This file stays at the
# original path so `python -m process_agents.edge_inference_agent <args>`
# keeps working unchanged.
#
# The `__main__`/import branches are mutually exclusive so the target
# module's top-level code runs exactly once either way, not twice.

if __name__ == "__main__":
    import runpy
    runpy.run_module("process_agents.common.edge_inference_agent", run_name="__main__")
else:
    from process_agents.common.edge_inference_agent import *  # noqa: F401,F403
