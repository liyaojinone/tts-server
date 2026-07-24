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


def test_qwen3_asr_service_applies_request_batch_size_to_audio_array():
    from types import SimpleNamespace

    from app.handler import Qwen3ASRHandler
    from bobogen_protocol.models import GenerateRequest

    class FakeModel:
        max_inference_batch_size = 7

        def transcribe(self, *, audio, language, return_time_stamps):
            assert audio == ["E:/audio/part-1.wav", "E:/audio/part-2.wav"]
            assert language == "Chinese"
            assert return_time_stamps is False
            assert self.max_inference_batch_size == 2
            return [
                SimpleNamespace(text="第一段。", language="Chinese", time_stamps=[]),
                SimpleNamespace(text="第二段。", language="Chinese", time_stamps=[]),
            ]

    model = FakeModel()
    handler = Qwen3ASRHandler(test_mode=False)
    handler._load_model = lambda: model
    request = GenerateRequest.model_validate(
        {
            "model": "qwen3_asr_0_6b",
            "task": "asr.transcribe",
            "input": {
                "audio": ["E:/audio/part-1.wav", "E:/audio/part-2.wav"],
                "language": "Chinese",
            },
            "parameters": {"batch_size": 2, "timestamps": False},
            "output": {"format": "json"},
        }
    )

    payload = handler.transcribe(request)

    assert model.max_inference_batch_size == 7
    assert payload["text"] == "第一段。第二段。"
    assert [item["text"] for item in payload["items"]] == ["第一段。", "第二段。"]
    assert [item["index"] for item in payload["items"]] == [0, 1]


def test_qwen3_forced_aligner_service_health_and_test_mode_alignment(monkeypatch):
    monkeypatch.setenv("QWEN3_ASR_MODEL_ID", "qwen3_forced_aligner_0_6b")
    monkeypatch.setenv("QWEN3_ASR_HF_REPO_ID", "Qwen/Qwen3-ForcedAligner-0.6B-hf")
    monkeypatch.setenv("QWEN3_ASR_PORT", "5112")

    from app.main import create_app

    app = create_app(test_mode=True)
    client = TestClient(app)

    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["model"] == "qwen3_forced_aligner_0_6b"
    assert health.json()["hfRepoId"] == "Qwen/Qwen3-ForcedAligner-0.6B-hf"

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


def test_qwen3_forced_aligner_uses_native_processor_and_token_classifier():
    from types import SimpleNamespace

    from app.handler import Qwen3ASRHandler
    from bobogen_protocol.models import GenerateRequest

    class FakeBatch(dict):
        def to(self, device, dtype):
            assert device == "cuda:0"
            assert dtype == "bfloat16"
            return self

    class FakeProcessor:
        def prepare_forced_aligner_inputs(self, *, audio, transcript, language):
            assert audio == "E:/audio/line.wav"
            assert transcript == "你好"
            assert language == "Chinese"
            return FakeBatch(input_ids="input-ids"), [["你", "好"]]

        def decode_forced_alignment(
            self,
            *,
            logits,
            input_ids,
            word_lists,
            timestamp_token_id,
            timestamp_segment_time,
        ):
            assert logits == "token-classification-logits"
            assert input_ids == "input-ids"
            assert word_lists == [["你", "好"]]
            assert timestamp_token_id == 151705
            assert timestamp_segment_time == 80
            return [
                [
                    {"text": "你", "start_time": 0.1, "end_time": 0.3},
                    {"text": "好", "start_time": 0.3, "end_time": 0.6},
                ]
            ]

    class FakeModel:
        device = "cuda:0"
        dtype = "bfloat16"
        config = SimpleNamespace(timestamp_token_id=151705, timestamp_segment_time=80)

        def __call__(self, **inputs):
            assert inputs == {"input_ids": "input-ids"}
            return SimpleNamespace(logits="token-classification-logits")

    handler = Qwen3ASRHandler(test_mode=False)
    handler._aligner = (FakeModel(), FakeProcessor())
    request = GenerateRequest.model_validate(
        {
            "model": "qwen3_asr_0_6b",
            "task": "audio.align",
            "input": {
                "audio": "E:/audio/line.wav",
                "text": "你好",
                "language": "Chinese",
                "clip_start": 12.0,
            },
            "parameters": {"granularity": "word"},
            "output": {"format": "json"},
        }
    )

    payload = handler.align(request)

    assert payload["segments"] == [
        {
            "index": 0,
            "text": "你",
            "start": 0.1,
            "end": 0.3,
            "global_start": 12.1,
            "global_end": 12.3,
        },
        {
            "index": 1,
            "text": "好",
            "start": 0.3,
            "end": 0.6,
            "global_start": 12.3,
            "global_end": 12.6,
        },
    ]


def test_qwen3_forced_aligner_passes_no_language_hint_when_request_is_auto():
    from types import SimpleNamespace

    from app.handler import Qwen3ASRHandler
    from bobogen_protocol.models import GenerateRequest

    captured = {}

    class FakeBatch(dict):
        def to(self, _device, _dtype):
            return self

    class FakeProcessor:
        def prepare_forced_aligner_inputs(self, *, audio, transcript, language):
            captured["language"] = language
            return FakeBatch(input_ids="input-ids"), [["你"]]

        def decode_forced_alignment(self, **_kwargs):
            return [[{"text": "你", "start_time": 0.0, "end_time": 0.1}]]

    class FakeModel:
        device = "cuda:0"
        dtype = "bfloat16"
        config = SimpleNamespace(timestamp_token_id=151705, timestamp_segment_time=80)

        def __call__(self, **_inputs):
            return SimpleNamespace(logits="token-classification-logits")

    handler = Qwen3ASRHandler(test_mode=False)
    handler._aligner = (FakeModel(), FakeProcessor())
    request = GenerateRequest.model_validate(
        {
            "model": "qwen3_asr_0_6b",
            "task": "audio.align",
            "input": {
                "audio": "E:/audio/line.wav",
                "text": "你",
                "language": "auto",
            },
            "parameters": {"granularity": "word"},
            "output": {"format": "json"},
        }
    )

    handler.align(request)

    assert captured["language"] is None


