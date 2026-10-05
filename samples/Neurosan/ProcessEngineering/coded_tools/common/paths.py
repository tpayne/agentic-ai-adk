"""Shared on-disk locations for this project's artifacts.

Mirrors the ADK sample's PROJECT_ROOT/output/ convention (see
samples/GCP/ProcessEngineering/process_agents/common/utils.py) so the two
samples describe the same artifact shapes even though no code is shared.
"""

import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


def output_path(filename: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, filename)
