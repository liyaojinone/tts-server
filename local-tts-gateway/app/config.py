from pathlib import Path

import yaml

from app.schemas.provider import ProviderConfig


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "configs"
PROVIDER_DIR = CONFIG_DIR / "providers"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_provider_configs(config_dir: Path | None = None) -> list[ProviderConfig]:
    directory = config_dir or PROVIDER_DIR
    providers: list[ProviderConfig] = []
    for path in sorted(directory.glob("*.yaml")):
        providers.append(ProviderConfig.model_validate(load_yaml(path)))
    return providers
