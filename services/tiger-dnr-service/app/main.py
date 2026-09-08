from contextlib import asynccontextmanager
import os
from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.responses import (
    JSONResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from bobogen_protocol.models import GenerateRequest

from app.handler import TigerDNRHandler
from app.job_manager import (
    ArtifactNotFoundError,
    JobAlreadyExistsError,
    JobNotFoundError,
    TigerDNRJobManager,
)


_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class CreateJobEnvelope(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    job_id: str
    request: GenerateRequest


def _error(
    status: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def create_app(test_mode: bool | None = None) -> FastAPI:
    if test_mode is None:
        test_mode = (
            os.environ.get("TIGER_DNR_TEST_MODE", "")
            .strip()
            .lower()
            in {"1", "true", "yes"}
        )
    handler = TigerDNRHandler(test_mode=test_mode)
    job_root = Path(
        os.environ.get(
            "TIGER_DNR_JOB_ROOT",
            "data/jobs",
        )
    )
    manager = TigerDNRJobManager(
        handler,
        root=job_root,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(
        title="TIGER-DnR Separation Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.handler = handler
    app.state.job_manager = manager

    @app.get("/v1/health")
    async def health():
        return handler.health()

    @app.post("/v1/warmup")
    async def warmup():
        try:
            return await run_in_threadpool(handler.warmup)
        except Exception as exc:
            return _error(500, "WARMUP_FAILED", str(exc))

    @app.post("/v1/jobs", status_code=202)
    async def create_job(envelope: CreateJobEnvelope):
        if not _SAFE_JOB_ID.fullmatch(envelope.job_id):
            return _error(
                400,
                "INVALID_JOB_ID",
                "job_id must contain only letters, numbers, '-' or '_'",
            )
        try:
            return await run_in_threadpool(
                manager.create,
                envelope.job_id,
                envelope.request,
            )
        except JobAlreadyExistsError:
            return _error(
                409,
                "JOB_ALREADY_EXISTS",
                f"Job already exists: {envelope.job_id}",
            )
        except ValueError as exc:
            code = (
                "UNSUPPORTED_TASK"
                if "task" in str(exc).lower()
                else "INVALID_REQUEST"
            )
            return _error(400, code, str(exc))

    @app.get("/v1/jobs/{job_id}")
    async def get_job(job_id: str):
        try:
            return manager.get(job_id)
        except JobNotFoundError:
            return _error(
                404,
                "JOB_NOT_FOUND",
                f"Job not found: {job_id}",
            )

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        try:
            return manager.cancel(job_id)
        except JobNotFoundError:
            return _error(
                404,
                "JOB_NOT_FOUND",
                f"Job not found: {job_id}",
            )

    @app.get(
        "/v1/jobs/{job_id}/artifacts/{artifact_id}"
    )
    async def get_artifact(
        job_id: str,
        artifact_id: str,
    ):
        try:
            path, artifact = manager.artifact_path(
                job_id,
                artifact_id,
            )
        except JobNotFoundError:
            return _error(
                404,
                "JOB_NOT_FOUND",
                f"Job not found: {job_id}",
            )
        except ArtifactNotFoundError:
            return _error(
                404,
                "ARTIFACT_NOT_FOUND",
                f"Artifact not found: {artifact_id}",
            )
        def stream_artifact():
            try:
                with path.open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        yield chunk
            finally:
                manager.release_artifact(job_id)

        return StreamingResponse(
            stream_artifact(),
            media_type=artifact["content_type"],
            headers={
                "Content-Disposition": (
                    "attachment; filename="
                    f'"{artifact["filename"]}"'
                ),
                "Content-Length": str(
                    artifact["size_bytes"]
                ),
            },
        )

    @app.delete(
        "/v1/jobs/{job_id}",
        status_code=204,
    )
    async def delete_job(job_id: str):
        try:
            await run_in_threadpool(
                manager.delete,
                job_id,
            )
        except JobNotFoundError:
            return _error(
                404,
                "JOB_NOT_FOUND",
                f"Job not found: {job_id}",
            )
        return Response(status_code=204)

    return app
