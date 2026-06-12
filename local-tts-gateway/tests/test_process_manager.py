import asyncio

import pytest


def test_ensure_started_returns_existing_healthy_state():
    from app.core.state import ProviderRuntimeState
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="test-provider",
        provider_type="f5-tts",
        display_name="Test Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/AiModel/tts/F5-TTS",
            cwd="E:/AiModel/tts/F5-TTS",
            command=["python", "api.py"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5102,
            base_url="http://127.0.0.1:5102",
            healthcheck_path="/health",
        ),
        capabilities=CapabilityConfig(voices=True, synthesize=True, clone=False, stream=False),
    )

    manager = ProcessManager({provider.provider_id: provider})
    manager._states[provider.provider_id] = ProviderRuntimeState(
        provider_id=provider.provider_id,
        status="healthy",
        pid=1234,
        port=provider.network.port,
    )

    state = asyncio.run(manager.ensure_started(provider.provider_id))

    assert state.status == "healthy"
    assert state.pid == 1234


def test_ensure_started_rejects_unknown_provider():
    from app.core.exceptions import ProviderNotFoundError
    from app.services.process_manager import ProcessManager

    manager = ProcessManager({})

    with pytest.raises(ProviderNotFoundError):
        asyncio.run(manager.ensure_started("missing"))


def test_ensure_started_starts_stopped_provider():
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="lazy-provider",
        provider_type="f5-tts",
        display_name="Lazy Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/AiModel/tts/F5-TTS",
            cwd="E:/AiModel/tts/F5-TTS",
            command=["python", "api.py"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5102,
            base_url="http://127.0.0.1:5102",
            healthcheck_path="/health",
        ),
        capabilities=CapabilityConfig(voices=True, synthesize=True, clone=False, stream=False),
    )

    manager = ProcessManager({provider.provider_id: provider})

    started = []

    async def fake_launcher(provider_config):
        started.append(provider_config.provider_id)
        return 9999

    async def fake_initial_healthcheck(provider_id):
        return False

    async def fake_wait_until_healthy(provider_id):
        return True

    manager._launch_process = fake_launcher
    manager.healthcheck = fake_initial_healthcheck
    manager._wait_until_healthy = fake_wait_until_healthy

    state = asyncio.run(manager.ensure_started(provider.provider_id))

    assert started == ["lazy-provider"]
    assert state.status == "healthy"
    assert state.pid == 9999
