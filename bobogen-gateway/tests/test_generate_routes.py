from fastapi.testclient import TestClient


def test_models_endpoint_lists_tts_models_from_existing_providers():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models")

    assert response.status_code == 200
    models = response.json()["models"]
    f5 = next(model for model in models if model["id"] == "local_f5_tts")
    assert f5["provider_id"] == "local_f5_tts"
    assert f5["tasks"] == ["tts.speech"]
    assert "audio/wav" in f5["outputs"]
    assert f5["enabled"] is True

    stable_audio = next(model for model in models if model["id"] == "stable-audio-3-small-sfx")
    assert stable_audio["provider_id"] == "stable_audio_3_small_sfx"
    assert stable_audio["tasks"] == ["audio.generate"]
    assert "audio/wav" in stable_audio["outputs"]


def test_model_detail_includes_voices_and_generation_capabilities():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/local_f5_tts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "local_f5_tts"
    assert payload["tasks"] == ["tts.speech"]
    assert payload["voices"][0]["voice_id"] == "f5-default"
    assert payload["capabilities"]["reference_audio"] is True


def test_stable_audio3_model_detail_describes_audio_generation():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/stable-audio-3-small-sfx")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "stable-audio-3-small-sfx"
    assert payload["provider_id"] == "stable_audio_3_small_sfx"
    assert payload["tasks"] == ["audio.generate"]
    assert payload["voices"] == []


def test_generate_tts_speech_json_calls_adapter_generate():
    from app.main import create_app
    from app.services.audio_service import AudioResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    calls = {"started": [], "generated": []}

    async def fake_ensure_started(provider_id):
        calls["started"].append(provider_id)
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            calls["generated"].append((provider.provider_id, request.task, request.input["text"]))
            return AudioResult(
                content=b"RIFF",
                content_type="audio/wav",
                duration_seconds=2.5,
                sample_rate=24000,
                format="wav",
            )

    manager.ensure_started = fake_ensure_started
    registry._adapters["local_f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "local_f5_tts",
            "task": "tts.speech",
            "input": {"text": "你好", "voice": "f5-default", "language": "zh"},
            "parameters": {"reference_audio": {"kind": "path", "path": "E:/AiModel/tts/ref.wav"}},
            "output": {"format": "wav", "sample_rate": 24000},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-provider-id"] == "local_f5_tts"
    assert response.headers["x-model-id"] == "local_f5_tts"
    assert response.headers["x-task"] == "tts.speech"
    assert calls["started"] == ["local_f5_tts"]
    assert calls["generated"] == [("local_f5_tts", "tts.speech", "你好")]


def test_generate_multipart_upload_resolves_file_inputs_to_temp_paths():
    from pathlib import Path

    from app.main import create_app
    from app.services.audio_service import AudioResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    seen = {}

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            path = request.parameters["reference_audio"]
            seen["path"] = path
            seen["exists_during_generate"] = Path(path).exists()
            seen["content"] = Path(path).read_bytes()
            return AudioResult(content=b"RIFF", content_type="audio/wav")

    manager.ensure_started = fake_ensure_started
    registry._adapters["local_f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        data={
            "request": """{
                "model": "local_f5_tts",
                "task": "tts.speech",
                "input": {"text": "你好", "voice": "f5-default"},
                "parameters": {"reference_audio": {"kind": "upload", "field": "ref_audio"}},
                "output": {"format": "wav"}
            }"""
        },
        files={"ref_audio": ("speaker.wav", b"RIFFspeaker", "audio/wav")},
    )

    assert response.status_code == 200
    assert seen["exists_during_generate"] is True
    assert seen["content"] == b"RIFFspeaker"
    assert not Path(seen["path"]).exists()


def test_generate_json_data_uri_resolves_file_inputs_to_temp_paths():
    from pathlib import Path

    from app.main import create_app
    from app.services.audio_service import AudioResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    seen = {}

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            path = request.parameters["reference_audio"]
            seen["path"] = path
            seen["exists_during_generate"] = Path(path).exists()
            seen["content"] = Path(path).read_bytes()
            return AudioResult(content=b"RIFF", content_type="audio/wav")

    manager.ensure_started = fake_ensure_started
    registry._adapters["local_f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "local_f5_tts",
            "task": "tts.speech",
            "input": {"text": "你好", "voice": "f5-default"},
            "parameters": {"reference_audio": {"kind": "data_uri", "data": "data:audio/wav;base64,UklGRg=="}},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    assert seen["exists_during_generate"] is True
    assert seen["content"] == b"RIFF"
    assert not Path(seen["path"]).exists()


def test_generate_logs_sanitized_request_without_data_uri(caplog):
    import logging

    from app.main import create_app
    from app.services.audio_service import AudioResult

    caplog.set_level(logging.INFO, logger="bobogen_gateway.generate")

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            return AudioResult(content=b"RIFF", content_type="audio/wav")

    manager.ensure_started = fake_ensure_started
    registry._adapters["local_f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "local_f5_tts",
            "task": "tts.speech",
            "input": {"text": "你好", "voice": "f5-default"},
            "parameters": {"reference_audio": {"kind": "data_uri", "data": "data:audio/wav;base64,UklGRg=="}},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "local_f5_tts" in messages
    assert "tts.speech" in messages
    assert "data_uri" in messages
    assert "UklGRg==" not in messages


def test_generate_unknown_model_returns_stable_error_payload():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/generate",
        json={
            "model": "missing-model",
            "task": "tts.speech",
            "input": {"text": "你好", "voice": "default"},
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_generate_external_provider_not_started_returns_503_with_start_hint():
    from app.core.exceptions import ProviderExternalStartRequiredError
    from app.main import create_app

    app = create_app()
    manager = app.state.process_manager

    async def fake_ensure_started(provider_id):
        raise ProviderExternalStartRequiredError(
            "Provider stable_audio_3_small_sfx is external. Start it with: bash start.sh --docker --model stable-audio3",
            {"provider_id": provider_id, "compose_service": "stable-audio3"},
        )

    manager.ensure_started = fake_ensure_started

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "stable-audio-3-small-sfx",
            "task": "audio.generate",
            "input": {"prompt": "short cinematic whoosh impact"},
            "parameters": {"duration": 1},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_EXTERNAL_START_REQUIRED"
    assert "bash start.sh --docker --model stable-audio3" in response.json()["error"]["message"]


def test_generate_unsupported_task_returns_stable_error_payload():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/generate",
        json={
            "model": "local_f5_tts",
            "task": "audio.generate",
            "input": {"prompt": "cinematic hit"},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_TASK"


def test_legacy_synthesize_endpoint_remains_available():
    from app.main import create_app
    from app.services.audio_service import AudioResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def synthesize(self, provider, request, files=None):
            return AudioResult(content=b"RIFF", content_type="audio/wav")

    manager.ensure_started = fake_ensure_started
    registry._adapters["local_f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/local_f5_tts/v1/synthesize",
        json={"text": "你好", "voice_id": "f5-default", "parameters": {}, "output": {"format": "wav"}},
    )

    assert response.status_code == 200
