from fastapi.testclient import TestClient


class DummyHandler:
    def __init__(self):
        self.started = False
        self.last_synthesize = None

    async def startup(self):
        self.started = True

    async def health(self):
        return {"status": "ok", "started": self.started}

    async def list_voices(self, language=None, page=1, page_size=100):
        return {
            "voices": [{"voice_id": "default", "name": "Default", "language": ["zh"], "metadata": {}}],
            "total": 1,
            "page": page,
            "page_size": page_size,
        }

    async def synthesize(self, request, reference_audio=None, reference_text=None):
        self.last_synthesize = {
            "request": request,
            "reference_audio": reference_audio,
            "reference_text": reference_text,
        }
        return {
            "content": b"RIFF",
            "content_type": "audio/wav",
            "headers": {"X-Audio-Duration": "1.0"},
        }

    async def clone(self, request, audio):
        return {"voice_id": request.name or "dummy", "status": "ready", "name": request.name}

    async def clone_status(self, task_id):
        return {"task_id": task_id, "status": "ready", "voice_id": "dummy", "name": "Dummy"}


class ErrorHandler(DummyHandler):
    async def synthesize(self, request, reference_audio=None, reference_text=None):
        raise ValueError("unknown voice_id")


def test_app_factory_exposes_protocol_routes():
    from bobogen_service_kit.app import create_service_app

    app = create_service_app("dummy", DummyHandler())
    client = TestClient(app)

    with client:
        health = client.get("/v1/health")
        assert health.status_code == 200
        assert health.json()["started"] is True
        assert client.get("/v1/voices").status_code == 200
        synth = client.post(
            "/v1/synthesize",
            json={"text": "你好", "voice_id": "default", "parameters": {}, "output": {"format": "wav"}},
        )
        assert synth.status_code == 200
        assert synth.headers["content-type"].startswith("audio/wav")
        clone = client.post(
            "/v1/clone",
            data={"name": "测试音色", "language": "zh", "text": "参考文本"},
            files={"audio": ("ref.wav", b"RIFF", "audio/wav")},
        )
        assert clone.status_code == 200
        clone_status = client.get("/v1/clone/dummy/status")
        assert clone_status.status_code == 200
        assert clone_status.json()["status"] == "ready"
        stream = client.post(
            "/v1/synthesize/stream",
            json={"text": "你好", "voice_id": "default", "parameters": {}, "output": {"format": "wav"}},
        )
        assert stream.status_code == 404
        design = client.post("/v1/design", json={"base_voice_id": "default", "name": "新音色", "parameters": {"extra": {}}})
        assert design.status_code == 404


def test_app_factory_supports_bearer_auth():
    from bobogen_service_kit.app import create_service_app

    app = create_service_app("dummy", DummyHandler(), api_key="secret")
    client = TestClient(app)

    unauthorized = client.get("/v1/health")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED"

    authorized = client.get("/v1/health", headers={"Authorization": "Bearer secret"})
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "ok"


def test_app_factory_returns_standard_error_payloads():
    from bobogen_service_kit.app import create_service_app

    app = create_service_app("dummy", ErrorHandler())
    client = TestClient(app)

    response = client.post(
        "/v1/synthesize",
        json={"text": "你好", "voice_id": "missing", "parameters": {}, "output": {"format": "wav"}},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "VOICE_NOT_FOUND"
    assert "voice" in payload["error"]["message"].lower()


def test_app_factory_stores_emotion_reference_audio_upload_in_extra_for_multipart_requests():
    from bobogen_service_kit.app import create_service_app

    handler = DummyHandler()
    app = create_service_app("dummy", handler)
    client = TestClient(app)

    response = client.post(
        "/v1/synthesize",
        data={
            "request": """{
                "text": "你好",
                "voice_id": "default",
                "language": "zh",
                "parameters": {
                    "reference_text": "主参考文本"
                },
                "output": {"format": "wav"}
            }""",
            "reference_text": "上传主参考文本",
        },
        files={
            "reference_audio": ("speaker.wav", b"RIFFspeaker", "audio/wav"),
            "emotion_reference_audio": ("emotion.wav", b"RIFFemotion", "audio/wav"),
        },
    )

    assert response.status_code == 200
    assert handler.last_synthesize is not None
    assert handler.last_synthesize["reference_audio"].filename == "speaker.wav"
    assert handler.last_synthesize["request"].parameters.extra["emotion_reference_audio_upload_name"] == "emotion.wav"
    assert handler.last_synthesize["request"].parameters.extra["_emotion_reference_audio_upload"].filename == "emotion.wav"
