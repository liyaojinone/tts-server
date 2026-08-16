from fastapi.testclient import TestClient


def test_models_endpoint_lists_tts_models_from_existing_providers():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models")

    assert response.status_code == 200
    models = response.json()["models"]
    f5 = next(model for model in models if model["id"] == "f5_tts")
    assert f5["provider_id"] == "f5_tts"
    assert f5["tasks"] == ["tts.speech"]
    assert "audio/wav" in f5["outputs"]
    assert f5["enabled"] is True

    stable_audio = next(model for model in models if model["id"] == "stable_audio_3_small_sfx")
    assert stable_audio["provider_id"] == "stable_audio_3_small_sfx"
    assert stable_audio["tasks"] == ["audio.generate"]
    assert "audio/wav" in stable_audio["outputs"]

    stable_audio_music = next(model for model in models if model["id"] == "stable_audio_3_small_music")
    assert stable_audio_music["provider_id"] == "stable_audio_3_small_music"
    assert stable_audio_music["tasks"] == ["audio.generate"]
    assert "audio/wav" in stable_audio_music["outputs"]


def test_model_detail_includes_voices_and_generation_capabilities():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/f5_tts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "f5_tts"
    assert payload["tasks"] == ["tts.speech"]
    assert payload["voices"][0]["voice_id"] == "f5-default"
    assert payload["capabilities"]["reference_audio"] is True


def test_stable_audio3_model_detail_describes_audio_generation():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/stable_audio_3_small_sfx")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "stable_audio_3_small_sfx"
    assert payload["provider_id"] == "stable_audio_3_small_sfx"
    assert payload["tasks"] == ["audio.generate"]
    assert payload["voices"] == []
    assert payload["input_schema"]["properties"]["prompt"]["type"] == "string"
    assert "prompt" in payload["input_schema"]["required"]
    assert "duration" in payload["parameters_schema"]["properties"]
    assert payload["parameters_schema"]["properties"]["batch_size"]["default"] == 1
    assert payload["examples"][0]["request"]["model"] == "stable_audio_3_small_sfx"
    assert payload["examples"][0]["request"]["parameters"]["cfg_scale"] == 1.0


def test_stable_audio3_medium_model_detail_reuses_audio_generation_schema():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/stable_audio_3_medium")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "stable_audio_3_medium"
    assert payload["provider_id"] == "stable_audio_3_medium"
    assert payload["tasks"] == ["audio.generate"]
    assert payload["input_schema"]["properties"]["prompt"]["type"] == "string"
    assert "duration" in payload["parameters_schema"]["properties"]
    assert payload["examples"][0]["request"]["model"] == "stable_audio_3_medium"


def test_stable_audio3_small_music_model_detail_reuses_audio_generation_schema():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/stable_audio_3_small_music")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "stable_audio_3_small_music"
    assert payload["provider_id"] == "stable_audio_3_small_music"
    assert payload["tasks"] == ["audio.generate"]
    assert payload["input_schema"]["properties"]["prompt"]["type"] == "string"
    assert "duration" in payload["parameters_schema"]["properties"]
    assert payload["examples"][0]["request"]["model"] == "stable_audio_3_small_music"


def test_qwen3_asr_model_detail_describes_transcription_schema():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/qwen3_asr_0_6b")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "qwen3_asr_0_6b"
    assert payload["provider_id"] == "qwen3_asr_0_6b"
    assert payload["tasks"] == ["asr.transcribe"]
    assert payload["outputs"] == ["application/json"]
    assert "audio" in payload["input_schema"]["properties"]
    assert "audio" in payload["input_schema"]["required"]
    assert payload["input_schema"]["properties"]["language"]["default"] == "auto"
    assert payload["parameters_schema"]["properties"]["timestamps"]["default"] is False
    assert payload["parameters_schema"]["properties"]["batch_size"]["default"] == 2
    audio_schema = payload["input_schema"]["properties"]["audio"]
    assert any(option.get("type") == "array" for option in audio_schema["anyOf"])
    assert payload["output_schema"]["properties"]["format"]["default"] == "json"
    assert payload["examples"][0]["request"]["model"] == "qwen3_asr_0_6b"
    assert payload["examples"][0]["request"]["task"] == "asr.transcribe"
    assert payload["examples"][0]["request"]["parameters"]["batch_size"] == 2


def test_qwen3_forced_aligner_model_detail_describes_alignment_schema():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/qwen3_forced_aligner_0_6b")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "qwen3_forced_aligner_0_6b"
    assert payload["provider_id"] == "qwen3_forced_aligner_0_6b"
    assert payload["tasks"] == ["audio.align"]
    assert payload["outputs"] == ["application/json"]
    assert set(payload["input_schema"]["required"]) == {"audio", "text", "language"}
    assert "clip_start" in payload["input_schema"]["properties"]
    assert payload["parameters_schema"]["properties"]["granularity"]["default"] == "word"
    assert payload["output_schema"]["properties"]["format"]["default"] == "json"
    assert payload["examples"][0]["request"]["model"] == "qwen3_forced_aligner_0_6b"
    assert payload["examples"][0]["request"]["task"] == "audio.align"


