import base64
from pathlib import Path
import tempfile
from typing import Any

from fastapi import UploadFile

from app.schemas.generate import FileInput


def _suffix_from_name(name: str | None) -> str:
    suffix = Path(name or "").suffix
    return suffix or ".bin"


def _write_temp_file(content: bytes, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(content)
        return Path(temp.name)


async def _resolve_file_input(value: FileInput, uploads: dict[str, UploadFile]) -> tuple[str, Path | None]:
    if value.kind == "path":
        return str(value.path), None

    if value.kind == "data_uri":
        header, _, payload = (value.data or "").partition(",")
        if not payload or ";base64" not in header:
            raise ValueError("data_uri file input must be a base64 data URI")
        path = _write_temp_file(base64.b64decode(payload), ".bin")
        return str(path), path

    upload = uploads.get(value.field or "")
    if upload is None:
        raise ValueError(f"upload file field not found: {value.field}")
    path = _write_temp_file(await upload.read(), _suffix_from_name(upload.filename))
    return str(path), path


async def resolve_generation_files(value: Any, uploads: dict[str, UploadFile] | None = None) -> tuple[Any, list[Path]]:
    uploads = uploads or {}
    cleanups: list[Path] = []

    async def resolve(item: Any) -> Any:
        if isinstance(item, FileInput):
            resolved, cleanup = await _resolve_file_input(item, uploads)
            if cleanup is not None:
                cleanups.append(cleanup)
            return resolved
        if isinstance(item, dict):
            return {key: await resolve(child) for key, child in item.items()}
        if isinstance(item, list):
            return [await resolve(child) for child in item]
        return item

    return await resolve(value), cleanups


def cleanup_temp_files(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
