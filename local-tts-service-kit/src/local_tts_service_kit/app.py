from contextlib import asynccontextmanager
import os
import traceback
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from local_tts_protocol.models import CloneRequest, DesignRequest, ErrorResponse, SynthesizeRequest
from local_tts_service_kit.errors import ProtocolError, map_exception
from local_tts_service_kit.reference_audio import resolve_reference_audio


def create_service_app(service_name: str, handler, api_key: Optional[str] = None) -> FastAPI:
    startup_hook = getattr(handler, "startup", None)
    shutdown_hook = getattr(handler, "shutdown", None)
    configured_api_key = api_key or os.environ.get("LOCAL_TTS_API_KEY")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if callable(startup_hook):
            await startup_hook()
        try:
            yield
        finally:
            if callable(shutdown_hook):
                await shutdown_hook()

    app = FastAPI(title=service_name, version="0.1.0", lifespan=lifespan)

    def build_error_response(error: ProtocolError) -> JSONResponse:
        payload = ErrorResponse(
            error={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        ).model_dump()
        return JSONResponse(status_code=error.status_code, content=payload)

    async def ensure_authorized(request: Request):
        if not configured_api_key:
            return
        authorization = request.headers.get("Authorization")
        if authorization != f"Bearer {configured_api_key}":
            raise ProtocolError(401, "UNAUTHORIZED", "Missing or invalid bearer token", {})

    @app.exception_handler(ProtocolError)
    async def protocol_error_handler(request: Request, exc: ProtocolError):
        traceback.print_exc()
        return build_error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return build_error_response(ProtocolError(400, "INVALID_REQUEST", "Request validation failed", {"errors": exc.errors()}))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        traceback.print_exc()
        return build_error_response(map_exception(exc))

    @app.get("/v1/health")
    async def health(request: Request):
        await ensure_authorized(request)
        return await handler.health()

    @app.get("/v1/voices")
    async def list_voices(request: Request, language: Optional[str] = None, page: int = 1, page_size: int = 100):
        await ensure_authorized(request)
        return await handler.list_voices(language=language, page=page, page_size=page_size)

    @app.post("/v1/synthesize")
    async def synthesize(http_request: Request):
        await ensure_authorized(http_request)
        reference_audio = None
        reference_text = None
        _cleanups: list = []
        content_type = http_request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            form = await http_request.form()
            synth_request = SynthesizeRequest.model_validate_json(str(form.get("request") or "{}"))
            reference_audio = form.get("reference_audio")
            reference_text = form.get("reference_text")
            emotion_reference_audio = form.get("emotion_reference_audio")
            if emotion_reference_audio is not None:
                synth_request.parameters.extra["emotion_reference_audio_upload_name"] = getattr(
                    emotion_reference_audio, "filename", None
                )
                synth_request.parameters.extra["_emotion_reference_audio_upload"] = emotion_reference_audio
        else:
            synth_request = SynthesizeRequest.model_validate(await http_request.json())
            # 解析 base64 data URI 为临时文件
            resolved, cleanup = await resolve_reference_audio(synth_request.parameters.reference_audio)
            if resolved:
                synth_request.parameters.reference_audio = resolved
            if cleanup:
                _cleanups.append(cleanup)
            # 同样处理 extra 中的 emotion_reference_audio
            emo = synth_request.parameters.extra.get("emotion_reference_audio")
            if isinstance(emo, str):
                emo_resolved, emo_cleanup = await resolve_reference_audio(emo)
                if emo_resolved:
                    synth_request.parameters.extra["emotion_reference_audio"] = emo_resolved
                if emo_cleanup:
                    _cleanups.append(emo_cleanup)
        try:
            result = await handler.synthesize(
                synth_request,
                reference_audio=reference_audio,
                reference_text=reference_text,
            )
        except Exception as exc:
            traceback.print_exc()
            raise map_exception(exc)
        finally:
            for p in _cleanups:
                if p.exists():
                    p.unlink(missing_ok=True)
        return Response(
            content=result["content"],
            media_type=result["content_type"],
            headers=result.get("headers", {}),
        )

    @app.post("/v1/synthesize/stream")
    async def synthesize_stream(http_request: Request):
        await ensure_authorized(http_request)
        stream_hook = getattr(handler, "stream_synthesize", None)
        if not callable(stream_hook):
            raise ProtocolError(404, "ENDPOINT_NOT_AVAILABLE", "Stream synthesis is not implemented for this service", {})
        synth_request = SynthesizeRequest.model_validate(await http_request.json())
        result = await stream_hook(synth_request)
        return StreamingResponse(
            result["content"],
            media_type=result.get("content_type", "application/octet-stream"),
            headers=result.get("headers", {}),
        )

    @app.post("/v1/clone")
    async def clone(
        request_http: Request,
        audio: UploadFile = File(...),
        text: Optional[str] = Form(default=None),
        name: Optional[str] = Form(default=None),
        language: Optional[str] = Form(default=None),
        emotion: Optional[str] = Form(default=None),
    ):
        await ensure_authorized(request_http)
        clone_hook = getattr(handler, "clone", None)
        if not callable(clone_hook):
            raise ProtocolError(404, "ENDPOINT_NOT_AVAILABLE", "Clone is not implemented for this service", {})
        request = CloneRequest(
            name=name,
            language=language,
            text=text,
            emotion=emotion,
        )
        return await clone_hook(request, audio=audio)

    @app.get("/v1/clone/{task_id}/status")
    async def clone_status(request: Request, task_id: str):
        await ensure_authorized(request)
        status_hook = getattr(handler, "clone_status", None)
        if not callable(status_hook):
            raise ProtocolError(404, "ENDPOINT_NOT_AVAILABLE", "Clone status is not implemented for this service", {})
        return await status_hook(task_id)

    @app.post("/v1/design")
    async def design(request_http: Request):
        await ensure_authorized(request_http)
        design_hook = getattr(handler, "design", None)
        if not callable(design_hook):
            raise ProtocolError(404, "ENDPOINT_NOT_AVAILABLE", "Design is not implemented for this service", {})
        design_request = DesignRequest.model_validate(await request_http.json())
        return await design_hook(design_request)

    return app
