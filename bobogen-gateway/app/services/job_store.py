import json
import os
from pathlib import Path
import shutil
import threading

from app.schemas.jobs import GatewayJobRecord


class JobNotFoundError(LookupError):
    pass


class GatewayJobStore:
    def __init__(self, root: Path | None = None):
        configured_root = os.environ.get("BOBOGEN_JOB_ROOT")
        workspace_root = Path(
            os.environ.get(
                "BOBOGEN_ROOT",
                Path(__file__).resolve().parents[3],
            )
        )
        self.root = (
            Path(root)
            if root is not None
            else Path(configured_root)
            if configured_root
            else workspace_root / "runtime" / "gateway-jobs"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._resolved_root = self.root.resolve()
        self._records: dict[str, GatewayJobRecord] = {}
        self._lock = threading.RLock()
        self._load_records()

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def create(
        self,
        *,
        job_id: str,
        provider_id: str,
        model: str,
        task: str,
    ) -> GatewayJobRecord:
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        (job_dir / "inputs").mkdir()
        record = GatewayJobRecord(
            id=job_id,
            provider_id=provider_id,
            model=model,
            task=task,
            job_dir=str(job_dir),
        )
        with self._lock:
            self._records[job_id] = record
            self._write_record(record)
        return record

    def get(self, job_id: str) -> GatewayJobRecord:
        with self._lock:
            record = self._records.get(job_id)
        if record is None:
            raise JobNotFoundError(job_id)
        return record

    def delete(self, job_id: str) -> None:
        record = self.get(job_id)
        job_dir = self._validated_job_dir(record)
        (job_dir / "gateway.json").unlink(missing_ok=True)
        with self._lock:
            self._records.pop(job_id, None)
        shutil.rmtree(job_dir, ignore_errors=True)

    def discard(self, job_id: str) -> None:
        with self._lock:
            record = self._records.get(job_id)
        if record is not None:
            job_dir = self._validated_job_dir(record)
            (job_dir / "gateway.json").unlink(missing_ok=True)
            with self._lock:
                self._records.pop(job_id, None)
            shutil.rmtree(job_dir, ignore_errors=True)

    def _validated_job_dir(
        self,
        record: GatewayJobRecord,
    ) -> Path:
        job_dir = Path(record.job_dir).resolve()
        if (
            job_dir.parent != self._resolved_root
            or job_dir.name != record.id
        ):
            raise ValueError(
                f"Unsafe gateway job directory: {record.job_dir}"
            )
        return job_dir

    def _write_record(self, record: GatewayJobRecord) -> None:
        path = Path(record.job_dir) / "gateway.json"
        partial = path.with_suffix(".json.partial")
        partial.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(partial, path)

    def _load_records(self) -> None:
        for path in self.root.glob("*/gateway.json"):
            try:
                record = GatewayJobRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            job_dir = path.parent.resolve()
            if (
                record.id != path.parent.name
                or Path(record.job_dir).resolve() != job_dir
                or job_dir.parent != self._resolved_root
            ):
                continue
            self._records[record.id] = record
