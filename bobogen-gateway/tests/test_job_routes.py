import asyncio
from io import BytesIO
from pathlib import Path
import json
import wave

from fastapi.testclient import TestClient
import httpx
import pytest


def _wav_bytes(*, sample_rate: int = 8000, frames: int = 16) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


class StubJobAdapter:
    provider_type = "stub"

    def __init__(self):
        self.created = []
        self.cancelled = []
        self.deleted = []
        self.artifact_bytes = _wav_bytes()

    async def create_job(self, provider, job_id, request):
        audio_path = Path(request.input["audio"])
        self.created.append(
            {
                "provider_id": provider.provider_id,
                "job_id": job_id,
                "task": request.task,
                "audio_path": audio_path,
                "exists": audio_path.exists(),
                "content": (
                    audio_path.read_bytes()
                    if audio_path.exists()
                    else None
                ),
            }
        )
        return {
            "id": job_id,
            "model": request.model,
            "task": request.task,
            "status": "queued",
            "progress": {"phase": "preparing", "fraction": 0.0},
            "artifacts": [],
        }

    async def get_job(self, provider, job_id):
        return {
            "id": job_id,
            "model": provider.model_id,
            "task": "audio.separate",
            "status": "succeeded",
            "progress": {"phase": "validating", "fraction": 1.0},
            "artifacts": [
                {
                    "id": "dialogue-artifact",
                    "role": "dialogue",
                    "filename": "dialogue.wav",
                    "content_type": "audio/wav",
                    "size_bytes": len(self.artifact_bytes),
                    "sample_rate": 8000,
                    "channels": 1,
                    "frame_count": 16,
                    "sha256": "a" * 64,
                },
                {
                    "id": "background-artifact",
                    "role": "background",
                    "filename": "background.wav",
                    "content_type": "audio/wav",
                    "size_bytes": len(self.artifact_bytes),
                    "sample_rate": 8000,
                    "channels": 1,
                    "frame_count": 16,
                    "sha256": "b" * 64,
                },
            ],
        }

    async def cancel_job(self, provider, job_id):
        self.cancelled.append((provider.provider_id, job_id))
        return {
            "id": job_id,
            "model": provider.model_id,
            "task": "audio.separate",
            "status": "cancelling",
            "progress": {"phase": "separating", "fraction": 0.5},
            "artifacts": [],
        }

    async def get_artifact(self, provider, job_id, artifact_id):
        assert provider.provider_id == "tiger_dnr"
        assert job_id == self.created[-1]["job_id"]
        assert artifact_id == "dialogue-artifact"
        return {
            "stream": iter([self.artifact_bytes[:10], self.artifact_bytes[10:]]),
            "content_type": "audio/wav",
            "filename": "dialogue.wav",
            "size_bytes": len(self.artifact_bytes),
        }

    async def delete_job(self, provider, job_id):
        self.deleted.append((provider.provider_id, job_id))


class UnavailableCreateAdapter(StubJobAdapter):
    async def create_job(self, provider, job_id, request):
        await super().create_job(provider, job_id, request)

        from app.core.exceptions import ProviderUnavailableError

        raise ProviderUnavailableError(
            "provider connection closed before the response",
            {"provider_id": provider.provider_id},
            status_code=503,
        )


class MalformedPayloadAdapter(StubJobAdapter):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    async def create_job(self, provider, job_id, request):
        payload = await super().create_job(
            provider,
            job_id,
            request,
        )
        if self.kind == "missing-id":
            payload.pop("id")
        else:
            payload["status"] = "not-a-job-status"
        return payload


class IdentityMismatchAdapter(StubJobAdapter):
    def __init__(self, field, value):
        super().__init__()
        self.field = field
        self.value = value

    async def create_job(self, provider, job_id, request):
        payload = await super().create_job(
            provider,
            job_id,
            request,
        )
        payload[self.field] = self.value
        return payload


class LeaseAwareArtifactAdapter(StubJobAdapter):
    def __init__(self):
        super().__init__()
        self.events = []
        self.release_stream = asyncio.Event()
        self.stream_started = asyncio.Event()
        self.lease_count = 0

    async def get_artifact(self, provider, job_id, artifact_id):
        self.lease_count += 1
        self.events.append("upstream-open")

        async def stream():
            self.events.append("stream-start")
            self.stream_started.set()
            try:
                yield self.artifact_bytes[:10]
                await self.release_stream.wait()
                yield self.artifact_bytes[10:]
            finally:
                self.lease_count -= 1
                self.events.append("stream-close")

        return {
            "stream": stream(),
            "content_type": "audio/wav",
            "filename": "dialogue.wav",
            "size_bytes": len(self.artifact_bytes),
        }

    async def delete_job(self, provider, job_id):
        self.events.append(f"delete:lease={self.lease_count}")
        await super().delete_job(provider, job_id)


