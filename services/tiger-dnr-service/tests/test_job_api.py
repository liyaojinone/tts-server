from io import BytesIO
import json
from pathlib import Path
import threading
import time
import wave

from fastapi.testclient import TestClient
import pytest


def _write_source(
    path: Path,
    *,
    frames: int = 80,
    sample_rate: int = 8000,
) -> None:
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        samples = b"".join(
            int((index % 20 - 10) * 500).to_bytes(2, "little", signed=True)
            for index in range(frames)
        )
        wav.writeframes(samples)
    path.write_bytes(output.getvalue())


def _wait_for_terminal(
    client: TestClient,
    job_id: str,
    timeout: float = 3.0,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("job did not reach terminal state")


def _wait_for_status(
    client: TestClient,
    job_id: str,
    expected: set[str],
    timeout: float = 3.0,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/jobs/{job_id}")
        if response.status_code == 404:
            if "missing" in expected:
                return None
            raise AssertionError("job disappeared before expected status")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(
        f"job did not reach one of the expected statuses: {expected}"
    )


def test_service_runs_one_job_and_publishes_dialogue_and_background(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(tmp_path / "jobs"))
    source = tmp_path / "source.wav"
    _write_source(source)

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        created = client.post(
            "/v1/jobs",
            json={
                "job_id": "opaque-job-id",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "input": {"audio": str(source)},
                    "parameters": {},
                    "output": {"format": "wav"},
                },
            },
        )

        assert created.status_code == 202
        assert created.json()["id"] == "opaque-job-id"
        terminal = _wait_for_terminal(client, "opaque-job-id")

        assert terminal["status"] == "succeeded"
        assert terminal["progress"]["fraction"] == 1.0
        assert [item["role"] for item in terminal["artifacts"]] == [
            "dialogue",
            "background",
        ]
        job_dir = tmp_path / "jobs" / "opaque-job-id"
        manifest = json.loads(
            (job_dir / "job.json").read_text(encoding="utf-8")
        )
        owned_input = Path(
            manifest["request"]["input"]["audio"]
        )
        assert owned_input.parent == job_dir
        assert owned_input != source
        assert owned_input.is_file()
        for artifact in terminal["artifacts"]:
            response = client.get(
                f"/v1/jobs/opaque-job-id/artifacts/{artifact['id']}"
            )
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("audio/wav")
            assert response.content.startswith(b"RIFF")


def test_service_cancels_queued_or_running_job_without_publishing_partial_artifacts(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("TIGER_DNR_TEST_CHUNK_DELAY", "0.03")
    source = tmp_path / "long.wav"
    _write_source(source, frames=8000 * 3)

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        created = client.post(
            "/v1/jobs",
            json={
                "job_id": "cancel-me",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "input": {"audio": str(source)},
                },
            },
        )
        assert created.status_code == 202

        cancelled = client.post("/v1/jobs/cancel-me/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] in {"cancelling", "cancelled"}

        terminal = _wait_for_terminal(client, "cancel-me")
        assert terminal["status"] == "cancelled"
        assert terminal["artifacts"] == []
        job_dir = tmp_path / "jobs" / "cancel-me"
        assert not list(job_dir.glob("*.partial.wav"))
        assert not list(job_dir.glob("dialogue.wav"))


def test_delete_can_reserve_and_cancel_job_while_input_copy_is_in_progress(
    tmp_path,
):
    from bobogen_protocol.models import GenerateRequest

    from app.handler import TigerDNRHandler
    from app.job_manager import (
        JobNotFoundError,
        TigerDNRJobManager,
    )

    source = tmp_path / "source.wav"
    _write_source(source, frames=8000)
    manager = TigerDNRJobManager(
        TigerDNRHandler(test_mode=True),
        root=tmp_path / "jobs",
    )
    original_copy = manager._copy_source
    copy_started = threading.Event()
    allow_copy = threading.Event()
    result = {}

    def blocked_copy(source_path, destination, job_id):
        copy_started.set()
        assert allow_copy.wait(timeout=3)
        original_copy(source_path, destination, job_id)

    def create_job():
        try:
            result["response"] = manager.create(
                "copy-race",
                GenerateRequest.model_validate(
                    {
                        "model": "tiger-dnr",
                        "task": "audio.separate",
                        "input": {"audio": str(source)},
                    }
                ),
            )
        except Exception as exc:
            result["error"] = exc

    manager._copy_source = blocked_copy
    thread = threading.Thread(target=create_job)
    try:
        thread.start()
        assert copy_started.wait(timeout=3)

        manager.delete("copy-race")
        allow_copy.set()
        thread.join(timeout=5)

        assert not thread.is_alive()
        assert "error" not in result
        assert result["response"]["status"] == "cancelled"
        with pytest.raises(JobNotFoundError):
            manager.get("copy-race")
        assert not (tmp_path / "jobs" / "copy-race").exists()
    finally:
        allow_copy.set()
        thread.join(timeout=5)
        manager.shutdown()


def test_delete_before_create_thread_starts_reserves_job_id(
    tmp_path,
):
    from bobogen_protocol.models import GenerateRequest

    from app.handler import TigerDNRHandler
    from app.job_manager import (
        JobAlreadyExistsError,
        TigerDNRJobManager,
    )

    source = tmp_path / "source.wav"
    _write_source(source)
    manager = TigerDNRJobManager(
        TigerDNRHandler(test_mode=True),
        root=tmp_path / "jobs",
    )
    try:
        manager.delete("reserved-before-create")

        with pytest.raises(JobAlreadyExistsError):
            manager.create(
                "reserved-before-create",
                GenerateRequest.model_validate(
                    {
                        "model": "tiger-dnr",
                        "task": "audio.separate",
                        "input": {"audio": str(source)},
                    }
                ),
            )
        assert (
            tmp_path
            / "jobs"
            / "reserved-before-create"
            / "delete.tombstone"
        ).is_file()
    finally:
        manager.shutdown()


def test_cancel_between_final_check_and_publish_cannot_be_overwritten_by_success(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "TIGER_DNR_JOB_ROOT",
        str(tmp_path / "jobs"),
    )
    source = tmp_path / "source.wav"
    _write_source(source)

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        manager = client.app.state.job_manager
        original_check = manager._raise_if_cancelled

        def cancel_after_check(job_id):
            original_check(job_id)
            manager.cancel(job_id)

        manager._raise_if_cancelled = cancel_after_check
        created = client.post(
            "/v1/jobs",
            json={
                "job_id": "cancel-publish-race",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "input": {"audio": str(source)},
                },
            },
        )
        assert created.status_code == 202

        terminal = _wait_for_terminal(
            client,
            "cancel-publish-race",
        )
        assert terminal["status"] == "cancelled"
        assert terminal["artifacts"] == []
        job_dir = tmp_path / "jobs" / "cancel-publish-race"
        assert not (job_dir / "dialogue.wav").exists()
        assert not (job_dir / "background.wav").exists()


def test_delete_after_cancel_accepts_running_job_and_removes_manifest_and_inputs(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("TIGER_DNR_TEST_CHUNK_DELAY", "0.05")
    source = tmp_path / "long.wav"
    _write_source(source, frames=8000 * 12)

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        created = client.post(
            "/v1/jobs",
            json={
                "job_id": "delete-running",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "input": {"audio": str(source)},
                    "parameters": {},
                    "output": {"format": "wav"},
                },
            },
        )
        assert created.status_code == 202
        _wait_for_status(client, "delete-running", {"running"})

        cancelled = client.post(
            "/v1/jobs/delete-running/cancel"
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] in {
            "cancelling",
            "cancelled",
        }

        deleted = client.delete("/v1/jobs/delete-running")
        assert deleted.status_code == 204
        _wait_for_status(client, "delete-running", {"missing"})

        job_dir = tmp_path / "jobs" / "delete-running"
        deadline = time.monotonic() + 3
        while job_dir.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not job_dir.exists()


def test_delete_tombstone_waits_for_artifact_lease_and_cannot_revive_on_restart(
    tmp_path,
    monkeypatch,
):
    job_root = tmp_path / "jobs"
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(job_root))
    source = tmp_path / "source.wav"
    _write_source(source)

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        created = client.post(
            "/v1/jobs",
            json={
                "job_id": "leased-download",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "input": {"audio": str(source)},
                },
            },
        )
        assert created.status_code == 202
        terminal = _wait_for_terminal(
            client,
            "leased-download",
        )
        artifact_id = terminal["artifacts"][0]["id"]
        manager = client.app.state.job_manager
        path, _artifact = manager.artifact_path(
            "leased-download",
            artifact_id,
        )
        open_stream = path.open("rb")
        job_dir = job_root / "leased-download"

        try:
            manager.delete("leased-download")
            manifest = json.loads(
                (job_dir / "job.json").read_text(
                    encoding="utf-8"
                )
            )
            assert manifest["delete_requested"] is True
            assert client.get(
                "/v1/jobs/leased-download"
            ).status_code == 404
            assert job_dir.exists()
        finally:
            open_stream.close()
            manager.release_artifact("leased-download")

        deadline = time.monotonic() + 3
        while job_dir.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not job_dir.exists()

    with TestClient(create_app(test_mode=True)) as restarted:
        assert restarted.get(
            "/v1/jobs/leased-download"
        ).status_code == 404


