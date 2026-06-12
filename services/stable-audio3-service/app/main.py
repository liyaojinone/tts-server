import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app.handler import StableAudio3Handler
from local_tts_protocol.models import GenerateRequest


def _error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def create_app(test_mode: bool = False):
    app = FastAPI(title="stable-audio3-service", version="0.1.0")
    handler = StableAudio3Handler(test_mode=test_mode)
    api_key = os.environ.get("LOCAL_TTS_API_KEY")

    async def ensure_authorized(request: Request):
        if not api_key:
            return
        if request.headers.get("Authorization") != f"Bearer {api_key}":
            return _error_response(401, "UNAUTHORIZED", "Missing or invalid bearer token")
        return None

    @app.get("/v1/health")
    async def health(request: Request):
        unauthorized = await ensure_authorized(request)
        if unauthorized is not None:
            return unauthorized
        return handler.health()

    @app.post("/v1/generate")
    async def generate(http_request: Request):
        unauthorized = await ensure_authorized(http_request)
        if unauthorized is not None:
            return unauthorized
        try:
            request = GenerateRequest.model_validate(await http_request.json())
            result = handler.generate(request)
        except ValidationError as exc:
            return _error_response(400, "INVALID_REQUEST", "Request validation failed", {"errors": exc.errors()})
        except ValueError as exc:
            return _error_response(400, "UNSUPPORTED_TASK", str(exc))
        except RuntimeError as exc:
            return _error_response(503, "MODEL_UNAVAILABLE", str(exc))

        return Response(
            content=result["content"],
            media_type=result["content_type"],
            headers=result.get("headers", {}),
        )

    return app
