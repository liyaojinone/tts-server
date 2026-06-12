from pathlib import Path
import importlib
import sys


ROOT = Path(__file__).resolve().parents[3]


def reload_handler():
    sys.modules.pop("app.handler", None)
    return importlib.import_module("app.handler")


def test_f5tts_repo_dir_defaults_to_workspace_models(monkeypatch):
    monkeypatch.delenv("F5TTS_REPO_DIR", raising=False)

    handler = reload_handler()

    assert handler.F5_ROOT == ROOT / "models" / "f5-tts" / "repo"


def test_f5tts_repo_dir_honors_environment_override(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    monkeypatch.setenv("F5TTS_REPO_DIR", str(repo_dir))

    handler = reload_handler()

    assert handler.F5_ROOT == repo_dir