class MissingRemoteDeleteAdapter(StubJobAdapter):
    async def delete_job(self, provider, job_id):
        from app.core.exceptions import GatewayError

        raise GatewayError(
            f"Job not found: {job_id}",
            {},
            status_code=404,
        )


def test_default_job_store_uses_durable_workspace_runtime(
    tmp_path,
    monkeypatch,
):
    from app.services.job_store import GatewayJobStore

    monkeypatch.delenv("BOBOGEN_JOB_ROOT", raising=False)
    monkeypatch.setenv("BOBOGEN_ROOT", str(tmp_path))

    store = GatewayJobStore()

    assert store.root == tmp_path / "runtime" / "gateway-jobs"


def test_job_store_ignores_manifest_outside_its_root(tmp_path):
    from app.services.job_store import (
        GatewayJobStore,
        JobNotFoundError,
    )

    root = tmp_path / "jobs"
    job_dir = root / "unsafe"
    outside = tmp_path / "outside"
    job_dir.mkdir(parents=True)
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    (job_dir / "gateway.json").write_text(
        json.dumps(
            {
                "id": "unsafe",
                "provider_id": "tiger_dnr",
                "model": "tiger-dnr",
                "task": "audio.separate",
                "job_dir": str(outside),
            }
        ),
        encoding="utf-8",
    )

    store = GatewayJobStore(root=root)

    with pytest.raises(JobNotFoundError):
        store.get("unsafe")
    assert sentinel.read_text(encoding="utf-8") == "keep"


def _client_with_stub(tmp_path):
    from app.main import create_app
    from app.services.job_store import GatewayJobStore

    app = create_app()
    app.state.job_store = GatewayJobStore(
        root=tmp_path / "gateway-jobs"
    )
    adapter = StubJobAdapter()
    manager = app.state.process_manager
    registry = app.state.provider_registry

    ensure_started_calls = []

    async def fake_ensure_started(provider_id):
        ensure_started_calls.append(provider_id)
        return manager.get_state(provider_id)

    manager.ensure_started = fake_ensure_started
    registry._adapters["tiger_dnr"] = adapter
    return TestClient(app), adapter, ensure_started_calls


