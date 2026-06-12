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
