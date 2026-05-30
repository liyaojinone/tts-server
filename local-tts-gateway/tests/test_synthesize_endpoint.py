from fastapi.testclient import TestClient


def test_synthesize_endpoint_calls_manager_and_adapter():
    from app.main import create_app
    from app.services.audio_service import AudioResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    calls = {"started": [], "synthesized": []}

    async def fake_ensure_started(provider_id):
        calls["started"].append(provider_id)
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def list_voices(self, provider):
            return {"voices": []}

        async def synthesize(self, provider, request, files=None):
            calls["synthesized"].append((provider.provider_id, request.text))
            return AudioResult(
                content=b"RIFF",
                content_type="audio/wav",
                duration_seconds=1.23,
                sample_rate=24000,
                format="wav",
            )

        async def healthcheck(self, provider):
            return True

    manager.ensure_started = fake_ensure_started
    registry._adapters["f5tts-default"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/providers/f5tts-default/synthesize",
        json={
            "text": "你好",
            "voice_id": "f5-default",
            "language": "zh",
            "parameters": {"reference_audio": "E:/AiModel/tts/ref.wav"},
            "output": {"format": "wav", "sample_rate": 24000},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-provider-id"] == "f5tts-default"
    assert calls["started"] == ["f5tts-default"]
    assert calls["synthesized"] == [("f5tts-default", "你好")]


def test_synthesize_alias_route_uses_provider_id_from_body():
    from app.main import create_app
    from app.services.audio_service import AudioResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    calls = {"started": [], "synthesized": []}

    async def fake_ensure_started(provider_id):
        calls["started"].append(provider_id)
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def list_voices(self, provider):
            return {"voices": []}

        async def synthesize(self, provider, request, files=None):
            calls["synthesized"].append((provider.provider_id, request.text))
            return AudioResult(content=b"RIFF", content_type="audio/wav")

        async def healthcheck(self, provider):
            return True

    manager.ensure_started = fake_ensure_started
    registry._adapters["gptsovits-default"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/synthesize",
        json={
            "provider_id": "gptsovits-default",
            "text": "你好",
            "voice_id": "default",
            "language": "zh",
            "parameters": {"reference_audio": "E:/AiModel/tts/ref.wav"},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert response.headers["x-provider-id"] == "gptsovits-default"
    assert calls["started"] == ["gptsovits-default"]
    assert calls["synthesized"] == [("gptsovits-default", "你好")]
