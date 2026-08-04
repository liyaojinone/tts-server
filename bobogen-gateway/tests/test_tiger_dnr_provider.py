import asyncio
from pathlib import Path

import httpx
import pytest


def test_tiger_dnr_provider_uses_async_separation_service():
    from app.config import load_provider_configs

    config_dir = (
        Path(__file__).resolve().parents[1]
        / "configs"
        / "providers"
    )
    providers = {
        provider.provider_id: provider
        for provider in load_provider_configs(config_dir)
    }

    provider = providers["tiger_dnr"]
    assert provider.model_id == "tiger-dnr"
    assert provider.provider_type == "tiger-dnr"
    assert provider.tasks == ["audio.separate"]
    assert provider.runtime.root_dir.endswith(
        r"services\tiger-dnr-service"
    )
    assert provider.runtime.command[:2] == ["powershell", "-File"]
    assert provider.runtime.command[2].endswith(
        r"services\tiger-dnr-service\start.ps1"
    )
    assert provider.runtime.env["TIGER_DNR_HF_REPO_ID"] == (
        "JusperLee/TIGER-DnR"
    )
    assert provider.runtime.env["TIGER_DNR_HF_REVISION"] == (
        "b7a59560bbca10febbcd46fb01600f868e587f57"
    )
    assert provider.runtime.env["TIGER_DNR_DEVICE"] == "cuda:0"
    assert provider.runtime.env["TIGER_DNR_PORT"] == "5114"
    assert provider.network.port == 5114
    assert provider.network.base_url == "http://127.0.0.1:5114"
    assert provider.capabilities.synthesize is False


def test_tiger_dnr_registry_adapter_and_model_schema():
    from app.main import create_app

    app = create_app()
    registry = app.state.provider_registry

    assert registry.get_adapter("tiger_dnr").provider_type == "tiger-dnr"

    from fastapi.testclient import TestClient

    response = TestClient(app).get("/v1/models/tiger-dnr")
    assert response.status_code == 200
    payload = response.json()
    assert payload["tasks"] == ["audio.separate"]
    assert payload["outputs"] == ["audio/wav"]
    assert payload["capabilities"]["separation"] is True
    assert payload["capabilities"]["async_jobs"] is True
    assert payload["capabilities"]["artifact_roles"] == [
        "dialogue",
        "background",
    ]
    assert payload["input_schema"]["required"] == ["audio"]
    assert payload["examples"][0]["request"]["task"] == "audio.separate"


def test_tiger_dnr_adapter_maps_network_failure_to_provider_unavailable(
    monkeypatch,
):
    from app.core.exceptions import ProviderUnavailableError
    from app.main import create_app

    app = create_app()
    registry = app.state.provider_registry
    provider = registry.get_provider("tiger_dnr")
    adapter = registry.get_adapter("tiger_dnr")

    async def fail_request(_client, method, url, **_kwargs):
        request = httpx.Request(
            method,
            f"http://127.0.0.1:5114{url}",
        )
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr(
        httpx.AsyncClient,
        "request",
        fail_request,
    )

    with pytest.raises(ProviderUnavailableError) as captured:
        asyncio.run(adapter.get_job(provider, "network-failure"))

    assert captured.value.status_code == 503
    assert captured.value.details["provider_id"] == "tiger_dnr"


def test_tiger_dnr_adapter_opens_upstream_before_return_and_closes_stream(
    monkeypatch,
):
    from app.main import create_app

    app = create_app()
    registry = app.state.provider_registry
    provider = registry.get_provider("tiger_dnr")
    adapter = registry.get_adapter("tiger_dnr")
    events = []

    async def fake_get_job(_provider, job_id):
        return {
            "artifacts": [
                {
                    "id": "dialogue-artifact",
                    "content_type": "audio/wav",
                    "filename": "dialogue.wav",
                    "size_bytes": 6,
                }
            ]
        }

    class FakeResponse:
        is_error = False

        async def aiter_bytes(self):
            yield b"abc"
            yield b"def"

        async def aclose(self):
            events.append("response-close")

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            events.append("client-create")

        def build_request(self, method, path):
            return httpx.Request(
                method,
                f"http://127.0.0.1:5114{path}",
            )

        async def send(self, request, *, stream):
            assert request.url.path == (
                "/v1/jobs/job-1/artifacts/dialogue-artifact"
            )
            assert stream is True
            events.append("upstream-enter")
            return FakeResponse()

        async def aclose(self):
            events.append("client-close")

    monkeypatch.setattr(adapter, "get_job", fake_get_job)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    async def scenario():
        artifact = await adapter.get_artifact(
            provider,
            "job-1",
            "dialogue-artifact",
        )
        assert events == ["client-create", "upstream-enter"]
        body = b"".join(
            [
                chunk
                async for chunk in artifact["stream"]
            ]
        )
        assert body == b"abcdef"
        assert events == [
            "client-create",
            "upstream-enter",
            "response-close",
            "client-close",
        ]

    asyncio.run(scenario())


def test_tiger_dnr_service_entrypoints_use_local_model_and_venv():
    repo_root = Path(__file__).resolve().parents[2]
    service_root = repo_root / "services" / "tiger-dnr-service"

    powershell = (service_root / "start.ps1").read_text(
        encoding="utf-8"
    )
    shell = (service_root / "start.sh").read_text(
        encoding="utf-8"
    )
    pyproject = (service_root / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert r"models\tiger\repo" in powershell
    assert r"models\tiger\TIGER-DnR" in powershell
    assert r".venv\Scripts\python.exe" in powershell
    assert "NUMBA_CACHE_DIR" in powershell
    assert "TIGER_DNR_HF_REVISION" in powershell
    assert "models/tiger/repo" in shell
    assert "models/tiger/TIGER-DnR" in shell
    assert ".venv/bin/python" in shell
    assert "NUMBA_CACHE_DIR" in shell
    assert "TIGER_DNR_HF_REVISION" in shell
    assert "soundfile" in pyproject
    assert "scipy" in pyproject
    assert "huggingface-hub" in pyproject
    assert "pytorch-lightning" in pyproject
    assert "safetensors" in pyproject
    assert "torch-complex" in pyproject
