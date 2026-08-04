from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from queue import Queue
import shutil
import threading
from typing import Any

from bobogen_protocol.models import GenerateRequest, JobResponse

from app.handler import (
    SeparationCancelled,
    TigerDNRHandler,
)


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class JobNotFoundError(LookupError):
    pass


class ArtifactNotFoundError(LookupError):
    pass


class JobAlreadyExistsError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TigerDNRJobManager:
    def __init__(
        self,
        handler: TigerDNRHandler,
        *,
        root: Path,
    ):
        self.handler = handler
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._resolved_root = self.root.resolve()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._requests: dict[str, GenerateRequest] = {}
        self._artifact_paths: dict[tuple[str, str], Path] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._delete_requested: set[str] = set()
        self._preparing_jobs: set[str] = set()
        self._download_leases: dict[str, int] = {}
        self._cleanup_retrying: set[str] = set()
        self._lock = threading.RLock()
        self._queue: Queue[str | None] = Queue()
        self._load_existing_jobs()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="tiger-dnr-gpu-worker",
            daemon=True,
        )
        self._worker.start()

    def create(
        self,
        job_id: str,
        request: GenerateRequest,
    ) -> dict:
        if request.task != "audio.separate":
            raise ValueError(
                f"Unsupported TIGER-DnR task: {request.task}"
            )
        if request.model != "tiger-dnr":
            raise ValueError(
                f"Unsupported TIGER-DnR model: {request.model}"
            )
        if request.output.format.lower() != "wav":
            raise ValueError("TIGER-DnR first version only outputs WAV")
        source = Path(str(request.input.get("audio") or ""))
        if not source.is_file():
            raise ValueError(f"Audio input not found: {source}")

        with self._lock:
            if job_id in self._jobs:
                raise JobAlreadyExistsError(job_id)
            job_dir = self._job_dir(job_id)
            if job_dir.exists():
                raise JobAlreadyExistsError(job_id)
            job_dir.mkdir(parents=True)
            now = _now()
            job = {
                "id": job_id,
                "model": request.model,
                "task": request.task,
                "status": "queued",
                "progress": {
                    "phase": "preparing",
                    "fraction": 0.0,
                    "message": "正在复制任务输入",
                },
                "artifacts": [],
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
            self._jobs[job_id] = job
            self._requests[job_id] = request.model_copy(
                deep=True
            )
            self._cancel_events[job_id] = threading.Event()
            self._preparing_jobs.add(job_id)
            self._persist(job_id)

        local_source = job_dir / (
            f"input{source.suffix}" if source.suffix else "input.bin"
        )
        partial_source = local_source.with_suffix(
            f"{local_source.suffix}.partial"
        )
        try:
            self._copy_source(
                source,
                partial_source,
                job_id,
            )
            self._raise_if_cancelled(job_id)
            os.replace(partial_source, local_source)
            owned_request = request.model_copy(deep=True)
            owned_request.input["audio"] = str(local_source)
            with self._lock:
                cancel_event = self._cancel_events.get(job_id)
                if (
                    cancel_event is None
                    or cancel_event.is_set()
                ):
                    raise SeparationCancelled(
                        "separation cancelled"
                    )
                self._requests[job_id] = owned_request
                self._preparing_jobs.discard(job_id)
                job = self._jobs[job_id]
                job["progress"]["message"] = None
                job["updated_at"] = _now()
                self._persist(job_id)
                self._queue.put(job_id)
                return self._public(job)
        except SeparationCancelled:
            partial_source.unlink(missing_ok=True)
            local_source.unlink(missing_ok=True)
            with self._lock:
                self._preparing_jobs.discard(job_id)
                job = self._jobs.get(job_id)
                if job is None:
                    raise
                job["status"] = "cancelled"
                job["progress"]["message"] = "任务已取消"
                job["updated_at"] = _now()
                self._persist(job_id)
                response = self._public(job)
                delete_requested = (
                    job_id in self._delete_requested
                )
            if delete_requested:
                self._remove_job(job_id)
            return response
        except Exception:
            partial_source.unlink(missing_ok=True)
            local_source.unlink(missing_ok=True)
            with self._lock:
                self._preparing_jobs.discard(job_id)
                if job_id in self._jobs:
                    self._delete_requested.add(job_id)
                    self._persist(job_id)
            self._remove_job(job_id)
            raise

    def _copy_source(
        self,
        source: Path,
        destination: Path,
        job_id: str,
    ) -> None:
        with (
            source.open("rb") as source_stream,
            destination.open("wb") as destination_stream,
        ):
            while True:
                self._raise_if_cancelled(job_id)
                chunk = source_stream.read(1024 * 1024)
                if not chunk:
                    break
                destination_stream.write(chunk)

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                job is None
                or job_id in self._delete_requested
            ):
                raise JobNotFoundError(job_id)
            return self._public(job)

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                job is None
                or job_id in self._delete_requested
            ):
                raise JobNotFoundError(job_id)
            if job["status"] in TERMINAL_STATUSES:
                return self._public(job)
            self._cancel_events[job_id].set()
            if job_id in self._preparing_jobs:
                job["status"] = "cancelling"
                job["progress"]["message"] = (
                    "正在停止输入复制"
                )
            elif job["status"] == "queued":
                job["status"] = "cancelled"
                job["progress"]["message"] = "任务已在队列中取消"
            else:
                job["status"] = "cancelling"
                job["progress"]["message"] = "正在安全停止分离任务"
            job["updated_at"] = _now()
            self._persist(job_id)
            return self._public(job)

    def artifact_path(
        self,
        job_id: str,
        artifact_id: str,
    ) -> tuple[Path, dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                job is None
                or job_id in self._delete_requested
            ):
                raise JobNotFoundError(job_id)
            artifact = next(
                (
                    item
                    for item in job["artifacts"]
                    if item["id"] == artifact_id
                ),
                None,
            )
            path = self._artifact_paths.get(
                (job_id, artifact_id)
            )
            if (
                artifact is None
                or path is None
                or not path.is_file()
            ):
                raise ArtifactNotFoundError(artifact_id)
            self._download_leases[job_id] = (
                self._download_leases.get(job_id, 0) + 1
            )
            return path, dict(artifact)

    def release_artifact(self, job_id: str) -> None:
        with self._lock:
            leases = self._download_leases.get(job_id, 0)
            if leases <= 1:
                self._download_leases.pop(job_id, None)
            else:
                self._download_leases[job_id] = leases - 1
            should_delete = (
                leases <= 1
                and job_id in self._delete_requested
            )
        if should_delete:
            self._remove_job(job_id)

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                job_dir = self._job_dir(job_id)
                job_dir.mkdir(parents=True, exist_ok=True)
                tombstone = job_dir / "delete.tombstone"
                partial = tombstone.with_suffix(
                    ".tombstone.partial"
                )
                partial.write_text(_now(), encoding="utf-8")
                os.replace(partial, tombstone)
                return
            self._delete_requested.add(job_id)
            if job["status"] not in TERMINAL_STATUSES:
                self._cancel_events[job_id].set()
                if job_id in self._preparing_jobs:
                    job["status"] = "cancelling"
                    job["progress"]["message"] = (
                        "正在停止输入复制并清理"
                    )
                elif job["status"] == "queued":
                    job["status"] = "cancelled"
                    job["progress"]["message"] = (
                        "任务已在队列中取消并清理"
                    )
                else:
                    job["status"] = "cancelling"
                    job["progress"]["message"] = (
                        "正在安全停止并清理分离任务"
                    )
            job["updated_at"] = _now()
            self._persist(job_id)
            should_defer = (
                job_id in self._preparing_jobs
                or job["status"] not in TERMINAL_STATUSES
                or self._download_leases.get(job_id, 0) > 0
            )
        if not should_defer:
            self._remove_job(job_id)

    def shutdown(self) -> None:
        self._queue.put(None)
        self._worker.join(timeout=5)

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                if job_id is None:
                    return
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            request = self._requests.get(job_id)
            if job is None or request is None:
                return
            if job["status"] == "cancelled":
                return
            job["status"] = "running"
            self._set_progress_locked(
                job_id,
                "decoding",
                0.0,
                "正在解码原始音频",
            )
        job_dir = self.root / job_id
        source_path = Path(str(request.input["audio"]))
        try:
            raw_artifacts = self.handler.separate_file(
                source_path=source_path,
                output_dir=job_dir,
                progress=lambda phase, fraction, message: (
                    self._set_progress(
                        job_id,
                        phase,
                        fraction,
                        message,
                    )
                ),
                should_cancel=lambda: self._is_cancelled(
                    job_id,
                ),
            )
            self._raise_if_cancelled(job_id)
            artifacts = []
            with self._lock:
                cancel_event = self._cancel_events.get(job_id)
                if (
                    cancel_event is None
                    or cancel_event.is_set()
                ):
                    raise SeparationCancelled(
                        "separation cancelled"
                    )
                for raw in raw_artifacts:
                    path = Path(raw.pop("_path"))
                    self._artifact_paths[
                        (job_id, raw["id"])
                    ] = path
                    artifacts.append(raw)
                job = self._jobs[job_id]
                job["status"] = "succeeded"
                job["progress"] = {
                    "phase": "validating",
                    "fraction": 1.0,
                    "message": "分离产物校验完成",
                }
                job["artifacts"] = artifacts
                job["error"] = None
                job["updated_at"] = _now()
                self._persist(job_id)
        except SeparationCancelled:
            self._mark_cancelled(job_id)
            self._cleanup_outputs(job_dir)
        except Exception as exc:
            self._mark_failed(job_id, exc)
            self._cleanup_outputs(job_dir)
        finally:
            self._finalize_deferred_delete(job_id)

    def _set_progress(
        self,
        job_id: str,
        phase: str,
        fraction: float,
        message: str,
    ) -> None:
        with self._lock:
            self._set_progress_locked(
                job_id,
                phase,
                fraction,
                message,
            )

    def _set_progress_locked(
        self,
        job_id: str,
        phase: str,
        fraction: float,
        message: str,
    ) -> None:
        job = self._jobs[job_id]
        if job["status"] in TERMINAL_STATUSES:
            return
        job["progress"] = {
            "phase": phase,
            "fraction": max(0.0, min(1.0, float(fraction))),
            "message": message,
        }
        job["updated_at"] = _now()
        self._persist(job_id)

    def _is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(job_id)
            return event is None or event.is_set()

    def _raise_if_cancelled(self, job_id: str) -> None:
        if self._is_cancelled(job_id):
            raise SeparationCancelled("separation cancelled")

    def _mark_cancelled(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "cancelled"
            job["artifacts"] = []
            job["error"] = None
            job["progress"]["message"] = "任务已取消"
            job["updated_at"] = _now()
            self._persist(job_id)

    def _mark_failed(
        self,
        job_id: str,
        exc: Exception,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "failed"
            job["artifacts"] = []
            job["error"] = {
                "code": "SEPARATION_FAILED",
                "message": str(exc),
                "details": {},
            }
            job["progress"]["message"] = "分离失败"
            job["updated_at"] = _now()
            self._persist(job_id)

    def _cleanup_outputs(self, job_dir: Path) -> None:
        for name in (
            "dialogue.partial.wav",
            "background.partial.wav",
            "dialogue.wav",
            "background.wav",
            "dialogue.accum.f32",
            "dialogue.weights.f32",
            "source.decoded.partial.wav",
            "source.decoded.wav",
        ):
            (job_dir / name).unlink(missing_ok=True)

    def _finalize_deferred_delete(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            should_delete = (
                job_id in self._delete_requested
                and (
                    job is None
                    or job["status"] in TERMINAL_STATUSES
                )
                and self._download_leases.get(job_id, 0) == 0
            )
        if should_delete:
            self._remove_job(job_id)

    def _job_dir(self, job_id: str) -> Path:
        job_dir = (self.root / job_id).resolve()
        if (
            job_dir.parent != self._resolved_root
            or job_dir.name != job_id
        ):
            raise ValueError(f"Unsafe job id: {job_id}")
        return job_dir

    def _remove_job(
        self,
        job_id: str,
        *,
        schedule_retry: bool = True,
    ) -> bool:
        with self._lock:
            if self._download_leases.get(job_id, 0) > 0:
                return False
        job_dir = self._job_dir(job_id)
        try:
            shutil.rmtree(job_dir)
        except FileNotFoundError:
            pass
        except OSError:
            if schedule_retry:
                self._schedule_cleanup_retry(job_id)
            return False
        if job_dir.exists():
            if schedule_retry:
                self._schedule_cleanup_retry(job_id)
            return False
        with self._lock:
            self._jobs.pop(job_id, None)
            self._requests.pop(job_id, None)
            self._cancel_events.pop(job_id, None)
            self._delete_requested.discard(job_id)
            self._preparing_jobs.discard(job_id)
            self._download_leases.pop(job_id, None)
            self._cleanup_retrying.discard(job_id)
            for key in [
                key
                for key in self._artifact_paths
                if key[0] == job_id
            ]:
                self._artifact_paths.pop(key, None)
        return True

    def _schedule_cleanup_retry(self, job_id: str) -> None:
        with self._lock:
            if job_id in self._cleanup_retrying:
                return
            self._cleanup_retrying.add(job_id)

        def retry() -> None:
            try:
                for delay in (0.1, 0.5, 1.0, 2.0, 5.0):
                    threading.Event().wait(delay)
                    with self._lock:
                        if self._download_leases.get(
                            job_id,
                            0,
                        ) > 0:
                            continue
                    if self._remove_job(
                        job_id,
                        schedule_retry=False,
                    ):
                        return
            finally:
                with self._lock:
                    self._cleanup_retrying.discard(job_id)

        threading.Thread(
            target=retry,
            name=f"tiger-dnr-cleanup-{job_id[:8]}",
            daemon=True,
        ).start()

    def _persist(self, job_id: str) -> None:
        job = self._jobs[job_id]
        request = self._requests.get(job_id)
        payload = {
            "job": job,
            "delete_requested": job_id in self._delete_requested,
            "request": (
                request.model_dump(mode="json")
                if request is not None
                else None
            ),
        }
        path = self._job_dir(job_id) / "job.json"
        partial = path.with_suffix(".json.partial")
        partial.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(partial, path)

    def _load_existing_jobs(self) -> None:
        for tombstone in self.root.glob(
            "*/delete.tombstone"
        ):
            job_dir = tombstone.parent.resolve()
            if job_dir.parent != self._resolved_root:
                continue
            try:
                shutil.rmtree(job_dir)
            except OSError:
                continue
        for manifest in self.root.glob("*/job.json"):
            try:
                payload = json.loads(
                    manifest.read_text(encoding="utf-8")
                )
                job = payload["job"]
                request_payload = payload.get("request")
                job_id = str(job["id"])
                job_dir = manifest.parent.resolve()
                if (
                    self._job_dir(job_id) != job_dir
                    or manifest.name != "job.json"
                ):
                    continue
                if payload.get("delete_requested"):
                    try:
                        shutil.rmtree(job_dir)
                    except OSError:
                        self._schedule_cleanup_retry(job_id)
                    continue
                if job["status"] not in TERMINAL_STATUSES:
                    self._cleanup_outputs(manifest.parent)
                    job["status"] = "failed"
                    job["error"] = {
                        "code": "SERVICE_RESTARTED",
                        "message": (
                            "The separation service restarted before "
                            "the job completed"
                        ),
                        "details": {},
                    }
                    job["updated_at"] = _now()
                self._jobs[job_id] = job
                if request_payload is not None:
                    self._requests[job_id] = (
                        GenerateRequest.model_validate(
                            request_payload
                        )
                    )
                self._cancel_events[job_id] = threading.Event()
                for artifact in job.get("artifacts", []):
                    filename = str(artifact["filename"])
                    if (
                        Path(filename).name != filename
                        or Path(filename).is_absolute()
                    ):
                        continue
                    path = (job_dir / filename).resolve()
                    if path.parent != job_dir:
                        continue
                    if path.is_file():
                        self._artifact_paths[
                            (job_id, artifact["id"])
                        ] = path
                self._persist(job_id)
            except (KeyError, OSError, ValueError):
                continue

    @staticmethod
    def _public(job: dict) -> dict:
        return JobResponse.model_validate(job).model_dump(mode="json")
