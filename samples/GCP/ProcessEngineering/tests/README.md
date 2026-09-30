# ProcessEngineering tests

Most of the suite uses Python's standard `unittest` runner and stubs optional
ADK/runtime dependencies where appropriate, so it can run without installing
the full application stack. The suite covers utility validation and persistence,
OpenAPI request boundaries, Monte Carlo simulation and scenario handling, plus
edge-inference and subprocess-diagram helper logic.

Two modules are the exception: `test_web_service.py` and
`test_cloudarch_drawio_mcp.py` deliberately clear any stub modules other test
files installed and force a real re-import of `process_agents.common.agent`
(which validates model-provider credentials and calls `dotenv.load_dotenv()`
at import time), so they need the real packages from `requirements.txt`
installed -- not just the stub-friendly subset. Running the full suite in an
environment without `requirements.txt` installed will fail those two modules
specifically (`ModuleNotFoundError` for `google`/`dotenv`) while the rest of
the suite still passes.

From the repository root:

```bash
PYTHONPATH=samples/GCP/ProcessEngineering \
  python3 -m unittest discover -s samples/GCP/ProcessEngineering/tests -v
```

To measure coverage after installing `requirements-dev.txt`:

```bash
python3 -m pip install -r samples/GCP/ProcessEngineering/requirements-dev.txt
PYTHONPATH=samples/GCP/ProcessEngineering \
  coverage run -m unittest discover -s samples/GCP/ProcessEngineering/tests
coverage report -m
```
