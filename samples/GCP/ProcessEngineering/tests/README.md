# ProcessEngineering tests

The tests use Python's standard `unittest` runner and stub optional ADK/runtime
dependencies where appropriate, so the focused suite can run without installing
the full application stack. The suite covers utility validation and persistence,
OpenAPI request boundaries, Monte Carlo simulation and scenario handling, plus
edge-inference and subprocess-diagram helper logic.

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
