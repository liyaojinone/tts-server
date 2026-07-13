from fastapi.testclient import TestClient


def test_speaker_diarization_service_health_and_test_mode_diarize(monkeypatch):
    monkeypatch.setenv("SPEAKER_DIARIZATION_MODEL_ID", "campplus_speaker_diarization")
    monkeypatch.setenv("SPEAKER_DIARIZATION_MODEL_NAME", "iic/speech_campplus_speaker-diarization_common")
    monkeypatch.setenv("SPEAKER_DIARIZATION_MODEL_REVISION", "master")

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["model"] == "campplus_speaker_diarization"
    assert health.json()["modelName"] == "iic/speech_campplus_speaker-diarization_common"
    assert health.json()["modelRevision"] == "master"
    assert health.json()["device"] == "cuda:0"

    response = client.post(
        "/v1/diarize",
        json={
            "model": "campplus_speaker_diarization",
            "task": "audio.diarize",
            "input": {"audio": "E:/audio/dialogue.wav", "clip_start": 10.0},
            "parameters": {"oracle_num": 2, "min_duration": 0.0},
            "output": {"format": "json"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "campplus_speaker_diarization"
    assert payload["clip_start"] == 10.0
    assert payload["segments"] == [
        {
            "index": 0,
            "speaker": "SPEAKER_00",
            "start": 0.0,
            "end": 1.0,
            "global_start": 10.0,
            "global_end": 11.0,
        }
    ]


def test_speaker_diarization_service_rejects_unsupported_task():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/diarize",
        json={
            "model": "campplus_speaker_diarization",
            "task": "asr.transcribe",
            "input": {"audio": "E:/audio/dialogue.wav"},
            "output": {"format": "json"},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_TASK"


def test_speaker_diarization_normalizes_modelscope_text_output(monkeypatch):
    from app.handler import SpeakerDiarizationHandler
    from bobogen_protocol.models import GenerateRequest

    handler = SpeakerDiarizationHandler(test_mode=False)

    class StubPipeline:
        def __call__(self, audio, **kwargs):
            return {
                "text": "SPEAKER dialogue 1 0.50 1.25 <NA> <NA> SPEAKER_00 <NA> <NA>\n"
                "SPEAKER dialogue 1 2.00 0.75 <NA> <NA> SPEAKER_01 <NA> <NA>"
            }

    monkeypatch.setattr(handler, "_load_pipeline", lambda: StubPipeline())

    result = handler.diarize(
        GenerateRequest(
            model="campplus_speaker_diarization",
            task="audio.diarize",
            input={"audio": "E:/audio/dialogue.wav", "clip_start": 20.0},
            parameters={"oracle_num": 2, "min_duration": 0.8},
            output={"format": "json"},
        )
    )

    assert result["segments"] == [
        {
            "index": 0,
            "speaker": "SPEAKER_00",
            "start": 0.5,
            "end": 1.75,
            "global_start": 20.5,
            "global_end": 21.75,
        }
    ]


def test_speaker_diarization_normalizes_modelscope_triplet_output(monkeypatch):
    from app.handler import SpeakerDiarizationHandler
    from bobogen_protocol.models import GenerateRequest

    handler = SpeakerDiarizationHandler(test_mode=False)

    class StubPipeline:
        def __call__(self, audio, **kwargs):
            return {"text": [[0.08, 24.28, 0], [24.28, 34.68, 1]]}

    monkeypatch.setattr(handler, "_load_pipeline", lambda: StubPipeline())

    result = handler.diarize(
        GenerateRequest(
            model="campplus_speaker_diarization",
            task="audio.diarize",
            input={"audio": "E:/audio/dialogue.wav", "clip_start": 100.0},
            parameters={"oracle_num": 2, "min_duration": 0.0},
            output={"format": "json"},
        )
    )

    assert result["segments"] == [
        {
            "index": 0,
            "speaker": "SPEAKER_00",
            "start": 0.08,
            "end": 24.28,
            "global_start": 100.08,
            "global_end": 124.28,
        },
        {
            "index": 1,
            "speaker": "SPEAKER_01",
            "start": 24.28,
            "end": 34.68,
            "global_start": 124.28,
            "global_end": 134.68,
        },
    ]