def test_create_job_streams_upload_to_persistent_job_input(tmp_path):
    client, adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )
    source = _wav_bytes()

    response = client.post(
        "/v1/jobs",
        data={
            "request": """{
                "model": "tiger-dnr",
                "task": "audio.separate",
                "input": {"audio": {"kind": "upload", "field": "audio"}},
                "parameters": {},
                "output": {"format": "wav"}
            }"""
        },
        files={"audio": ("source.wav", source, "audio/wav")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["id"]
    assert payload["status"] == "queued"
    assert payload["progress"] == {"phase": "preparing", "fraction": 0.0, "message": None}
    assert adapter.created[0]["job_id"] == payload["id"]
    assert adapter.created[0]["exists"] is True
    assert adapter.created[0]["content"] == source
    assert adapter.created[0]["audio_path"].parent.name == "inputs"


def test_create_job_cleans_provider_after_uncertain_submission_failure(
    tmp_path,
):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )
    adapter = UnavailableCreateAdapter()
    client.app.state.provider_registry._adapters[
        "tiger_dnr"
    ] = adapter

    response = client.post(
        "/v1/jobs",
        data={
            "request": """{
                "model": "tiger-dnr",
                "task": "audio.separate",
                "input": {"audio": {"kind": "upload", "field": "audio"}}
            }"""
        },
        files={
            "audio": (
                "source.wav",
                _wav_bytes(),
                "audio/wav",
            )
        },
    )

    assert response.status_code == 503
    job_id = adapter.created[0]["job_id"]
    assert adapter.deleted == [("tiger_dnr", job_id)]
    from app.services.job_store import JobNotFoundError

    with pytest.raises(JobNotFoundError):
        client.app.state.job_store.get(job_id)


@pytest.mark.parametrize(
    "kind",
    ["missing-id", "invalid-status"],
)
def test_create_job_deletes_provider_after_invalid_202_payload(
    tmp_path,
    kind,
):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )
    adapter = MalformedPayloadAdapter(kind)
    client.app.state.provider_registry._adapters[
        "tiger_dnr"
    ] = adapter

    response = client.post(
        "/v1/jobs",
        data={
            "request": """{
                "model": "tiger-dnr",
                "task": "audio.separate",
                "input": {"audio": {"kind": "upload", "field": "audio"}}
            }"""
        },
        files={
            "audio": (
                "source.wav",
                _wav_bytes(),
                "audio/wav",
            )
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == (
        "INVALID_PROVIDER_RESPONSE"
    )
    job_id = adapter.created[0]["job_id"]
    assert adapter.deleted == [("tiger_dnr", job_id)]
    from app.services.job_store import JobNotFoundError

    with pytest.raises(JobNotFoundError):
        client.app.state.job_store.get(job_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "different-provider-job"),
        ("model", "different-model"),
        ("task", "tts.speech"),
    ],
)
def test_create_job_deletes_provider_after_identity_mismatch(
    tmp_path,
    field,
    value,
):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )
    adapter = IdentityMismatchAdapter(field, value)
    client.app.state.provider_registry._adapters[
        "tiger_dnr"
    ] = adapter

    response = client.post(
        "/v1/jobs",
        json={
            "model": "tiger-dnr",
            "task": "audio.separate",
            "input": {
                "audio": {
                    "kind": "path",
                    "path": "E:/audio/source.wav",
                }
            },
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == (
        "INVALID_PROVIDER_RESPONSE"
    )
    job_id = adapter.created[0]["job_id"]
    assert adapter.deleted == [("tiger_dnr", job_id)]
    from app.services.job_store import JobNotFoundError

    with pytest.raises(JobNotFoundError):
        client.app.state.job_store.get(job_id)


def test_create_job_deletes_provider_after_non_json_202(
    tmp_path,
    monkeypatch,
):
    from app.adapters.tiger_dnr import TigerDNRAdapter

    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )
    adapter = TigerDNRAdapter()
    calls = []

    async def fake_request(provider, method, path, **_kwargs):
        calls.append((method, path))
        request = httpx.Request(
            method,
            f"{provider.network.base_url}{path}",
        )
        if method == "POST":
            return httpx.Response(
                202,
                text="not-json",
                request=request,
            )
        return httpx.Response(204, request=request)

    monkeypatch.setattr(adapter, "_request", fake_request)
    client.app.state.provider_registry._adapters[
        "tiger_dnr"
    ] = adapter

    response = client.post(
        "/v1/jobs",
        data={
            "request": """{
                "model": "tiger-dnr",
                "task": "audio.separate",
                "input": {"audio": {"kind": "upload", "field": "audio"}}
            }"""
        },
        files={
            "audio": (
                "source.wav",
                _wav_bytes(),
                "audio/wav",
            )
        },
    )

    assert response.status_code == 502
    assert calls[0] == ("POST", "/v1/jobs")
    assert calls[1][0] == "DELETE"
    assert not list(client.app.state.job_store.root.iterdir())


def test_async_separation_rejects_data_uri_input(tmp_path):
    client, adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )

    response = client.post(
        "/v1/jobs",
        json={
            "model": "tiger-dnr",
            "task": "audio.separate",
            "input": {
                "audio": {
                    "kind": "data_uri",
                    "data": (
                        "data:audio/wav;base64,"
                        "UklGRgAAAAA="
                    ),
                }
            },
        },
    )

    assert response.status_code == 400
    assert "data_uri is not supported" in (
        response.json()["error"]["message"]
    )
    assert adapter.created == []


def test_async_separation_rejects_oversized_json_before_decoding(
    tmp_path,
):
    client, adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )

    response = client.post(
        "/v1/jobs",
        json={
            "model": "tiger-dnr",
            "task": "audio.separate",
            "input": {
                "audio": {
                    "kind": "data_uri",
                    "data": "A" * (1024 * 1024),
                }
            },
        },
    )

    assert response.status_code == 400
    assert "too large" in response.json()["error"]["message"]
    assert adapter.created == []


def test_upload_filename_suffix_is_whitelisted():
    from app.routers.jobs import _safe_upload_name

    assert _safe_upload_name(
        "audio",
        r"\\server\share\voice.wav:stream",
    ) == "audio.bin"
    assert _safe_upload_name(
        "../audio",
        "CON.M4A",
    ) == "audio.m4a"


