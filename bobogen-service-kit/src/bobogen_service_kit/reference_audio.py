import base64
import binascii
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple


_DATA_URI_RE = re.compile(r"^data:([^;]*)?(;base64)?,(.*)$", re.IGNORECASE)

_AUDIO_SUFFIX_MAP = {
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/aac": ".aac",
    "audio/x-wav": ".wav",
}


def is_data_uri(s: str) -> bool:
    return s.startswith("data:")


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def get_data_uri_bytes(s: str) -> Tuple[bytes, str]:
    """Decode a base64 data URI. Returns (raw_bytes, file_suffix)."""
    m = _DATA_URI_RE.match(s)
    if not m:
        raise ValueError("Invalid data URI format")

    mime = (m.group(1) or "audio/wav").strip().lower()
    is_base64 = m.group(2) is not None
    payload = m.group(3)

    if not is_base64:
        raise ValueError("Only base64-encoded data URIs are supported")

    suffix = _AUDIO_SUFFIX_MAP.get(mime, ".wav")

    try:
        raw = base64.b64decode(payload, validate=True)
    except binascii.Error as e:
        raise ValueError(f"Invalid base64 encoding: {e}")

    return raw, suffix


async def resolve_reference_audio(ref_audio: Optional[str]) -> Tuple[Optional[str], Optional[Path]]:
    """Resolve reference_audio string that may be a base64 data URI.

    Returns (resolved_path, cleanup_path).
    - If ref_audio is None, returns (None, None).
    - If ref_audio is a base64 data URI, decodes it to a temp file and
      returns (temp_file_path, temp_file_path) for later cleanup.
    - If ref_audio is already a file path, returns (ref_audio, None).

    The caller is responsible for deleting cleanup_path after synthesis.
    """
    if not ref_audio:
        return ref_audio, None

    if not is_data_uri(ref_audio):
        return ref_audio, None

    raw_bytes, suffix = get_data_uri_bytes(ref_audio)
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(raw_bytes)
    tmp.close()
    return tmp.name, Path(tmp.name)
