from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
for path in [
    ROOT / "services" / "gptsovits-service",
    ROOT / "bobogen-service-kit" / "src",
    ROOT / "bobogen-protocol" / "src",
]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(autouse=True)
def isolate_versioned_runtime_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("GPTSOVITS_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("GPTSOVITS_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("GPTSOVITS_RUNTIME_CONFIG_PATH", str(tmp_path / "runtime" / "tts_infer.yaml"))