def test_qwen3_forced_aligner_loads_native_hf_backend_without_legacy_fallback(monkeypatch):
    import sys
    import types

    from app.handler import Qwen3ASRHandler

    loaded = {}
    fake_processor = object()
    fake_model = object()

    class FakeAutoProcessor:
        @staticmethod
        def from_pretrained(model_path):
            loaded["processor"] = model_path
            return fake_processor

    class FakeAutoModelForTokenClassification:
        @staticmethod
        def from_pretrained(model_path, *, dtype, device_map):
            loaded["model"] = (model_path, dtype, device_map)
            return fake_model

    class LegacyAligner:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            raise AssertionError("legacy Qwen3ForcedAligner must not be used")

    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: True),
        bfloat16="bfloat16",
    )
    fake_transformers = types.SimpleNamespace(
        AutoProcessor=FakeAutoProcessor,
        AutoModelForTokenClassification=FakeAutoModelForTokenClassification,
    )
    fake_qwen_asr = types.SimpleNamespace(Qwen3ForcedAligner=LegacyAligner)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "qwen_asr", fake_qwen_asr)

    handler = Qwen3ASRHandler(test_mode=False)
    aligner = handler._load_aligner()

    assert aligner == (fake_model, fake_processor)
    assert loaded == {
        "processor": handler.hf_repo_id,
        "model": (handler.hf_repo_id, "bfloat16", handler.device),
    }


def test_qwen3_forced_aligner_health_is_ready_after_native_model_load(monkeypatch):
    from app.handler import Qwen3ASRHandler

    monkeypatch.setenv("QWEN3_ASR_MODEL_ID", "qwen3_forced_aligner_0_6b")
    handler = Qwen3ASRHandler(test_mode=False)
    handler._aligner = (object(), object())

    assert handler.health()["ready"] is True


def test_qwen3_forced_aligner_serializes_gpu_inference():
    import threading
    import time
    from types import SimpleNamespace

    from app.handler import Qwen3ASRHandler
    from bobogen_protocol.models import GenerateRequest

    active_calls = 0
    max_active_calls = 0
    counter_lock = threading.Lock()

    class FakeBatch(dict):
        def to(self, _device, _dtype):
            return self

    class FakeProcessor:
        def prepare_forced_aligner_inputs(self, **_kwargs):
            return FakeBatch(input_ids="input-ids"), [[]]

        def decode_forced_alignment(self, **_kwargs):
            return [[]]

    class FakeModel:
        device = "cuda:0"
        dtype = "bfloat16"
        config = SimpleNamespace(timestamp_token_id=151705, timestamp_segment_time=80)

        def __call__(self, **_inputs):
            nonlocal active_calls, max_active_calls
            with counter_lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            time.sleep(0.05)
            with counter_lock:
                active_calls -= 1
            return SimpleNamespace(logits="logits")

    handler = Qwen3ASRHandler(test_mode=False)
    handler._aligner = (FakeModel(), FakeProcessor())
    request = GenerateRequest.model_validate(
        {
            "model": "qwen3_asr_0_6b",
            "task": "audio.align",
            "input": {"audio": "line.wav", "text": "你好", "language": "Chinese"},
            "output": {"format": "json"},
        }
    )
    threads = [threading.Thread(target=handler.align, args=(request,)) for _ in range(2)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active_calls == 1


def test_qwen3_forced_aligner_releases_unused_cuda_cache_after_inference(monkeypatch):
    import sys
    import types
    from contextlib import nullcontext
    from types import SimpleNamespace

    from app.handler import Qwen3ASRHandler
    from bobogen_protocol.models import GenerateRequest

    released = []

    class FakeBatch(dict):
        def to(self, _device, _dtype):
            return self

    class FakeProcessor:
        def prepare_forced_aligner_inputs(self, **_kwargs):
            return FakeBatch(input_ids="input-ids"), [[]]

        def decode_forced_alignment(self, **_kwargs):
            return [[]]

    class FakeModel:
        device = "cuda:0"
        dtype = "bfloat16"
        config = SimpleNamespace(timestamp_token_id=151705, timestamp_segment_time=80)

        def __call__(self, **_inputs):
            return SimpleNamespace(logits="logits")

    fake_torch = types.SimpleNamespace(
        inference_mode=nullcontext,
        cuda=types.SimpleNamespace(empty_cache=lambda: released.append(True)),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    handler = Qwen3ASRHandler(test_mode=False)
    handler._aligner = (FakeModel(), FakeProcessor())
    request = GenerateRequest.model_validate(
        {
            "model": "qwen3_asr_0_6b",
            "task": "audio.align",
            "input": {"audio": "line.wav", "text": "你好", "language": "Chinese"},
            "output": {"format": "json"},
        }
    )

    handler.align(request)

    assert released == [True]


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
