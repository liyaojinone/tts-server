import json
from pathlib import Path
import re
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import GatewayError
from app.dependencies import get_process_manager, get_provider_registry
from app.schemas.generate import FileInput, GenerateRequest
from app.schemas.generate_catalog import (
    GenerateSchemaValidationError,
    validate_generate_request_schema,
)
from app.schemas.jobs import JobResponse
from app.services.job_store import GatewayJobStore, JobNotFoundError


router = APIRouter()
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_UPLOAD_CHUNK_SIZE = 1024 * 1024
_MAX_JSON_REQUEST_BYTES = 1024 * 1024
_ALLOWED_AUDIO_SUFFIXES = {
    ".aac",
    ".bin",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
    ".wav",
    ".wave",
    ".webm",
    ".wma",
}


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def _gateway_error_response(exc: GatewayError) -> JSONResponse:
    status = exc.status_code or 400
    provider_code = exc.details.get("provider_error_code")
    return _error_response(
        status,
        provider_code or exc.code,
        exc.message,
        exc.details.get("provider_details") or exc.details,
    )


def _store(request: Request) -> GatewayJobStore:
    return request.app.state.job_store


async def _parse_request(http_request: Request) -> tuple[GenerateRequest, dict]:
    content_type = http_request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await http_request.form()
        request_json = str(form.get("request") or "{}")
        uploads = {
            key: value
            for key, value in form.items()
            if hasattr(value, "filename") and hasattr(value, "read")
        }
        return GenerateRequest.model_validate_json(request_json), uploads
    content_length = http_request.headers.get("content-length")
    if (
        content_length is not None
        and int(content_length) > _MAX_JSON_REQUEST_BYTES
    ):
        raise ValueError(
            "JSON async job request is too large; use multipart upload"
        )
    chunks = []
    total_bytes = 0
    async for chunk in http_request.stream():
        total_bytes += len(chunk)
        if total_bytes > _MAX_JSON_REQUEST_BYTES:
            raise ValueError(
                "JSON async job request is too large; "
                "use multipart upload"
            )
        chunks.append(chunk)
    return GenerateRequest.model_validate_json(
        b"".join(chunks)
    ), {}


def _safe_upload_name(field: str, filename: str | None) -> str:
    suffix = Path(
        (filename or "").replace("\\", "/")
    ).suffix.lower()
    if suffix not in _ALLOWED_AUDIO_SUFFIXES:
        suffix = ".bin"
    safe_field = _SAFE_FILENAME.sub("_", field).strip("._") or "upload"
    return f"{safe_field}{suffix}"


