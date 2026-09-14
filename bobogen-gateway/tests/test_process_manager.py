import asyncio
import subprocess

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

    async def fake_healthcheck(provider_id):
        return True

    manager.healthcheck = fake_healthcheck

    state = asyncio.run(manager.ensure_started(provider.provider_id))

    assert state.status == "healthy"
    assert state.pid == 1234


def test_ensure_started_restarts_stale_healthy_state():
    from app.core.state import ProviderRuntimeState
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="stale-provider",
        provider_type="qwen3-asr",
        display_name="Stale Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/services/qwen3-asr-service",
            cwd="E:/services/qwen3-asr-service",
            command=["python", "-m", "app.main"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5110,
            base_url="http://127.0.0.1:5110",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )

    manager = ProcessManager({provider.provider_id: provider})
    manager._states[provider.provider_id] = ProviderRuntimeState(
        provider_id=provider.provider_id,
        status="healthy",
        pid=27976,
        port=provider.network.port,
    )
    health_results = [False, False, False]
    launched = []

    async def fake_healthcheck(provider_id):
        return health_results.pop(0) if health_results else True

    async def fake_launcher(provider_config):
        launched.append(provider_config.provider_id)
        return 30001

    async def fake_wait_until_healthy(provider_id, process=None):
        return True

    manager.healthcheck = fake_healthcheck
    manager._launch_process = fake_launcher
    manager._wait_until_healthy = fake_wait_until_healthy

    state = asyncio.run(manager.ensure_started(provider.provider_id))

    assert launched == ["stale-provider"]
    assert state.status == "healthy"
    assert state.pid == 30001


def test_refresh_state_marks_stale_healthy_provider_stopped():
    from app.core.state import ProviderRuntimeState
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="status-provider",
        provider_type="qwen3-asr",
        display_name="Status Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/services/qwen3-asr-service",
            cwd="E:/services/qwen3-asr-service",
            command=["python", "-m", "app.main"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5110,
            base_url="http://127.0.0.1:5110",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )
    manager = ProcessManager({provider.provider_id: provider})
    manager._states[provider.provider_id] = ProviderRuntimeState(
        provider_id=provider.provider_id,
        status="healthy",
        pid=27976,
        port=provider.network.port,
    )

    async def fake_healthcheck(provider_id):
        return False

    manager.healthcheck = fake_healthcheck

    state = asyncio.run(manager.refresh_state(provider.provider_id))

    assert state.status == "stopped"
    assert state.pid is None
    assert state.last_error == "healthcheck failed"


