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


def validate_provider_configs(providers: list[ProviderConfig]) -> list[ProviderConfig]:
    provider_ids: dict[str, ProviderConfig] = {}
    model_ids: dict[str, ProviderConfig] = {}
    endpoints: dict[tuple[str, int], ProviderConfig] = {}
    process_ports: dict[int, ProviderConfig] = {}

    for provider in providers:
        previous_provider = provider_ids.get(provider.provider_id)
        if previous_provider is not None:
            raise ValueError(
                "Duplicate provider_id "
                f"{provider.provider_id!r}: {previous_provider.display_name!r} and {provider.display_name!r}"
            )
        provider_ids[provider.provider_id] = provider

        model_id = provider.model_id or provider.provider_id
        previous_model = model_ids.get(model_id)
        if previous_model is not None:
            raise ValueError(
                "Duplicate model_id "
                f"{model_id!r}: {previous_model.provider_id!r} and {provider.provider_id!r}"
            )
        model_ids[model_id] = provider

        endpoint = (provider.network.host, provider.network.port)
        previous_endpoint = endpoints.get(endpoint)
        if previous_endpoint is not None:
            raise ValueError(
                "Duplicate network endpoint "
                f"{provider.network.host}:{provider.network.port}: "
                f"{previous_endpoint.provider_id!r} and {provider.provider_id!r}"
            )
        endpoints[endpoint] = provider

        # Local process launchers bind a local socket themselves.  They must not
        # share a port even if a future YAML happens to use a different network
        # host value, otherwise both processes can still contend for the same
        # local listener.
        if provider.runtime.launch_mode == "process":
            previous_process_port = process_ports.get(provider.network.port)
            if previous_process_port is not None:
                raise ValueError(
                    "Duplicate local process port "
                    f"{provider.network.port}: {previous_process_port.provider_id!r} "
                    f"and {provider.provider_id!r}"
                )
            process_ports[provider.network.port] = provider

    return providers


def load_provider_configs(config_dir: Path | None = None) -> list[ProviderConfig]:
    directory = config_dir or PROVIDER_DIR
    providers: list[ProviderConfig] = []
    for path in sorted(directory.glob("*.yaml")):
        if _platform_skip(path.name):
            continue
        providers.append(ProviderConfig.model_validate(_expand_value(load_yaml(path))))
    return validate_provider_configs(providers)
