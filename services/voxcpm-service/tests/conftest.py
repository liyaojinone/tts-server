import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "services" / "voxcpm-service"

for path in [
    SERVICE_ROOT,
    ROOT / "bobogen-protocol" / "src",
    ROOT / "bobogen-service-kit" / "src",
]:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


@pytest.fixture(autouse=True)
def isolate_versioned_runtime_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("VOXCPM_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("VOXCPM_OUTPUT_DIR", str(tmp_path / "outputs"))
