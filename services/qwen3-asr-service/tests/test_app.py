from fastapi.testclient import TestClient


def test_qwen3_asr_service_health_and_test_mode_transcription(monkeypatch):
    monkeypatch.setenv("QWEN3_ASR_MODEL_ID", "qwen3_asr_0_6b")
    monkeypatch.setenv("QWEN3_ASR_HF_REPO_ID", "Qwen/Qwen3-ASR-0.6B")

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["model"] == "qwen3_asr_0_6b"
    assert health.json()["hfRepoId"] == "Qwen/Qwen3-ASR-0.6B"
    assert health.json()["device"] == "cuda:0"
    assert health.json()["gpuRequired"] is True

    response = client.post(
        "/v1/transcribe",
        json={
            "model": "qwen3_asr_0_6b",
            "task": "asr.transcribe",
            "input": {"audio": "E:/audio/demo.wav", "language": "auto"},
            "parameters": {"mode": "offline", "timestamps": False},
            "output": {"format": "json"},
        },
    )

    assert response.status_code == 200
    assert response.json()["text"] == "test transcription"
    assert response.json()["language"] == "auto"
    assert response.json()["model"] == "qwen3_asr_0_6b"
    assert response.json()["segments"] == []


def test_qwen3_asr_service_can_run_1_7b_from_env(monkeypatch):
    monkeypatch.setenv("QWEN3_ASR_MODEL_ID", "qwen3_asr_1_7b")
    monkeypatch.setenv("QWEN3_ASR_HF_REPO_ID", "Qwen/Qwen3-ASR-1.7B")
    monkeypatch.setenv("QWEN3_ASR_PORT", "5111")

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["model"] == "qwen3_asr_1_7b"
    assert health.json()["hfRepoId"] == "Qwen/Qwen3-ASR-1.7B"


def test_qwen3_forced_aligner_service_health_and_test_mode_alignment(monkeypatch):
    monkeypatch.setenv("QWEN3_ASR_MODEL_ID", "qwen3_forced_aligner_0_6b")
    monkeypatch.setenv("QWEN3_ASR_HF_REPO_ID", "Qwen/Qwen3-ForcedAligner-0.6B")
    monkeypatch.setenv("QWEN3_ASR_PORT", "5112")

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["model"] == "qwen3_forced_aligner_0_6b"
    assert health.json()["hfRepoId"] == "Qwen/Qwen3-ForcedAligner-0.6B"

    response = client.post(
        "/v1/align",
        json={
            "model": "qwen3_forced_aligner_0_6b",
            "task": "audio.align",
            "input": {
                "audio": "E:/audio/line.wav",
                "text": "你终于来了。",
                "language": "Chinese",
                "clip_start": 120.0,
            },
            "parameters": {"granularity": "word"},
            "output": {"format": "json"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "你终于来了。"
    assert payload["language"] == "Chinese"
    assert payload["clip_start"] == 120.0
    assert payload["model"] == "qwen3_forced_aligner_0_6b"
    assert payload["segments"][0] == {
        "index": 0,
        "text": "你终于来了。",
        "start": 0.0,
        "end": 1.0,
        "global_start": 120.0,
        "global_end": 121.0,
    }


def test_qwen3_forced_aligner_normalizes_forced_align_result_items():
    from app.handler import Qwen3ASRHandler

    class ForcedAlignResultLike:
        def __iter__(self):
            return iter(
                [
                    {"text": "你", "start_time": 0.12, "end_time": 0.26},
                    {"text": "好", "start_time": 0.28, "end_time": 0.46},
                ]
            )

    handler = Qwen3ASRHandler(test_mode=True)
    payload = handler._normalize_alignment_result(
        [ForcedAlignResultLike()],
        text="你好",
        language="Chinese",
        clip_start=120.0,
    )

    assert payload["segments"] == [
        {
            "index": 0,
            "text": "你",
            "start": 0.12,
            "end": 0.26,
            "global_start": 120.12,
            "global_end": 120.26,
        },
        {
            "index": 1,
            "text": "好",
            "start": 0.28,
            "end": 0.46,
            "global_start": 120.28,
            "global_end": 120.46,
        },
    ]


def test_qwen3_asr_service_rejects_unsupported_task():
    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    response = client.post(
        "/v1/transcribe",
        json={
            "model": "qwen3_asr_0_6b",
            "task": "audio.generate",
            "input": {"prompt": "ignored"},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_TASK"


def test_qwen3_asr_non_test_mode_requires_cuda(monkeypatch):
    import types

    from app.handler import Qwen3ASRHandler

    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        bfloat16="bfloat16",
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)

    handler = Qwen3ASRHandler(test_mode=False)

    try:
        handler._load_model()
    except RuntimeError as exc:
        assert "CUDA GPU is required" in str(exc)
    else:
        raise AssertionError("expected CPU-only environment to be rejected")
