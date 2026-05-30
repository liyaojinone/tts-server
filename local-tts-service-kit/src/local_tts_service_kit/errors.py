from json import JSONDecodeError
from typing import Optional

from fastapi import HTTPException


class ProtocolError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def map_exception(exc: Exception) -> ProtocolError:
    if isinstance(exc, ProtocolError):
        return exc
    if isinstance(exc, HTTPException):
        return ProtocolError(exc.status_code, "HTTP_ERROR", str(exc.detail), {})
    if isinstance(exc, ValueError):
        message = str(exc)
        lowered = message.lower()
        if "unknown voice" in lowered or "voice_id" in lowered:
            return ProtocolError(404, "VOICE_NOT_FOUND", message, {})
        if "unsupported format" in lowered:
            return ProtocolError(400, "UNSUPPORTED_FORMAT", message, {})
        if "text too long" in lowered:
            return ProtocolError(400, "TEXT_TOO_LONG", message, {})
        return ProtocolError(400, "INVALID_REQUEST", message, {})
    if isinstance(exc, JSONDecodeError):
        return ProtocolError(400, "INVALID_REQUEST", "Malformed JSON request body", {})
    return ProtocolError(500, "INTERNAL_ERROR", "Internal server error", {})
