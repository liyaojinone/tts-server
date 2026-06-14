from pathlib import Path
import os
import platform
import sys

import yaml

from app.schemas.provider import ProviderConfig


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent
CONFIG_DIR = BASE_DIR / "configs"
PROVIDER_DIR = CONFIG_DIR / "providers"

_IS_WIN = sys.platform == "win32"
_IS_LINUX = sys.platform == "linux"


def _platform_skip(filename: str) -> bool:
    """Skip config files meant for other platforms."""
    deployment = os.environ.get("BOBOGEN_DEPLOYMENT", "native").strip().lower()
    if deployment == "docker":
        return not filename.endswith("-docker.yaml")
    if filename.endswith("-docker.yaml"):
        return True
    if _IS_LINUX and filename.endswith("-windows.yaml"):
        return True
    if _IS_WIN and filename.endswith("-linux.yaml"):
        return True
    return False


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _expand_value(value):
    if isinstance(value, str):
        root = Path(os.environ.get("BOBOGEN_ROOT", REPO_ROOT)).resolve()
        return value.replace("${BOBOGEN_ROOT}", str(root))
    if isinstance(value, list):
        return [_expand_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_value(item) for key, item in value.items()}
    return value


def load_provider_configs(config_dir: Path | None = None) -> list[ProviderConfig]:
    directory = config_dir or PROVIDER_DIR
    providers: list[ProviderConfig] = []
    for path in sorted(directory.glob("*.yaml")):
        if _platform_skip(path.name):
            continue
        providers.append(ProviderConfig.model_validate(_expand_value(load_yaml(path))))
    return providers