def test_restart_finishes_deferred_delete_from_manifest(
    tmp_path,
    monkeypatch,
):
    job_root = tmp_path / "jobs"
    job_dir = job_root / "delete-after-restart"
    job_dir.mkdir(parents=True)
    (job_dir / "input.wav").write_bytes(b"staged-input")
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "job": {"id": "delete-after-restart"},
                "request": None,
                "delete_requested": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(job_root))

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        response = client.get(
            "/v1/jobs/delete-after-restart"
        )
        assert response.status_code == 404
        assert not job_dir.exists()


def test_restart_marks_interrupted_job_failed_and_removes_unpublished_wavs(
    tmp_path,
    monkeypatch,
):
    job_root = tmp_path / "jobs"
    job_dir = job_root / "interrupted"
    job_dir.mkdir(parents=True)
    source = job_dir / "input.wav"
    _write_source(source)
    for name in (
        "dialogue.partial.wav",
        "background.partial.wav",
        "dialogue.wav",
        "background.wav",
    ):
        (job_dir / name).write_bytes(b"unpublished")
    request = {
        "model": "tiger-dnr",
        "task": "audio.separate",
        "input": {"audio": str(source)},
        "parameters": {},
        "output": {"format": "wav"},
    }
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "job": {
                    "id": "interrupted",
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "status": "running",
                    "progress": {
                        "phase": "encoding",
                        "fraction": 0.95,
                        "message": None,
                    },
                    "artifacts": [],
                    "error": None,
                },
                "request": request,
                "delete_requested": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(job_root))

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        response = client.get("/v1/jobs/interrupted")
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["error"]["code"] == (
            "SERVICE_RESTARTED"
        )
        assert not list(job_dir.glob("*.partial.wav"))
        assert not (job_dir / "dialogue.wav").exists()
        assert not (job_dir / "background.wav").exists()


