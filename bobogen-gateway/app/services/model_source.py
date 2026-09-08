"""Project-local model download source configuration.

The configuration in this module is deliberately process-scoped.  The gateway
never writes source variables to the user's machine-wide environment and never
changes model IDs, cache locations, or upstream repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from threading import RLock
from typing import Mapping
from urllib.parse import urlsplit


DEFAULT_HF_ENDPOINT = "https://huggingface.co"
DEFAULT_MODELSCOPE_DOMAIN = "www.modelscope.cn"


# This is a source-capability manifest, not a second model download manifest.
# It records which client families are used by the currently supported model
# services so that one UI switch can produce the right child-process env.
MODEL_SOURCE_PROFILES: dict[str, dict] = {
    "cosyvoice2": {
        "platforms": ["modelscope", "huggingface"],
        "support": "mixed",
        "note": "运行时主要使用 ModelScope；当前安装清单还包含 Hugging Face 资源。",
    },
    "f5_tts": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "主模型和 vocoder 通过 Hugging Face Hub 客户端获取。",
    },
    "gpt_sovits_v2pro": {
        "platforms": ["huggingface", "modelscope", "raw_url"],
        "support": "partial",
        "note": "同时存在 HF、ModelScope、固定 raw URL，且上游有硬编码 endpoint。",
    },
    "index_tts_2": {
        "platforms": ["huggingface", "modelscope"],
        "support": "mixed",
        "note": "主模型及多个运行时依赖分布在 Hugging Face 和 ModelScope。",
    },
    "voxcpm2": {
        "platforms": ["huggingface", "modelscope"],
        "support": "conditional",
        "note": "主模型使用 HF，可选降噪器使用 ModelScope；当前适配器优先只读本地文件。",
    },
    "stable_audio_3_small_sfx": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "Stable Audio 3 Small-SFX 通过 Hugging Face Hub 获取模型文件。",
    },
    "stable_audio_3_small_music": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "Stable Audio 3 Small-Music 通过 Hugging Face Hub 获取模型文件。",
    },
    "stable_audio_3_medium": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "Stable Audio 3 Medium 通过 Hugging Face Hub 获取模型文件。",
    },
    "qwen3_asr_0_6b": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "Qwen3-ASR 0.6B 使用 Transformers/Hugging Face Hub。",
    },
    "qwen3_asr_1_7b": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "Qwen3-ASR 1.7B 使用 Transformers/Hugging Face Hub。",
    },
    "qwen3_forced_aligner_0_6b": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "ForcedAligner 使用 Transformers/Hugging Face Hub。",
    },
    "campplus_speaker_diarization": {
        "platforms": ["modelscope"],
        "support": "full",
        "note": "CAM++ 通过 ModelScope pipeline 获取模型。",
    },
    "tiger-dnr": {
        "platforms": ["huggingface"],
        "support": "full",
        "note": "TIGER-DnR 基于 Hugging Face Hub mixin 获取权重。",
    },
}


class ModelSourceConfigError(ValueError):
    """Raised when the project-local source configuration is invalid."""


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ModelSourceConfigError(f"{field} 必须是字符串或 null")
    value = value.strip()
    return value or None


def normalize_hf_endpoint(value: object) -> str | None:
    endpoint = _optional_text(value, "hf_endpoint")
    if endpoint is None:
        return None
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ModelSourceConfigError("hf_endpoint 必须是带 http:// 或 https:// 的完整地址")
    if parsed.query or parsed.fragment:
        raise ModelSourceConfigError("hf_endpoint 不应包含 query 或 fragment")
    return endpoint.rstrip("/")


def normalize_modelscope_domain(value: object) -> str | None:
    domain = _optional_text(value, "modelscope_domain")
    if domain is None:
        return None

    # ModelScope's environment variable is a host/domain value in the
    # installed SDK.  Accept a pasted https:// URL for usability, then store
    # the host only so the child process receives the expected form.
    if "://" in domain:
        parsed = urlsplit(domain)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ModelSourceConfigError("modelscope_domain 必须是域名或 http(s) 地址")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ModelSourceConfigError("modelscope_domain 不应包含路径、query 或 fragment")
        domain = parsed.netloc

    if any(char.isspace() for char in domain) or "/" in domain or "?" in domain or "#" in domain:
        raise ModelSourceConfigError("modelscope_domain 只能填写域名（例如 www.modelscope.cn）")
    if not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", domain):
        raise ModelSourceConfigError("modelscope_domain 不是有效的域名")
    return domain.rstrip(".")


@dataclass(frozen=True)
class ModelSourceConfig:
    """The user-visible source switch and its optional endpoints."""

    enabled: bool = False
    hf_endpoint: str | None = None
    modelscope_domain: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ModelSourceConfig":
        enabled = payload.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ModelSourceConfigError("enabled 必须是布尔值")
        config = cls(
            enabled=enabled,
            hf_endpoint=normalize_hf_endpoint(payload.get("hf_endpoint")),
            modelscope_domain=normalize_modelscope_domain(payload.get("modelscope_domain")),
        )
        if config.enabled and not config.hf_endpoint and not config.modelscope_domain:
            raise ModelSourceConfigError("启用镜像时至少需要配置一个 Hugging Face 或 ModelScope 地址")
        return config

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "hf_endpoint": self.hf_endpoint,
            "modelscope_domain": self.modelscope_domain,
        }

    def env_for(self, model_id: str) -> dict[str, str]:
        """Return only source variables applicable to one model process."""

        if not self.enabled:
            return {}
        profile = MODEL_SOURCE_PROFILES.get(model_id, {})
        platforms = set(profile.get("platforms", []))
        env: dict[str, str] = {}
        if "huggingface" in platforms and self.hf_endpoint:
            env["HF_ENDPOINT"] = self.hf_endpoint
            # The Qwen launcher already understands this compatibility name;
            # setting both avoids an inherited stale value taking precedence.
            if model_id.startswith("qwen3_"):
                env["QWEN3_ASR_HF_ENDPOINT"] = self.hf_endpoint
        if "modelscope" in platforms and self.modelscope_domain:
            env["MODELSCOPE_DOMAIN"] = self.modelscope_domain
        return env


class ModelSourceConfigStore:
    """Load and atomically persist the source config under the project root."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = RLock()
        self._config = self._load()

    def _load(self) -> ModelSourceConfig:
        if not self.path.exists():
            return ModelSourceConfig()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelSourceConfigError(f"无法读取模型源配置: {self.path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ModelSourceConfigError("模型源配置必须是 JSON 对象")
        return ModelSourceConfig.from_mapping(payload)

    def get(self) -> ModelSourceConfig:
        with self._lock:
            return self._config

    def update(self, payload: Mapping[str, object]) -> ModelSourceConfig:
        with self._lock:
            merged = self._config.to_dict()
            merged.update(payload)
            config = ModelSourceConfig.from_mapping(merged)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            temporary.write_text(
                json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
            self._config = config
            return config


def source_profile(model_id: str) -> dict[str, object]:
    """Return a JSON-safe copy for catalog/status responses."""

    profile = MODEL_SOURCE_PROFILES.get(
        model_id,
        {"platforms": [], "support": "unknown", "note": "尚未登记下载客户端。"},
    )
    return {
        "platforms": list(profile["platforms"]),
        "support": profile["support"],
        "note": profile["note"],
    }
