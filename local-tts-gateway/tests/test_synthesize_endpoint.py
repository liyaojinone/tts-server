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
    registry._adapters["local_f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/local_f5_tts/v1/synthesize",
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
    assert response.headers["x-provider-id"] == "local_f5_tts"
    assert calls["started"] == ["local_f5_tts"]
    assert calls["synthesized"] == [("local_f5_tts", "你好")]