def test_restart_ignores_manifest_whose_id_escapes_or_mismatches_root(
    tmp_path,
    monkeypatch,
):
    job_root = tmp_path / "jobs"
    unsafe_dir = job_root / "unsafe"
    unsafe_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    (unsafe_dir / "job.json").write_text(
        json.dumps(
            {
                "job": {
                    "id": r"..\outside",
                    "status": "succeeded",
                },
                "request": None,
                "delete_requested": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(job_root))

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        assert client.get("/v1/jobs/unsafe").status_code == 404
        assert sentinel.read_text(encoding="utf-8") == "keep"
        assert unsafe_dir.exists()


def test_service_rejects_wrong_task_duplicate_job_and_unknown_artifact(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TIGER_DNR_JOB_ROOT", str(tmp_path / "jobs"))
    source = tmp_path / "source.wav"
    _write_source(source)

    from app.main import create_app

    with TestClient(create_app(test_mode=True)) as client:
        wrong_task = client.post(
            "/v1/jobs",
            json={
                "job_id": "wrong",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.generate",
                    "input": {"audio": str(source)},
                },
            },
        )
        assert wrong_task.status_code == 400
        assert wrong_task.json()["error"]["code"] == "UNSUPPORTED_TASK"

        first = client.post(
            "/v1/jobs",
            json={
                "job_id": "duplicate",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "input": {"audio": str(source)},
                },
            },
        )
        assert first.status_code == 202
        duplicate = client.post(
            "/v1/jobs",
            json={
                "job_id": "duplicate",
                "request": {
                    "model": "tiger-dnr",
                    "task": "audio.separate",
                    "input": {"audio": str(source)},
                },
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "JOB_ALREADY_EXISTS"

        missing = client.get(
            "/v1/jobs/duplicate/artifacts/not-found"
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"