def test_stop_terminates_windows_provider_process_tree_and_clears_runtime_state(monkeypatch):
    import app.services.process_manager as process_manager
    from app.core.state import ProviderRuntimeState
    from app.schemas.provider import CapabilityConfig, NetworkConfig, ProviderConfig, RuntimeConfig
    from app.services.process_manager import ProcessManager

    provider = ProviderConfig(
        provider_id="tree-provider",
        provider_type="qwen3-asr",
        display_name="Tree Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/services/qwen3-asr-service",
            cwd="E:/services/qwen3-asr-service",
            command=["powershell", "-File", "start.ps1"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5112,
            base_url="http://127.0.0.1:5112",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )

    class FakeProcess:
        pid = 4321

        def poll(self):
            return None

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(process_manager.os, "name", "nt")
    monkeypatch.setattr(process_manager.subprocess, "run", fake_run)

    manager = ProcessManager({provider.provider_id: provider})
    manager._processes[provider.provider_id] = FakeProcess()
    manager._states[provider.provider_id] = ProviderRuntimeState(
        provider_id=provider.provider_id,
        status="healthy",
        pid=4321,
        port=provider.network.port,
    )

    asyncio.run(manager.stop(provider.provider_id))

    assert calls == [
        (
            ["taskkill", "/PID", "4321", "/T", "/F"],
            {"check": False, "capture_output": True},
        )
    ]
    assert manager.get_state(provider.provider_id).status == "stopped"
    assert manager.get_state(provider.provider_id).pid is None
    assert provider.provider_id not in manager._processes


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

    async def fake_wait_until_healthy(provider_id, process=None):
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


def test_provider_logs_use_single_combined_log_file(monkeypatch, tmp_path):
    import app.services.process_manager as process_manager
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="combined-provider",
        provider_type="stableaudio3",
        display_name="Combined Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/services/stable-audio3-service",
            cwd="E:/services/stable-audio3-service",
            command=["python", "service.py"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5107,
            base_url="http://127.0.0.1:5107",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )
    log_dir = tmp_path / provider.provider_id
    log_dir.mkdir(parents=True)
    (log_dir / "combined.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setattr(process_manager, "LOG_DIR", tmp_path)

    manager = ProcessManager({provider.provider_id: provider})

    assert manager.get_logs(provider.provider_id, lines=2) == "two\nthree\n"
    assert manager.get_logs(provider.provider_id, stream="stderr", lines=1) == "three\n"


def test_launch_process_redirects_provider_output_to_single_combined_log(monkeypatch, tmp_path):
    import app.services.process_manager as process_manager
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import ProviderConfig, RuntimeConfig, NetworkConfig, CapabilityConfig

    provider = ProviderConfig(
        provider_id="launch-provider",
        provider_type="stableaudio3",
        display_name="Launch Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/services/stable-audio3-service",
            cwd="E:/services/stable-audio3-service",
            command=["python", "service.py"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=5107,
            base_url="http://127.0.0.1:5107",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )
    popen_args = {}

    class FakeProcess:
        pid = 4321

    def fake_popen(command, cwd, env, stdout, stderr):
        popen_args.update({"command": command, "cwd": cwd, "env": env, "stdout": stdout, "stderr": stderr})
        return FakeProcess()

    monkeypatch.setattr(process_manager, "LOG_DIR", tmp_path)
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    manager = ProcessManager({provider.provider_id: provider})
    pid = asyncio.run(manager._launch_process(provider))

    combined_log = tmp_path / provider.provider_id / "combined.log"
    assert pid == 4321
    assert combined_log.exists()
    assert "--- started at " in combined_log.read_text(encoding="utf-8")
    assert popen_args["stdout"].name == str(combined_log)
    assert popen_args["stderr"] == subprocess.STDOUT


def test_launch_process_injects_huggingface_token_only_for_gated_model(monkeypatch, tmp_path):
    import app.services.process_manager as process_manager
    from app.services.process_manager import ProcessManager
    from app.schemas.provider import CapabilityConfig, NetworkConfig, ProviderConfig, RuntimeConfig

    provider = ProviderConfig(
        provider_id="stable-audio-provider",
        model_id="stable_audio_3_small_sfx",
        provider_type="stableaudio3",
        display_name="Stable Audio",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir=str(tmp_path), cwd=str(tmp_path), command=["python", "service.py"], env={},
            startup_timeout_ms=1000, request_timeout_ms=1000, idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(host="127.0.0.1", port=5106, base_url="http://127.0.0.1:5106", healthcheck_path="/health"),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )
    popen_args = {}

    class TokenStore:
        def get(self):
            return "hf_example_secret_1234"

    class FakeProcess:
        pid = 4321

    def fake_popen(command, cwd, env, stdout, stderr):
        popen_args["env"] = env
        return FakeProcess()

    monkeypatch.setattr(process_manager, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    manager = ProcessManager({provider.provider_id: provider}, huggingface_token_store=TokenStore())
    assert asyncio.run(manager._launch_process(provider)) == 4321
    assert popen_args["env"]["HF_TOKEN"] == "hf_example_secret_1234"


def _make_idempotency_provider(provider_id: str, port: int = 5199):
    from app.schemas.provider import CapabilityConfig, NetworkConfig, ProviderConfig, RuntimeConfig

    return ProviderConfig(
        provider_id=provider_id,
        provider_type="qwen3-asr",
        display_name="Idempotency Provider",
        enabled=True,
        runtime=RuntimeConfig(
            root_dir="E:/services/qwen3-asr-service",
            cwd="E:/services/qwen3-asr-service",
            command=["python", "-m", "app.main"],
            env={},
            startup_timeout_ms=1000,
            request_timeout_ms=1000,
            idle_shutdown_seconds=0,
        ),
        network=NetworkConfig(
            host="127.0.0.1",
            port=port,
            base_url=f"http://127.0.0.1:{port}",
            healthcheck_path="/v1/health",
        ),
        capabilities=CapabilityConfig(voices=False, synthesize=False, clone=False, stream=False),
    )


def test_start_adopts_already_healthy_provider_without_launching():
    from app.services.process_manager import ProcessManager

    provider = _make_idempotency_provider("adopt-provider")
    manager = ProcessManager({provider.provider_id: provider})
    launched = []

    async def fail_launcher(provider_config):
        launched.append(provider_config.provider_id)
        return 1

    async def healthy(provider_id):
        return True

    manager._launch_process = fail_launcher
    manager.healthcheck = healthy

    state = asyncio.run(manager.start(provider.provider_id))

    assert state.status == "healthy"
    assert state.pid is None
    assert launched == []


def test_start_reuses_tracked_running_process_without_relaunching():
    from app.services.process_manager import ProcessManager

    provider = _make_idempotency_provider("reuse-provider")
    manager = ProcessManager({provider.provider_id: provider})
    launched = []

    class RunningProcess:
        pid = 777

        def poll(self):
            return None

    async def launcher(provider_config):
        launched.append(provider_config.provider_id)
        return 777

    async def healthy(provider_id):
        return True

    manager._launch_process = launcher
    manager.healthcheck = healthy
    manager._processes[provider.provider_id] = RunningProcess()

    state = asyncio.run(manager.start(provider.provider_id))

    assert state.status == "healthy"
    assert state.pid == 777
    assert launched == []


def test_start_fails_fast_when_spawned_process_exits_before_health():
    from app.core.exceptions import ProviderStartTimeoutError
    from app.services.process_manager import ProcessManager

    provider = _make_idempotency_provider("dead-provider", port=5198)
    manager = ProcessManager({provider.provider_id: provider})
    launched = []

    class DeadProcess:
        pid = 111

        def poll(self):
            return 1

    async def launcher(provider_config):
        launched.append(provider_config.provider_id)
        manager._processes[provider_config.provider_id] = DeadProcess()
        return 111

    async def never_healthy(provider_id):
        return False

    manager._launch_process = launcher
    manager.healthcheck = never_healthy

    with pytest.raises(ProviderStartTimeoutError):
        asyncio.run(manager.start(provider.provider_id))

    assert launched == ["dead-provider"]
    assert manager._processes == {}
    assert manager.get_state(provider.provider_id).status == "failed"
