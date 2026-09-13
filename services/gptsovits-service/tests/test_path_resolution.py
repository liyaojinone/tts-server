from pathlib import Path
import importlib
import sys


ROOT = Path(__file__).resolve().parents[3]


def reload_handler():
    sys.modules.pop("app.handler", None)
    return importlib.import_module("app.handler")


def test_gptsovits_repo_dir_defaults_to_workspace_models(monkeypatch):
    monkeypatch.delenv("GPTSOVITS_REPO_DIR", raising=False)

    handler = reload_handler()

    assert handler.GPTSOVITS_ROOT == ROOT / "models" / "gpt-sovits" / "repo"


def test_gptsovits_repo_dir_honors_environment_override(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    monkeypatch.setenv("GPTSOVITS_REPO_DIR", str(repo_dir))

    handler = reload_handler()

    assert handler.GPTSOVITS_ROOT == repo_dir


def test_ffmpeg_runtime_defaults_to_the_active_virtual_environment():
    handler = reload_handler()
    python_executable = ROOT / "services" / "gptsovits-service" / ".venv" / "Scripts" / "python.exe"

    assert handler.get_ffmpeg_runtime_dir(python_executable) == python_executable.parents[1] / "ffmpeg"


def test_start_script_uses_the_active_virtual_environment_ffmpeg_runtime():
    start_script = (ROOT / "services" / "gptsovits-service" / "start.ps1").read_text(encoding="utf-8")

    assert '$torchcodecFfmpegDir = Join-Path (Split-Path -Parent (Split-Path -Parent $pythonExe)) "ffmpeg"' in start_script
