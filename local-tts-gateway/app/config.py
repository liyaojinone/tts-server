from pathlib import Path
import platform
import sys

import yaml

from app.schemas.provider import ProviderConfig


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "configs"
PROVIDER_DIR = CONFIG_DIR / "providers"

_IS_WIN = sys.platform == "win32"
_IS_LINUX = sys.platform == "linux"


def _platform_skip(filename: str) -> bool:
    """Skip config files meant for other platforms."""
    if _IS_LINUX and filename.endswith("-windows.yaml"):
        return True
    if _IS_WIN and filename.endswith("-linux.yaml"):
        return True
    return False


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_provider_configs(config_dir: Path | None = None) -> list[ProviderConfig]:
    directory = config_dir or PROVIDER_DIR
    providers: list[ProviderConfig] = []
    for path in sorted(directory.glob("*.yaml")):
        if _platform_skip(path.name):
            continue
        providers.append(ProviderConfig.model_validate(load_yaml(path)))
    return providers