async def _stage_file_inputs(
    value,
    uploads: dict,
    input_dir: Path,
):
    async def resolve(item):
        if isinstance(item, FileInput):
            if item.kind == "path":
                return str(item.path)
            if item.kind == "data_uri":
                raise ValueError(
                    "data_uri is not supported for async audio "
                    "separation; use upload or path"
                )

            field = item.field or ""
            upload = uploads.get(field)
            if upload is None:
                raise ValueError(f"upload file field not found: {field}")
            path = input_dir / _safe_upload_name(field, upload.filename)
            with path.open("wb") as destination:
                while True:
                    chunk = await upload.read(_UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    await run_in_threadpool(
                        destination.write,
                        chunk,
                    )
            return str(path)
        if isinstance(item, dict):
            return {
                key: await resolve(child)
                for key, child in item.items()
            }
        if isinstance(item, list):
            return [await resolve(child) for child in item]
        return item

    return await resolve(value)


def _job_response(payload: dict) -> dict:
    return JobResponse.model_validate(payload).model_dump(mode="json")


async def _cleanup_uncertain_provider_job(
    *,
    adapter,
    provider,
    store: GatewayJobStore,
    job_id: str,
) -> bool:
    try:
        await adapter.delete_job(provider, job_id)
    except GatewayError as exc:
        if exc.status_code != 404:
            return False
    await run_in_threadpool(store.discard, job_id)
    return True


async def _cleanup_failed_creation(
    *,
    created: bool,
    submission_attempted: bool,
    adapter,
    provider,
    store: GatewayJobStore,
    job_id: str,
) -> bool:
    if not created:
        return True
    if (
        submission_attempted
        and adapter is not None
        and provider is not None
    ):
        return await _cleanup_uncertain_provider_job(
            adapter=adapter,
            provider=provider,
            store=store,
            job_id=job_id,
        )
    await run_in_threadpool(store.discard, job_id)
    return True


@router.post("/v1/jobs", status_code=202, tags=["02 Generate 新统一接口"])
async def create_job(
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    store = _store(http_request)
    job_id = uuid.uuid4().hex
    created = False
    provider = None
    adapter = None
    submission_attempted = False
    try:
        request, uploads = await _parse_request(http_request)
        provider = registry.get_provider_by_model(request.model)
        tasks = registry.get_model_tasks(provider)
        if request.task != "audio.separate" or request.task not in tasks:
            return _error_response(
                400,
                "UNSUPPORTED_ASYNC_TASK",
                f"Unsupported async task for model: {request.task}",
                {
                    "model": request.model,
                    "task": request.task,
                    "supported_tasks": tasks,
                },
            )
        request = validate_generate_request_schema(request, tasks)
        record = store.create(
            job_id=job_id,
            provider_id=provider.provider_id,
            model=request.model,
            task=request.task,
        )
        created = True
        input_dir = Path(record.job_dir) / "inputs"
        request.input = await _stage_file_inputs(
            request.input,
            uploads,
            input_dir,
        )
        request.parameters = await _stage_file_inputs(
            request.parameters,
            uploads,
            input_dir,
        )
        await manager.ensure_started(provider.provider_id)
        adapter = registry.get_adapter(provider.provider_id)
        submission_attempted = True
        payload = await adapter.create_job(provider, job_id, request)
        response = _job_response(payload)
        expected_identity = {
            "id": job_id,
            "model": request.model,
            "task": request.task,
        }
        mismatches = {
            field: {
                "expected": expected,
                "actual": response[field],
            }
            for field, expected in expected_identity.items()
            if response[field] != expected
        }
        if mismatches:
            raise ValueError(
                "Provider job identity does not match the request: "
                f"{mismatches}"
            )
        return response
    except ValidationError as exc:
        cleaned = await _cleanup_failed_creation(
            created=created,
            submission_attempted=submission_attempted,
            adapter=adapter,
            provider=provider,
            store=store,
            job_id=job_id,
        )
        if submission_attempted:
            details = {"errors": exc.errors()}
            if not cleaned:
                details.update(
                    {
                        "job_id": job_id,
                        "cleanup_pending": True,
                    }
                )
            return _error_response(
                502,
                "INVALID_PROVIDER_RESPONSE",
                "Provider returned an invalid job response",
                details,
            )
        return _error_response(
            400,
            "INVALID_REQUEST",
            "Request validation failed",
            {"errors": exc.errors()},
        )
    except GenerateSchemaValidationError as exc:
        if created:
            await run_in_threadpool(
                store.discard,
                job_id,
            )
        return _error_response(
            400,
            "INVALID_REQUEST",
            str(exc),
            {"errors": exc.errors},
        )
    except GatewayError as exc:
        if created:
            cleanup_needed = (
                submission_attempted
                and adapter is not None
                and provider is not None
                and (exc.status_code or 500) >= 500
            )
            cleaned = (
                await _cleanup_uncertain_provider_job(
                    adapter=adapter,
                    provider=provider,
                    store=store,
                    job_id=job_id,
                )
                if cleanup_needed
                else False
            )
            if not cleanup_needed:
                await run_in_threadpool(
                    store.discard,
                    job_id,
                )
            elif not cleaned:
                details = exc.details.setdefault(
                    "provider_details",
                    {},
                )
                details.update(
                    {
                        "job_id": job_id,
                        "cleanup_pending": True,
                    }
                )
        return _gateway_error_response(exc)
    except OSError as exc:
        cleaned = await _cleanup_failed_creation(
            created=created,
            submission_attempted=submission_attempted,
            adapter=adapter,
            provider=provider,
            store=store,
            job_id=job_id,
        )
        details = {"reason": str(exc)}
        if not cleaned:
            details.update(
                {
                    "job_id": job_id,
                    "cleanup_pending": True,
                }
            )
        return _error_response(
            500,
            "JOB_IO_ERROR",
            "Failed to stage or persist the separation job",
            details,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        cleaned = await _cleanup_failed_creation(
            created=created,
            submission_attempted=submission_attempted,
            adapter=adapter,
            provider=provider,
            store=store,
            job_id=job_id,
        )
        if submission_attempted:
            details = {"reason": str(exc)}
            if not cleaned:
                details.update(
                    {
                        "job_id": job_id,
                        "cleanup_pending": True,
                    }
                )
            return _error_response(
                502,
                "INVALID_PROVIDER_RESPONSE",
                "Provider returned an invalid job response",
                details,
            )
        return _error_response(400, "INVALID_REQUEST", str(exc))


def _resolve_job(
    request: Request,
    registry,
    job_id: str,
):
    try:
        record = _store(request).get(job_id)
    except JobNotFoundError:
        return None, None, _error_response(
            404,
            "JOB_NOT_FOUND",
            f"Job not found: {job_id}",
            {"job_id": job_id},
        )
    try:
        provider = registry.get_provider(record.provider_id)
    except GatewayError as exc:
        return None, None, _gateway_error_response(exc)
    return record, provider, None


@router.get("/v1/jobs/{job_id}", tags=["02 Generate 新统一接口"])
async def get_job(
    job_id: str,
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    _record, provider, error = _resolve_job(
        http_request,
        registry,
        job_id,
    )
    if error is not None:
        return error
    try:
        await manager.ensure_started(provider.provider_id)
        adapter = registry.get_adapter(provider.provider_id)
        return _job_response(await adapter.get_job(provider, job_id))
    except GatewayError as exc:
        return _gateway_error_response(exc)


@router.post(
    "/v1/jobs/{job_id}/cancel",
    tags=["02 Generate 新统一接口"],
)
async def cancel_job(
    job_id: str,
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    _record, provider, error = _resolve_job(
        http_request,
        registry,
        job_id,
    )
    if error is not None:
        return error
    try:
        await manager.ensure_started(provider.provider_id)
        adapter = registry.get_adapter(provider.provider_id)
        return _job_response(
            await adapter.cancel_job(provider, job_id)
        )
    except GatewayError as exc:
        return _gateway_error_response(exc)


@router.get(
    "/v1/jobs/{job_id}/artifacts/{artifact_id}",
    tags=["02 Generate 新统一接口"],
)
async def get_artifact(
    job_id: str,
    artifact_id: str,
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    _record, provider, error = _resolve_job(
        http_request,
        registry,
        job_id,
    )
    if error is not None:
        return error
    try:
        await manager.ensure_started(provider.provider_id)
        adapter = registry.get_adapter(provider.provider_id)
        job = _job_response(await adapter.get_job(provider, job_id))
        if not any(
            item["id"] == artifact_id
            for item in job["artifacts"]
        ):
            return _error_response(
                404,
                "ARTIFACT_NOT_FOUND",
                f"Artifact not found: {artifact_id}",
                {"job_id": job_id, "artifact_id": artifact_id},
            )
        artifact = await adapter.get_artifact(
            provider,
            job_id,
            artifact_id,
        )
    except GatewayError as exc:
        return _gateway_error_response(exc)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{artifact["filename"]}"'
        ),
        "Content-Length": str(artifact["size_bytes"]),
    }
    return StreamingResponse(
        artifact["stream"],
        media_type=artifact["content_type"],
        headers=headers,
    )


@router.delete(
    "/v1/jobs/{job_id}",
    status_code=204,
    tags=["02 Generate 新统一接口"],
)
async def delete_job(
    job_id: str,
    http_request: Request,
    registry=Depends(get_provider_registry),
    manager=Depends(get_process_manager),
):
    store = _store(http_request)
    _record, provider, error = _resolve_job(
        http_request,
        registry,
        job_id,
    )
    if error is not None:
        return error
    try:
        await manager.ensure_started(provider.provider_id)
        adapter = registry.get_adapter(provider.provider_id)
        await adapter.delete_job(provider, job_id)
        await run_in_threadpool(store.delete, job_id)
    except GatewayError as exc:
        if exc.status_code == 404:
            await run_in_threadpool(store.delete, job_id)
            return Response(status_code=204)
        return _gateway_error_response(exc)
    return Response(status_code=204)
