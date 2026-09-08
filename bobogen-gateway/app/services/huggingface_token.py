"""Encrypted, project-local storage for a Hugging Face access token."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from threading import RLock
from typing import Protocol


class HuggingFaceTokenError(ValueError):
    """Raised when the local Hugging Face credential cannot be used."""


HUGGINGFACE_GATED_MODEL_IDS = frozenset(
    {
        "stable_audio_3_small_sfx",
        "stable_audio_3_small_music",
        "stable_audio_3_medium",
    }
)


def requires_huggingface_token(model_id: str) -> bool:
    return model_id in HUGGINGFACE_GATED_MODEL_IDS


class TokenProtector(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class WindowsDpapiProtector:
    """Protect bytes for the current Windows user with the native DPAPI."""

    def __init__(self):
        if os.name != "nt":
            raise HuggingFaceTokenError("Hugging Face Token 加密存储目前仅支持 Windows")
        self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    @staticmethod
    def _input_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(data)
        return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

    def _copy_and_free(self, blob: _DataBlob) -> bytes:
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            if blob.pbData:
                self._kernel32.LocalFree(ctypes.cast(blob.pbData, wintypes.HLOCAL))

    def protect(self, plaintext: bytes) -> bytes:
        source, _source_buffer = self._input_blob(plaintext)
        protected = _DataBlob()
        if not self._crypt32.CryptProtectData(
            ctypes.byref(source), "BoboGen Hugging Face Token", None, None, None, 0, ctypes.byref(protected)
        ):
            raise HuggingFaceTokenError(f"无法加密 Hugging Face Token（Windows 错误 {ctypes.get_last_error()}）")
        return self._copy_and_free(protected)

    def unprotect(self, ciphertext: bytes) -> bytes:
        source, _source_buffer = self._input_blob(ciphertext)
        plaintext = _DataBlob()
        if not self._crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(plaintext)
        ):
            raise HuggingFaceTokenError(
                f"无法读取 Hugging Face Token；它可能属于其他 Windows 用户（错误 {ctypes.get_last_error()}）"
            )
        return self._copy_and_free(plaintext)


class HuggingFaceTokenStore:
    """Persist one token without ever exposing it in the regular config JSON."""

    def __init__(self, path: Path, protector: TokenProtector | None = None):
        self.path = Path(path)
        self._protector = protector or WindowsDpapiProtector()
        self._lock = RLock()

    def save(self, token: object) -> None:
        if not isinstance(token, str) or not token.strip():
            raise HuggingFaceTokenError("Token 必须是非空字符串")
        protected = self._protector.protect(token.strip().encode("utf-8"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            temporary.write_bytes(protected)
            temporary.replace(self.path)

    def get(self) -> str | None:
        with self._lock:
            if not self.path.exists():
                return None
            try:
                return self._protector.unprotect(self.path.read_bytes()).decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise HuggingFaceTokenError("无法读取已保存的 Hugging Face Token") from exc

    def delete(self) -> None:
        with self._lock:
            if self.path.exists():
                self.path.unlink()

    def metadata(self) -> dict[str, object]:
        token = self.get()
        return {"configured": token is not None, "token_suffix": token[-4:] if token else None}
