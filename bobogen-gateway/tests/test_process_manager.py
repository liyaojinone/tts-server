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


def test_external_provider_uses_existing_healthy_service_without_launching_process():
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="external-provider",
        provider_type="stableaudio3",
        display_name="External Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="/app/services/stable-audio3-service",
            cwd="/app/services/stable-audio3-service",
            command=[],
            env={},
            launch_mode="external",
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="stable-audio3",
            port=5106,
            base_url="http://stable-audio3:5106",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )

    manager = ProcessManager({provider.provider_id: provider})

    async def fake_healthcheck(provider_id):
        return True

    async def fail_launcher(provider_config):
        raise AssertionError("external providers must not launch local processes")

    manager.healthcheck = fake_healthcheck
    manager._launch_process = fail_launcher

    state = asyncio.run(manager.ensure_started(provider.provider_id))

    assert state.status == "healthy"
    assert state.pid is None


def test_external_provider_reports_compose_start_hint_when_service_is_unavailable():
    from app.core.exceptions import ProviderExternalStartRequiredError
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="stable_audio_3_small_sfx",
        provider_type="stableaudio3",
        display_name="Stable Audio 3 Small-SFX",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="/app/services/stable-audio3-service",
            cwd="/app/services/stable-audio3-service",
            command=[],
            env={},
            launch_mode="external",
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="stable-audio3",
            port=5106,
            base_url="http://stable-audio3:5106",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )

    manager = ProcessManager({provider.provider_id: provider})

    async def fake_healthcheck(provider_id):
        return False

    manager.healthcheck = fake_healthcheck

    with pytest.raises(ProviderExternalStartRequiredError) as exc:
        asyncio.run(manager.ensure_started(provider.provider_id))

    assert exc.value.code == "PROVIDER_EXTERNAL_START_REQUIRED"
    assert "bash start.sh --docker --model stable-audio3" in exc.value.message
    assert exc.value.details["compose_service"] == "stable-audio3"
