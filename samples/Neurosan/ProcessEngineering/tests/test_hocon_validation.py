"""Shells out to `ns validate` for every network this port owns (not the
scaffolded example networks neuro-san-studio ships) -- catches a broken
HOCON file (bad "class" path, invalid empty "properties", etc.) that a
pure-Python unit test wouldn't."""

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTED_NETWORKS = [
    "registries/requirements_summary.hocon",
    "registries/requirements_consultant.hocon",
    "registries/cloudarch.hocon",
    "registries/process.hocon",
    "registries/process_consultant.hocon",
    "registries/process_scenario_tester.hocon",
    "registries/process_simulation_query.hocon",
    "registries/cloudarch_consultant.hocon",
    "registries/cloudarch_simulation_query.hocon",
    "registries/cloudarch_finops.hocon",
    "registries/process_update.hocon",
    "registries/design.hocon",
    "registries/design_update.hocon",
    "registries/design_consultant.hocon",
    "registries/design_scenario_tester.hocon",
    "registries/design_simulation_query.hocon",
    "registries/process_architect.hocon",
]

_NS_EXECUTABLE = shutil.which("ns", path=str(PROJECT_ROOT / ".venv" / "bin")) or "ns"


@pytest.mark.parametrize("network_path", PORTED_NETWORKS)
def test_network_passes_structural_validation(network_path):
    result = subprocess.run(
        [_NS_EXECUTABLE, "validate", network_path],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60,
    )
    combined_output = result.stdout + result.stderr
    assert "Validation passed" in combined_output, combined_output