def test_campplus_speaker_diarization_model_detail_describes_diarization_schema():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/campplus_speaker_diarization")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "campplus_speaker_diarization"
    assert payload["provider_id"] == "campplus_speaker_diarization"
    assert payload["tasks"] == ["audio.diarize"]
    assert payload["outputs"] == ["application/json"]
    assert payload["input_schema"]["required"] == ["audio"]
    assert "clip_start" in payload["input_schema"]["properties"]
    assert payload["parameters_schema"]["properties"]["oracle_num"]["default"] is None
    assert payload["parameters_schema"]["properties"]["min_duration"]["default"] == 0.0
    assert payload["output_schema"]["properties"]["format"]["default"] == "json"
    assert payload["examples"][0]["request"]["model"] == "campplus_speaker_diarization"
    assert payload["examples"][0]["request"]["task"] == "audio.diarize"


def test_tts_model_detail_describes_dynamic_parameters():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/models/f5_tts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["input_schema"]["properties"]["text"]["type"] == "string"
    assert "text" in payload["input_schema"]["required"]
    assert "reference_audio" in payload["parameters_schema"]["properties"]
    assert "speed" in payload["parameters_schema"]["properties"]
    assert payload["examples"][0]["request"]["task"] == "tts.speech"
    assert payload["examples"][0]["request"]["parameters"]["reference_audio"]["kind"] == "path"


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
    registry._adapters["f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "f5_tts",
            "task": "tts.speech",
            "input": {"text": "你好", "voice": "f5-default", "language": "zh"},
            "parameters": {"reference_audio": {"kind": "path", "path": "E:/AiModel/tts/ref.wav"}},
            "output": {"format": "wav", "sample_rate": 24000},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["x-provider-id"] == "f5_tts"
    assert response.headers["x-model-id"] == "f5_tts"
    assert response.headers["x-task"] == "tts.speech"
    assert calls["started"] == ["f5_tts"]
    assert calls["generated"] == [("f5_tts", "tts.speech", "你好")]


def test_generate_can_return_json_result_from_adapter():
    from app.main import create_app
    from app.services.generate_result import JsonResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            return JsonResult(
                payload={
                    "text": "你好，世界。",
                    "language": "zh",
                    "duration_seconds": 1.25,
                    "segments": [],
                }
            )

    manager.ensure_started = fake_ensure_started
    registry._adapters["f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "f5_tts",
            "task": "tts.speech",
            "input": {"text": "ignored", "voice": "f5-default", "language": "zh"},
            "parameters": {},
            "output": {"format": "json"},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-provider-id"] == "f5_tts"
    assert response.json()["text"] == "你好，世界。"


def test_generate_stable_audio3_validates_registered_parameters_and_calls_adapter_generate():
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
            calls["generated"].append(
                (
                    provider.provider_id,
                    request.input["prompt"],
                    request.parameters["duration"],
                    request.parameters["batch_size"],
                )
            )
            return AudioResult(
                content=b"RIFF",
                content_type="audio/wav",
                duration_seconds=request.parameters["duration"],
                sample_rate=44100,
                format="wav",
            )

    manager.ensure_started = fake_ensure_started
    registry._adapters["stable_audio_3_small_sfx"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "stable_audio_3_small_sfx",
            "task": "audio.generate",
            "input": {"prompt": "short cinematic whoosh impact"},
            "parameters": {
                "duration": 5,
                "steps": 8,
                "cfg_scale": 1.0,
                "seed": 1234,
                "batch_size": 1,
                "truncate_output_to_duration": True,
            },
            "output": {"format": "wav", "sample_rate": 44100},
        },
    )

    assert response.status_code == 200
    assert response.headers["x-provider-id"] == "stable_audio_3_small_sfx"
    assert calls["started"] == ["stable_audio_3_small_sfx"]
    assert calls["generated"] == [("stable_audio_3_small_sfx", "short cinematic whoosh impact", 5, 1)]


def test_generate_stable_audio3_missing_prompt_returns_invalid_request():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/v1/generate",
        json={
            "model": "stable_audio_3_small_sfx",
            "task": "audio.generate",
            "input": {},
            "parameters": {"duration": 5},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_REQUEST"
    assert "input.prompt" in payload["error"]["message"]


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
    registry._adapters["f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        data={
            "request": """{
                "model": "f5_tts",
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


def test_generate_asr_multipart_upload_resolves_input_audio_to_temp_path():
    from pathlib import Path

    from app.main import create_app
    from app.services.generate_result import JsonResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    seen = {}

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            path = request.input["audio"]
            seen["provider_id"] = provider.provider_id
            seen["path"] = path
            seen["exists_during_generate"] = Path(path).exists()
            seen["content"] = Path(path).read_bytes()
            return JsonResult(payload={"text": "hello", "language": "en", "segments": []})

    manager.ensure_started = fake_ensure_started
    registry._adapters["qwen3_asr_0_6b"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        data={
            "request": """{
                "model": "qwen3_asr_0_6b",
                "task": "asr.transcribe",
                "input": {"audio": {"kind": "upload", "field": "audio"}, "language": "auto"},
                "parameters": {"mode": "offline", "timestamps": false},
                "output": {"format": "json"}
            }"""
        },
        files={"audio": ("speech.wav", b"RIFFspeech", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-provider-id"] == "qwen3_asr_0_6b"
    assert response.json()["text"] == "hello"
    assert seen["provider_id"] == "qwen3_asr_0_6b"
    assert seen["exists_during_generate"] is True
    assert seen["content"] == b"RIFFspeech"
    assert not Path(seen["path"]).exists()


def test_generate_audio_align_multipart_upload_resolves_input_audio_to_temp_path():
    from pathlib import Path

    from app.main import create_app
    from app.services.generate_result import JsonResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    seen = {}

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            path = request.input["audio"]
            seen["provider_id"] = provider.provider_id
            seen["task"] = request.task
            seen["path"] = path
            seen["exists_during_generate"] = Path(path).exists()
            seen["content"] = Path(path).read_bytes()
            return JsonResult(
                payload={
                    "text": request.input["text"],
                    "language": request.input["language"],
                    "clip_start": request.input["clip_start"],
                    "segments": [
                        {
                            "text": "你",
                            "start": 0.1,
                            "end": 0.22,
                            "global_start": 120.1,
                            "global_end": 120.22,
                        }
                    ],
                    "model": request.model,
                }
            )

    manager.ensure_started = fake_ensure_started
    registry._adapters["qwen3_forced_aligner_0_6b"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        data={
            "request": """{
                "model": "qwen3_forced_aligner_0_6b",
                "task": "audio.align",
                "input": {
                    "audio": {"kind": "upload", "field": "audio"},
                    "text": "你终于来了。",
                    "language": "Chinese",
                    "clip_start": 120.0
                },
                "parameters": {"granularity": "word"},
                "output": {"format": "json"}
            }"""
        },
        files={"audio": ("line.wav", b"RIFFline", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-provider-id"] == "qwen3_forced_aligner_0_6b"
    assert response.json()["segments"][0]["global_start"] == 120.1
    assert seen["provider_id"] == "qwen3_forced_aligner_0_6b"
    assert seen["task"] == "audio.align"
    assert seen["exists_during_generate"] is True
    assert seen["content"] == b"RIFFline"
    assert not Path(seen["path"]).exists()


def test_generate_audio_diarize_multipart_upload_resolves_input_audio_to_temp_path():
    from pathlib import Path

    from app.main import create_app
    from app.services.generate_result import JsonResult

    app = create_app()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    seen = {}

    async def fake_ensure_started(provider_id):
        return manager.get_state(provider_id)

    class StubAdapter:
        provider_type = "stub"

        async def generate(self, provider, request):
            path = request.input["audio"]
            seen["provider_id"] = provider.provider_id
            seen["task"] = request.task
            seen["path"] = path
            seen["exists_during_generate"] = Path(path).exists()
            seen["content"] = Path(path).read_bytes()
            return JsonResult(
                payload={
                    "model": request.model,
                    "clip_start": request.input["clip_start"],
                    "segments": [
                        {
                            "speaker": "SPEAKER_00",
                            "start": 0.1,
                            "end": 1.2,
                            "global_start": 10.1,
                            "global_end": 11.2,
                        }
                    ],
                }
            )

    manager.ensure_started = fake_ensure_started
    registry._adapters["campplus_speaker_diarization"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        data={
            "request": """{
                "model": "campplus_speaker_diarization",
                "task": "audio.diarize",
                "input": {
                    "audio": {"kind": "upload", "field": "audio"},
                    "clip_start": 10.0
                },
                "parameters": {"oracle_num": 2, "min_duration": 0.0},
                "output": {"format": "json"}
            }"""
        },
        files={"audio": ("dialogue.wav", b"RIFFdialogue", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-provider-id"] == "campplus_speaker_diarization"
    assert response.json()["segments"][0]["speaker"] == "SPEAKER_00"
    assert seen["provider_id"] == "campplus_speaker_diarization"
    assert seen["task"] == "audio.diarize"
    assert seen["exists_during_generate"] is True
    assert seen["content"] == b"RIFFdialogue"
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
    registry._adapters["f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "f5_tts",
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
    registry._adapters["f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/v1/generate",
        json={
            "model": "f5_tts",
            "task": "tts.speech",
            "input": {"text": "你好", "voice": "f5-default"},
            "parameters": {"reference_audio": {"kind": "data_uri", "data": "data:audio/wav;base64,UklGRg=="}},
            "output": {"format": "wav"},
        },
    )

    assert response.status_code == 200
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "f5_tts" in messages
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
            "model": "stable_audio_3_small_sfx",
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
            "model": "f5_tts",
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
    registry._adapters["f5_tts"] = StubAdapter()

    client = TestClient(app)
    response = client.post(
        "/f5_tts/v1/synthesize",
        json={"text": "你好", "voice_id": "f5-default", "parameters": {}, "output": {"format": "wav"}},
    )

    assert response.status_code == 200