def test_create_job_reports_storage_errors_as_server_errors(
    tmp_path,
    monkeypatch,
):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )

    def fail_create(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        client.app.state.job_store,
        "create",
        fail_create,
    )

    response = client.post(
        "/v1/jobs",
        json={
            "model": "tiger-dnr",
            "task": "audio.separate",
            "input": {
                "audio": {
                    "kind": "path",
                    "path": "E:/audio/source.wav",
                }
            },
        },
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "JOB_IO_ERROR"


def test_job_status_cancel_artifact_and_delete_are_proxied(tmp_path):
    client, adapter, ensure_started_calls = _client_with_stub(
        tmp_path
    )

    created = client.post(
        "/v1/jobs",
        json={
            "model": "tiger-dnr",
            "task": "audio.separate",
            "input": {"audio": {"kind": "path", "path": "E:/audio/source.wav"}},
            "parameters": {},
            "output": {"format": "wav"},
        },
    )
    job_id = created.json()["id"]

    status = client.get(f"/v1/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"
    assert [item["role"] for item in status.json()["artifacts"]] == ["dialogue", "background"]

    cancel = client.post(f"/v1/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelling"

    artifact = client.get(f"/v1/jobs/{job_id}/artifacts/dialogue-artifact")
    assert artifact.status_code == 200
    assert artifact.content == adapter.artifact_bytes
    assert artifact.headers["content-disposition"] == 'attachment; filename="dialogue.wav"'

    deleted = client.delete(f"/v1/jobs/{job_id}")
    assert deleted.status_code == 204
    assert adapter.cancelled == [("tiger_dnr", job_id)]
    assert adapter.deleted == [("tiger_dnr", job_id)]
    assert ensure_started_calls == ["tiger_dnr"] * 5

    missing = client.get(f"/v1/jobs/{job_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_artifact_stream_holds_upstream_lease_during_delete(tmp_path):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )
    adapter = LeaseAwareArtifactAdapter()
    client.app.state.provider_registry._adapters[
        "tiger_dnr"
    ] = adapter
    job_id = "stream-delete-order"
    client.app.state.job_store.create(
        job_id=job_id,
        provider_id="tiger_dnr",
        model="tiger-dnr",
        task="audio.separate",
    )

    async def request(method, path, *, on_send=None):
        messages = []
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }
            await asyncio.Future()

        async def send(message):
            messages.append(message)
            if on_send is not None:
                on_send(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        await client.app(scope, receive, send)
        return messages

    async def scenario():
        def record_stream_message(message):
            if message["type"] == "http.response.start":
                adapter.events.append("gateway-200")

        stream_task = asyncio.create_task(
            request(
                "GET",
                (
                    f"/v1/jobs/{job_id}/artifacts/"
                    "dialogue-artifact"
                ),
                on_send=record_stream_message,
            )
        )
        await asyncio.wait_for(
            adapter.stream_started.wait(),
            timeout=1,
        )

        assert adapter.events[:3] == [
            "upstream-open",
            "gateway-200",
            "stream-start",
        ]
        delete_messages = await request(
            "DELETE",
            f"/v1/jobs/{job_id}",
        )
        assert any(
            message.get("status") == 204
            for message in delete_messages
        )
        assert adapter.events[-1] == "delete:lease=1"

        adapter.release_stream.set()
        stream_messages = await asyncio.wait_for(
            stream_task,
            timeout=1,
        )
        assert adapter.events[-1] == "stream-close"
        assert adapter.lease_count == 0
        assert b"".join(
            message.get("body", b"")
            for message in stream_messages
            if message["type"] == "http.response.body"
        ) == adapter.artifact_bytes

    asyncio.run(scenario())


def test_delete_is_idempotent_when_provider_job_is_already_missing(
    tmp_path,
):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )
    adapter = MissingRemoteDeleteAdapter()
    client.app.state.provider_registry._adapters[
        "tiger_dnr"
    ] = adapter
    created = client.post(
        "/v1/jobs",
        json={
            "model": "tiger-dnr",
            "task": "audio.separate",
            "input": {
                "audio": {
                    "kind": "path",
                    "path": "E:/audio/source.wav",
                }
            },
        },
    )
    job_id = created.json()["id"]

    deleted = client.delete(f"/v1/jobs/{job_id}")

    assert deleted.status_code == 204
    assert client.get(f"/v1/jobs/{job_id}").status_code == 404


def test_create_job_rejects_sync_task_and_wrong_model_task(tmp_path):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )

    response = client.post(
        "/v1/jobs",
        json={
            "model": "local_f5_tts",
            "task": "tts.speech",
            "input": {"text": "hello"},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_ASYNC_TASK"


def test_unknown_job_and_artifact_return_structured_errors(tmp_path):
    client, _adapter, _ensure_started_calls = _client_with_stub(
        tmp_path
    )

    missing_job = client.get("/v1/jobs/not-found")
    assert missing_job.status_code == 404
    assert missing_job.json()["error"]["code"] == "JOB_NOT_FOUND"

    created = client.post(
        "/v1/jobs",
        json={
            "model": "tiger-dnr",
            "task": "audio.separate",
            "input": {"audio": {"kind": "path", "path": "E:/audio/source.wav"}},
        },
    )
    job_id = created.json()["id"]

    missing_artifact = client.get(f"/v1/jobs/{job_id}/artifacts/not-found")
    assert missing_artifact.status_code == 404
    assert missing_artifact.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"
