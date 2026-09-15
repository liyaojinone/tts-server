"""Model resource installation for the server-side model management page.

The installer deliberately owns a small, versioned allow-list.  It never accepts
URLs or paths from the browser and it never updates an existing upstream checkout.
An installation operation only fills missing resources from the pinned source and
model repositories in this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile

from app.services.model_source import (
    ModelSourceConfig,
    ModelSourceConfigError,
    ModelSourceConfigStore,
)
from app.services.huggingface_token import HuggingFaceTokenStore, requires_huggingface_token


LOGGER = logging.getLogger(__name__)


class ModelInstallError(RuntimeError):
    """Raised when a model's fixed installation plan cannot be completed."""


class ModelInstallBusyError(RuntimeError):
    """Raised when another model resource task is already running."""

    def __init__(self, job: dict):
        super().__init__("另一个模型资源任务正在执行")
        self.job = job


@dataclass(frozen=True)
class InstallProgress:
    step: str
    message: str


# Every upstream revision used by the installer is written in this manifest.
# Existing repositories are never pulled or replaced by the page.  A future
# service release changes this manifest explicitly.
MODEL_INSTALL_PLANS: dict[str, dict] = {
    "cosyvoice2": {
        "source": {
            "url": "https://github.com/FunAudioLLM/CosyVoice.git",
            "target": "models/cosyvoice/repo",
            "revision": "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc",
        },
        "environment": {
            "venv_dir": "services/cosyvoice-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                # setuptools<81 提供 pkg_resources，供 openai-whisper 的构建使用
                ["{python}", "-m", "pip", "install", "setuptools<81", "wheel"],
                ["{python}", "-m", "pip", "install", "tiktoken"],
                # 先单独装 whisper 并跳过构建隔离，避免官方 requirements 里的
                # openai-whisper 在隔离环境中因缺少 pkg_resources 而构建失败
                [
                    "{python}",
                    "-m",
                    "pip",
                    "install",
                    "openai-whisper==20231117",
                    "--no-build-isolation",
                    "--no-deps",
                ],
                ["{python}", "-m", "pip", "install", "-r", "models/cosyvoice/repo/requirements.txt"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-service-kit"],
                ["{python}", "-m", "pip", "install", "-e", "services/cosyvoice-service"],
            ],
        },
        "installation_marker": "runtime/model-install-state/cosyvoice2.json",
        "resources": [
            {
                "kind": "hf_snapshot_local",
                "repo_id": "FunAudioLLM/CosyVoice2-0.5B",
                "revision": "eec1ae6c79877dbd9379285cf8789c9e0879293d",
                "target": "models/cosyvoice/repo/pretrained_models/CosyVoice2-0.5B",
            }
        ],
    },
    "f5_tts": {
        "source": {
            "url": "https://github.com/SWivid/F5-TTS.git",
            "target": "models/f5-tts/repo",
            "revision": "9c614e9657089213efc6a7421b30630be138a3f5",
        },
        "environment": {
            "venv_dir": "services/f5tts-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                ["{python}", "-m", "pip", "install", "torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"],
                # F5-TTS 推理运行期依赖；不装 gradio/torchcodec/bitsandbytes 等
                # 训练与 CLI 专用包（Windows 上易构建失败），本体用 --no-deps 安装
                [
                    "{python}",
                    "-m",
                    "pip",
                    "install",
                    "transformers",
                    "vocos",
                    "cached_path",
                    "ema_pytorch",
                    "torchdiffeq",
                    "x_transformers",
                    "datasets",
                    "accelerate",
                    "wandb",
                    "pypinyin",
                    "rjieba",
                    "unidecode",
                    "librosa",
                    "soundfile",
                    "pydub",
                    "matplotlib",
                    "numpy",
                    "hydra-core",
                    "omegaconf",
                    "safetensors",
                    "transformers_stream_generator",
                    "tqdm",
                    "huggingface_hub",
                ],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-service-kit"],
                ["{python}", "-m", "pip", "install", "-e", "models/f5-tts/repo", "--no-deps"],
                ["{python}", "-m", "pip", "install", "-e", "services/f5tts-service"],
            ],
        },
        "runtime": {
            "model_id": "f5_tts",
            "hf_repo_id": "SWivid/F5-TTS",
            "cwd": "services/f5tts-service",
            "entrypoint": "services/f5tts-service/start.ps1",
        },
        "installation_marker": "runtime/model-install-state/f5_tts.json",
        "resources": [],
    },
    "gpt_sovits_v2pro": {
        "source": {
            "url": "https://github.com/RVC-Boss/GPT-SoVITS.git",
            "target": "models/gpt-sovits/repo",
            "revision": "d523079fc05d9a8028d6085bffe4a2757c32abb6",
        },
        "environment": {
            "venv_dir": "services/gptsovits-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                # 先装 opencc 的预编译 wheel，规避官方 requirements 中
                # --no-binary=opencc 在 Windows 上触发源码编译
                ["{python}", "-m", "pip", "install", "opencc"],
                ["{python}", "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cu128"],
                ["{python}", "-m", "pip", "install", "torchcodec"],
                ["{python}", "-m", "pip", "install", "onnxruntime-gpu"],
                ["{python}", "-m", "pip", "install", "-r", "models/gpt-sovits/repo/extra-req.txt", "--no-deps"],
                ["{python}", "-m", "pip", "install", "-r", "models/gpt-sovits/repo/requirements.txt"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-service-kit"],
                ["{python}", "-m", "pip", "install", "-e", "services/gptsovits-service"],
            ],
        },
        "installation_marker": "runtime/model-install-state/gpt_sovits_v2pro.json",
        "resources": [
            {
                "kind": "ffmpeg_shared_zip",
                "url": "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/assets/561416198",
                "sha256": "0968af68d5b2009c62bf726d6a9530c234bd3e158102823a8e7ee7f799257460",
                "cache_path": "runtime/model-download-cache/ffmpeg-win64-lgpl-shared-20260913.zip",
                "target": "services/gptsovits-service/.venv/ffmpeg",
                "package_glob": "ffmpeg-*-win64-lgpl-shared",
            },
            {
                "kind": "url_zip_extract",
                "url": "https://www.modelscope.cn/models/XXXXRT/GPT-SoVITS-Pretrained/resolve/master/nltk_data.zip",
                "cache_path": "runtime/model-download-cache/gpt-sovits-nltk_data.zip",
                "target": "services/gptsovits-service/.venv",
                "marker": "nltk_data/corpora/cmudict.zip",
            },
            {
                "kind": "hf_files",
                "repo_id": "XXXXRT/GPT-SoVITS-Pretrained",
                "revision": "0c47645e02a7bc3688d7b263b0042c81e3cd82cd",
                "files": [
                    {
                        "source": "pretrained_models/s1v3.ckpt",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/s1v3.ckpt",
                    },
                    {
                        "source": "pretrained_models/v2Pro/s2Gv2Pro.pth",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/v2Pro/s2Gv2Pro.pth",
                    },
                    {
                        "source": "pretrained_models/chinese-roberta-wwm-ext-large/config.json",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-roberta-wwm-ext-large/config.json",
                    },
                    {
                        "source": "pretrained_models/chinese-roberta-wwm-ext-large/pytorch_model.bin",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-roberta-wwm-ext-large/pytorch_model.bin",
                    },
                    {
                        "source": "pretrained_models/chinese-roberta-wwm-ext-large/tokenizer.json",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-roberta-wwm-ext-large/tokenizer.json",
                    },
                    {
                        "source": "pretrained_models/chinese-hubert-base/config.json",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-hubert-base/config.json",
                    },
                    {
                        "source": "pretrained_models/chinese-hubert-base/preprocessor_config.json",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-hubert-base/preprocessor_config.json",
                    },
                    {
                        "source": "pretrained_models/chinese-hubert-base/pytorch_model.bin",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-hubert-base/pytorch_model.bin",
                    },
                    {
                        "source": "pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt",
                        "target": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/sv/pretrained_eres2netv2w24s4ep4.ckpt",
                    },
                    {
                        "source": "pretrained_models/fast_langdetect/lid.176.bin",
                        "target": "models/gpt-sovits/repo/GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin",
                    },
                ],
            }
        ],
    },
    "index_tts_2": {
        "source": {
            "url": "https://github.com/index-tts/index-tts.git",
            "target": "models/index-tts/repo",
            "revision": "830f6f8f94a51fea23ab1d639027a86200075a4e",
        },
        "environment": {
            "venv_dir": "services/index-tts-service/.venv",
            "setup_commands": [
                ["uv", "pip", "install", "--python", "{python}", "python-multipart"],
            ],
        },
        "installation_marker": "runtime/model-install-state/index_tts_2.json",
        "resources": [
            {
                "kind": "hf_snapshot_local",
                "repo_id": "IndexTeam/IndexTTS-2",
                "revision": "740dcaff396282ffb241903d150ac011cd4b1ede",
                "target": "models/index-tts/checkpoints",
            }
        ],
    },
    "voxcpm2": {
        "source": {
            "url": "https://github.com/OpenBMB/VoxCPM.git",
            "target": "models/voxcpm/repo",
            "revision": "616d3d3e630a9c96c2853250eef91b0f39dcd5fa",
        },
        "environment": {
            "venv_dir": "services/voxcpm-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                ["{python}", "-m", "pip", "install", "torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"],
                # VoxCPM 推理运行期依赖；不装 gradio/torchcodec/datasets/funasr 等
                # 训练与前端专用包（Windows 易构建失败），本体用 --no-deps 安装
                [
                    "{python}",
                    "-m",
                    "pip",
                    "install",
                    "transformers",
                    "einops",
                    "inflect",
                    "librosa",
                    "modelscope",
                    "numpy",
                    "pydantic",
                    "regex",
                    "safetensors",
                    "soundfile",
                    "tqdm",
                    "huggingface_hub",
                    "wetext",
                ],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-service-kit"],
                ["{python}", "-m", "pip", "install", "-e", "models/voxcpm/repo", "--no-deps"],
                ["{python}", "-m", "pip", "install", "-e", "services/voxcpm-service"],
            ],
        },
        "installation_marker": "runtime/model-install-state/voxcpm2.json",
        "resources": [
            {
                "kind": "hf_snapshot_local",
                "repo_id": "openbmb/VoxCPM2",
                "revision": "e8b928065859f2869644c1e2881cbd21f888c659",
                "target": "models/voxcpm/checkpoints",
            }
        ],
    },
    "stable_audio_3_small_sfx": {
        "source": {
            "url": "https://github.com/Stability-AI/stable-audio-3.git",
            "target": "models/stable-audio-3/repo",
            "revision": "bccf5b7b75734c95a3049bb43bdbc7b3070a31bc",
        },
        "resources": [
            {
                "kind": "hf_snapshot_cache",
                "repo_id": "stabilityai/stable-audio-3-small-sfx",
                "revision": "ae12755283df9d62ca39a9b050a39a0b607b8c20",
                "cache_dir": "models/stable-audio-3/hf-home/hub",
            }
        ],
    },
    "stable_audio_3_small_music": {
        "source": {
            "url": "https://github.com/Stability-AI/stable-audio-3.git",
            "target": "models/stable-audio-3/repo",
            "revision": "bccf5b7b75734c95a3049bb43bdbc7b3070a31bc",
        },
        "resources": [
            {
                "kind": "hf_snapshot_cache",
                "repo_id": "stabilityai/stable-audio-3-small-music",
                "revision": "0fef1392cd842149a2b6d445e181c97608faac06",
                "cache_dir": "models/stable-audio-3/hf-home/hub",
            }
        ],
    },
    "stable_audio_3_medium": {
        "source": {
            "url": "https://github.com/Stability-AI/stable-audio-3.git",
            "target": "models/stable-audio-3/repo",
            "revision": "bccf5b7b75734c95a3049bb43bdbc7b3070a31bc",
        },
        "resources": [
            {
                "kind": "hf_snapshot_cache",
                "repo_id": "stabilityai/stable-audio-3-medium",
                "revision": "27b5a21b791b1b033d193a9e1e3ce78493f102f9",
                "cache_dir": "models/stable-audio-3/hf-home/hub",
            }
        ],
    },
    "qwen3_asr_0_6b": {
        "source": {
            "url": "https://github.com/QwenLM/Qwen3-ASR.git",
            "target": "models/qwen3-asr/repo",
            "revision": "7c6daf77a2421100f5fb066495372c00129d39ff",
        },
        "environment": {
            "venv_dir": "services/qwen3-asr-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                ["{python}", "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "models/qwen3-asr/repo"],
                ["{python}", "-m", "pip", "install", "-e", "services/qwen3-asr-service"],
            ],
        },
        "runtime": {
            "model_id": "qwen3_asr_0_6b",
            "hf_repo_id": "Qwen/Qwen3-ASR-0.6B",
            "cwd": "models/qwen3-asr/repo",
            "entrypoint": "services/qwen3-asr-service/start.ps1",
        },
        "installation_marker": "runtime/model-install-state/qwen3_asr_0_6b.json",
        "resources": [],
    },
    "qwen3_asr_1_7b": {
        "source": {
            "url": "https://github.com/QwenLM/Qwen3-ASR.git",
            "target": "models/qwen3-asr/repo",
            "revision": "7c6daf77a2421100f5fb066495372c00129d39ff",
        },
        "environment": {
            "venv_dir": "services/qwen3-asr-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                ["{python}", "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "models/qwen3-asr/repo"],
                ["{python}", "-m", "pip", "install", "-e", "services/qwen3-asr-service"],
            ],
        },
        "runtime": {
            "model_id": "qwen3_asr_1_7b",
            "hf_repo_id": "Qwen/Qwen3-ASR-1.7B",
            "cwd": "models/qwen3-asr/repo",
            "entrypoint": "services/qwen3-asr-service/start.ps1",
        },
        "installation_marker": "runtime/model-install-state/qwen3_asr_1_7b.json",
        "resources": [],
    },
    "qwen3_forced_aligner_0_6b": {
        "source": {
            "url": "https://github.com/QwenLM/Qwen3-ASR.git",
            "target": "models/qwen3-asr/repo",
            "revision": "7c6daf77a2421100f5fb066495372c00129d39ff",
        },
        "environment": {
            "venv_dir": "services/qwen3-asr-service/.venv-aligner",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                ["{python}", "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "models/qwen3-asr/repo", "--no-deps"],
                ["{python}", "-m", "pip", "install", "-e", "services/qwen3-asr-service"],
                ["{python}", "-m", "pip", "install", "accelerate", "librosa", "soundfile", "nagisa", "soynlp"],
                ["{python}", "-m", "pip", "install", "git+https://github.com/huggingface/transformers"],
            ],
        },
        "runtime": {
            "model_id": "qwen3_forced_aligner_0_6b",
            "hf_repo_id": "Qwen/Qwen3-ForcedAligner-0.6B-hf",
            "cwd": "models/qwen3-asr/repo",
            "entrypoint": "services/qwen3-asr-service/start.ps1",
        },
        "installation_marker": "runtime/model-install-state/qwen3_forced_aligner_0_6b.json",
        "resources": [],
    },
    "campplus_speaker_diarization": {
        "environment": {
            "venv_dir": "services/speaker-diarization-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                ["{python}", "-m", "pip", "install", "torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "services/speaker-diarization-service"],
            ],
        },
        "installation_marker": "runtime/model-install-state/campplus_speaker_diarization.json",
        "resources": [
            # 官方流水线由 configuration.json 引用以下 4 个包（说话人分离、
            # 声纹、变化点检测、VAD），全部预置到同一个 ModelScope 缓存，
            # 运行期直接命中本地缓存；revision 与运行期请求保持一致。
            {
                "kind": "modelscope_cache",
                "model_id": "iic/speech_campplus_speaker-diarization_common",
                "revision": "master",
                "cache_dir": "models/speaker-diarization/modelscope-cache",
            },
            {
                "kind": "modelscope_cache",
                "model_id": "damo/speech_campplus_sv_zh-cn_16k-common",
                "revision": "master",
                "cache_dir": "models/speaker-diarization/modelscope-cache",
            },
            {
                "kind": "modelscope_cache",
                "model_id": "damo/speech_campplus-transformer_scl_zh-cn_16k-common",
                "revision": "master",
                "cache_dir": "models/speaker-diarization/modelscope-cache",
            },
            {
                "kind": "modelscope_cache",
                "model_id": "damo/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                "revision": "v2.0.2",
                "cache_dir": "models/speaker-diarization/modelscope-cache",
            },
        ],
    },
    "tiger-dnr": {
        "source": {
            "url": "https://github.com/JusperLee/TIGER.git",
            "target": "models/tiger/repo",
            "revision": "9f18d4a10a7137e1ce8052cfb62215179f1287b6",
        },
        "environment": {
            "venv_dir": "services/tiger-dnr-service/.venv",
            "setup_commands": [
                ["{python}", "-m", "pip", "install", "-U", "pip"],
                ["{python}", "-m", "pip", "install", "torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"],
                # 官方 requirements.txt 含 triton/wandb/speechbrain 等训练或
                # Windows 不可用包；这里按服务声明的推理依赖安装最小集合
                [
                    "{python}",
                    "-m",
                    "pip",
                    "install",
                    "huggingface-hub",
                    "librosa",
                    "lightning-utilities",
                    "numpy",
                    "packaging",
                    "pytorch-lightning",
                    "rich",
                    "safetensors",
                    "scipy",
                    "soundfile",
                    "torch-complex",
                    "torchmetrics",
                    "typeguard",
                ],
                ["{python}", "-m", "pip", "install", "-e", "bobogen-protocol"],
                ["{python}", "-m", "pip", "install", "-e", "services/tiger-dnr-service"],
            ],
        },
        "installation_marker": "runtime/model-install-state/tiger-dnr.json",
        "resources": [
            {
                # 服务解码音频时调用 ffmpeg 命令行，必须随目录自带一份，
                # 否则整目录拷贝到没有系统 ffmpeg 的机器上无法运行
                "kind": "ffmpeg_shared_zip",
                "url": "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/assets/561416198",
                "sha256": "0968af68d5b2009c62bf726d6a9530c234bd3e158102823a8e7ee7f799257460",
                "cache_path": "runtime/model-download-cache/ffmpeg-win64-lgpl-shared-20260913.zip",
                "target": "services/tiger-dnr-service/.venv/ffmpeg",
                "package_glob": "ffmpeg-*-win64-lgpl-shared",
            },
            {
                "kind": "hf_snapshot_cache",
                "repo_id": "JusperLee/TIGER-DnR",
                "revision": "b7a59560bbca10febbcd46fb01600f868e587f57",
                "cache_dir": "models/tiger/TIGER-DnR",
            }
        ],
    },
}


ProgressCallback = Callable[[InstallProgress], None]


def is_resource_path_ready(repo_root: Path, relative_path: str) -> bool:
    """Return whether a manifest path contains usable resource data.

    A directory created by an interrupted download is not a valid resource by
    itself.  Files must be non-empty and directories must contain at least one
    entry.  The manifest is internal, but keeping the root check here prevents
    a future catalog edit from accidentally inspecting outside the service.
    """

    root = repo_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"安装清单路径越过服务根目录: {relative_path}") from exc

    if candidate.is_file():
        return candidate.stat().st_size > 0
    if candidate.is_dir():
        visible_entries = [entry for entry in candidate.iterdir() if not entry.name.startswith(".")]
        for entry in visible_entries:
            if entry.is_file() and entry.stat().st_size > 0:
                return True
            if entry.is_dir() and any(
                nested for nested in entry.iterdir() if not nested.name.startswith(".")
            ):
                return True
        return False
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelInstaller:
    """Execute one allow-listed model resource plan inside ``repo_root``."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        self._source_config = ModelSourceConfig()
        self._hf_token: str | None = None

    def run(
        self,
        model: dict,
        operation: str,
        progress: ProgressCallback,
        mirror: str | None = None,
        source_config: ModelSourceConfig | Mapping[str, object] | None = None,
        hf_token: str | None = None,
    ) -> None:
        if operation not in {"download", "repair"}:
            raise ModelInstallError(f"不支持的资源操作: {operation}")

        self._source_config = self._resolve_source_config(mirror, source_config)

        model_id = model["id"]
        self._hf_token = hf_token if requires_huggingface_token(model_id) else None
        plan = MODEL_INSTALL_PLANS.get(model_id)
        if plan is None:
            raise ModelInstallError(f"模型 {model_id} 没有固定安装清单")

        source = plan.get("source")
        if source:
            progress(InstallProgress("source", "下载官方仓库"))
            self._ensure_source(source, progress)

        env_config = plan.get("environment")
        env_ready = True
        python_path = None
        if env_config:
            venv_dir = self._safe_path(env_config["venv_dir"])
            python_path = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            env_ready = python_path.is_file()

        missing_paths = [
            path
            for path in model.get("required_paths", [])
            if not is_resource_path_ready(self.repo_root, path)
        ]
        marker_path = plan.get("installation_marker")
        install_complete = marker_path is None or is_resource_path_ready(self.repo_root, marker_path)
        if not missing_paths and env_ready and install_complete:
            if operation == "repair" and env_config:
                # 修复：资源已就绪，只重跑环境依赖，补齐缺失的运行期依赖（不重下资源）
                progress(InstallProgress("environment", "修复：重新安装依赖"))
                python_path = self._ensure_environment(env_config, progress)
                self._install_dependencies(env_config, python_path, progress, mirror=mirror)
                self._write_installation_marker(model_id, plan)
                progress(InstallProgress("done", "安装完成"))
                return
            self._write_installation_marker(model_id, plan)
            progress(InstallProgress("verify", "资源已经完整，无需重复下载；固定版本保持不变"))
            return
        if not missing_paths and env_ready and not install_complete:
            progress(InstallProgress("environment", "检测到未完成的安装，继续准备依赖"))

        if env_config:
            progress(InstallProgress("environment", "准备 Python 环境"))
            python_path = self._ensure_environment(env_config, progress)

            progress(InstallProgress("dependencies", "安装官方依赖"))
            self._install_dependencies(env_config, python_path, progress, mirror=mirror)

        resources = plan.get("resources", [])
        for index, resource in enumerate(resources, start=1):
            progress(InstallProgress("download", f"处理官方资源 {index}/{len(resources)}"))
            self._download_resource(resource, progress)

        missing_paths = [
            path
            for path in model.get("required_paths", [])
            if not is_resource_path_ready(self.repo_root, path)
        ]
        if missing_paths:
            formatted = "、".join(missing_paths[:5])
            suffix = " …" if len(missing_paths) > 5 else ""
            raise ModelInstallError(f"安装完成后仍缺少: {formatted}{suffix}")

        self._write_installation_marker(model_id, plan)
        progress(InstallProgress("done", "安装完成"))

    def _write_installation_marker(self, model_id: str, plan: dict) -> None:
        relative_path = plan.get("installation_marker")
        if not relative_path:
            return

        marker = self._safe_path(relative_path)
        marker.parent.mkdir(parents=True, exist_ok=True)
        source = plan.get("source") or {}
        environment = plan.get("environment") or {}
        payload = {
            "model_id": model_id,
            "source": {
                "target": source.get("target"),
                "revision": source.get("revision"),
            },
            "environment": {"venv_dir": environment.get("venv_dir")},
            "installed_at": _utc_now(),
        }
        partial = marker.with_name(f".{marker.name}.part")
        try:
            partial.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            partial.replace(marker)
        except OSError as exc:
            partial.unlink(missing_ok=True)
            raise ModelInstallError(f"无法写入模型安装记录: {marker}") from exc

    def weights_marker_path(self, model_id: str) -> str:
        return f"runtime/model-install-state/{model_id}.weights.json"

    def write_weights_marker(self, model_id: str) -> None:
        """记录“官方权重已成功预取/加载”。

        只有 warmup 成功（权重确实存在且可用）后才会调用，因此该文件是
        upstream_managed 模型“已安装”判定的必要依据。
        """
        marker = self._safe_path(self.weights_marker_path(model_id))
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_id": model_id,
            "weights_prefetched": True,
            "prefetched_at": _utc_now(),
        }
        partial = marker.with_name(f".{marker.name}.part")
        try:
            partial.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            partial.replace(marker)
        except OSError as exc:
            partial.unlink(missing_ok=True)
            raise ModelInstallError(f"无法写入权重预取记录: {marker}") from exc

    @staticmethod
    def _resolve_source_config(
        mirror: str | None,
        source_config: ModelSourceConfig | Mapping[str, object] | None,
    ) -> ModelSourceConfig:
        if source_config is not None:
            if isinstance(source_config, ModelSourceConfig):
                return source_config
            try:
                return ModelSourceConfig.from_mapping(source_config)
            except ModelSourceConfigError as exc:
                raise ModelInstallError(str(exc)) from exc
        if mirror is None:
            return ModelSourceConfig()
        try:
            return ModelSourceConfig.from_mapping(
                {
                    "enabled": bool(mirror),
                    "hf_endpoint": mirror or None,
                }
            )
        except ModelSourceConfigError as exc:
            raise ModelInstallError(str(exc)) from exc

    def _ensure_environment(self, env_config: dict, progress: ProgressCallback) -> Path:
        venv_dir = self._safe_path(env_config["venv_dir"])
        python_exe = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python_exe.is_file():
            progress(InstallProgress("environment", f"创建 Python 虚拟环境: {venv_dir}"))
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
            self._run_command([sys.executable, "-m", "venv", str(venv_dir)], self.repo_root, progress)
        if not python_exe.is_file():
            raise ModelInstallError(f"虚拟环境创建后未找到 Python 可执行文件: {python_exe}")
        return python_exe

    def _install_dependencies(
        self,
        env_config: dict,
        python_exe: Path,
        progress: ProgressCallback,
        mirror: str | None = None,
    ) -> None:
        setup_commands = env_config.get("setup_commands", [])
        env = os.environ.copy()
        if mirror:
            env["HF_ENDPOINT"] = mirror
        elif self._source_config.enabled:
            if self._source_config.hf_endpoint:
                env["HF_ENDPOINT"] = self._source_config.hf_endpoint
            if self._source_config.modelscope_domain:
                env["MODELSCOPE_DOMAIN"] = self._source_config.modelscope_domain
        for cmd in setup_commands:
            resolved_cmd = []
            for arg in cmd:
                if arg == "{python}":
                    resolved_cmd.append(str(python_exe))
                elif arg.startswith(("models/", "services/", "bobogen-")):
                    resolved_cmd.append(str(self._safe_path(arg)))
                else:
                    resolved_cmd.append(arg)
            progress(InstallProgress("dependencies", f"执行依赖命令: {' '.join(resolved_cmd)}"))
            self._run_command(resolved_cmd, self.repo_root, progress, env=env)

    def _safe_path(self, relative_path: str) -> Path:
        candidate = (self.repo_root / relative_path).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError as exc:
            raise ModelInstallError(f"安装清单路径越过服务根目录: {relative_path}") from exc
        return candidate

    def _ensure_source(self, source: dict, progress: ProgressCallback) -> None:
        target = self._safe_path(source["target"])
        revision = source["revision"]
        if (target / ".git").is_dir():
            current = self._git_revision(target)
            if current != revision:
                raise ModelInstallError(
                    f"源码已存在但版本不匹配: {target} 当前 {current or '未知'}，清单要求 {revision}。"
                    "不会自动覆盖，请使用对应的服务版本清单处理。"
                )
            self._init_submodules(target, progress)
            progress(InstallProgress("source", f"官方源码已存在并匹配固定版本 {revision[:8]}"))
            return

        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise ModelInstallError(f"源码目录已存在但不是受管仓库，拒绝覆盖: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        staging_parent = Path(tempfile.mkdtemp(prefix=f".{target.name}.install-", dir=target.parent))
        staging_target = staging_parent / "repo"
        progress(InstallProgress("source", f"克隆官方仓库并切换到固定版本 {revision[:8]}"))
        try:
            self._run_command(["git", "clone", source["url"], str(staging_target)], self.repo_root, progress)
            self._run_command(["git", "-C", str(staging_target), "checkout", "--detach", revision], self.repo_root, progress)
            self._init_submodules(staging_target, progress)
            if target.exists():
                # The target was verified empty above.  Leave a non-empty path
                # untouched if something changed it while cloning.
                if not target.is_dir() or any(target.iterdir()):
                    raise ModelInstallError(f"源码目录在安装期间发生变化，拒绝覆盖: {target}")
                target.rmdir()
            staging_target.replace(target)
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)

    def _init_submodules(self, target: Path, progress: ProgressCallback) -> None:
        if not (target / ".gitmodules").is_file():
            return
        progress(InstallProgress("source", "初始化官方子模块"))
        self._run_command(
            ["git", "-C", str(target), "submodule", "update", "--init", "--recursive"],
            self.repo_root,
            progress,
        )

    def _git_revision(self, target: Path) -> str | None:
        completed = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout.strip() or None

    def _download_resource(self, resource: dict, progress: ProgressCallback) -> None:
        kind = resource["kind"]
        if kind == "hf_snapshot_local":
            self._download_hf_snapshot_local(resource, progress)
        elif kind == "hf_snapshot_cache":
            self._download_hf_snapshot_cache(resource, progress)
        elif kind == "hf_files":
            self._download_hf_files(resource, progress)
        elif kind == "modelscope_cache":
            self._download_modelscope_cache(resource, progress)
        elif kind == "ffmpeg_shared_zip":
            self._download_ffmpeg_shared_zip(resource, progress)
        elif kind == "url_zip_extract":
            self._download_url_zip_extract(resource, progress)
        else:
            raise ModelInstallError(f"安装清单包含未知资源类型: {kind}")

    def _download_url_zip_extract(self, resource: dict, progress: ProgressCallback) -> None:
        target = self._safe_path(resource["target"])
        marker = (target / resource["marker"]).resolve()
        try:
            marker.relative_to(target.resolve())
        except ValueError as exc:
            raise ModelInstallError(f"压缩包资源标记越过目标目录: {resource['marker']}") from exc
        if marker.exists() and (not marker.is_file() or marker.stat().st_size > 0):
            progress(InstallProgress("weights", f"官方压缩资源已存在，跳过: {marker}"))
            return

        cache_path = self._safe_path(resource["cache_path"])
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = cache_path.with_name(f".{cache_path.name}.part")
        cache_invalid = cache_path.is_file() and cache_path.stat().st_size > 0 and not zipfile.is_zipfile(cache_path)
        if cache_invalid:
            # 缓存被截断/损坏（例如拷贝中断）时删除后重新下载，避免永久卡在解压失败
            progress(InstallProgress("weights", f"压缩资源缓存损坏，重新下载: {cache_path.name}"))
            cache_path.unlink(missing_ok=True)
        if not cache_path.is_file() or cache_path.stat().st_size == 0:
            progress(InstallProgress("weights", f"下载官方压缩资源: {resource['url']}"))
            from urllib.request import urlopen

            try:
                with urlopen(resource["url"], timeout=120) as response, partial_path.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
            except Exception as exc:
                partial_path.unlink(missing_ok=True)
                raise ModelInstallError(f"下载官方压缩资源失败: {resource['url']}: {exc}") from exc
            partial_path.replace(cache_path)

        target.mkdir(parents=True, exist_ok=True)
        progress(InstallProgress("weights", f"解压官方资源到: {target}"))
        try:
            with zipfile.ZipFile(cache_path) as archive:
                target_root = target.resolve()
                for member in archive.infolist():
                    member_path = (target / member.filename).resolve()
                    try:
                        member_path.relative_to(target_root)
                    except ValueError as exc:
                        raise ModelInstallError(f"压缩包条目越过目标目录: {member.filename}") from exc
                archive.extractall(target)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ModelInstallError(f"解压官方压缩资源失败: {cache_path}: {exc}") from exc
        if not marker.exists() or (marker.is_file() and marker.stat().st_size == 0):
            raise ModelInstallError(f"官方压缩资源解压后缺少预期内容: {marker}")

    def _download_ffmpeg_shared_zip(self, resource: dict, progress: ProgressCallback) -> None:
        target = self._safe_path(resource["target"])
        required_files = ("ffmpeg.exe", "ffprobe.exe")
        if all((target / filename).is_file() for filename in required_files) and any(target.glob("avcodec-*.dll")):
            progress(InstallProgress("weights", f"FFmpeg shared runtime 已存在，跳过: {target}"))
            return

        cache_path = self._safe_path(resource["cache_path"])
        expected_sha256 = resource["sha256"].lower()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not cache_path.is_file() or self._sha256(cache_path) != expected_sha256:
            partial_path = cache_path.with_name(f".{cache_path.name}.part")
            progress(InstallProgress("weights", "下载并校验 FFmpeg Windows shared runtime"))
            from urllib.request import Request, urlopen

            try:
                request = Request(
                    resource["url"],
                    headers={
                        "Accept": "application/octet-stream",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
                with urlopen(request, timeout=120) as response, partial_path.open("wb") as output:
                    shutil.copyfileobj(response, output)
            except Exception as exc:
                partial_path.unlink(missing_ok=True)
                raise ModelInstallError(f"下载 FFmpeg shared runtime 失败: {resource['url']}: {exc}") from exc
            if self._sha256(partial_path) != expected_sha256:
                partial_path.unlink(missing_ok=True)
                raise ModelInstallError("FFmpeg shared runtime SHA-256 校验失败")
            partial_path.replace(cache_path)

        staging_dir = Path(tempfile.mkdtemp(prefix=".ffmpeg.install-", dir=target.parent))
        try:
            with zipfile.ZipFile(cache_path) as archive:
                archive.extractall(staging_dir)
            package_root = next(staging_dir.glob(resource["package_glob"]), None)
            if package_root is None:
                raise ModelInstallError("FFmpeg 压缩包不包含预期的 Windows shared runtime")
            bin_dir = package_root / "bin"
            if not all((bin_dir / filename).is_file() for filename in required_files) or not any(bin_dir.glob("avcodec-*.dll")):
                raise ModelInstallError("FFmpeg shared runtime 缺少命令行程序或 avcodec DLL")
            if target.exists():
                shutil.rmtree(target)
            bin_dir.replace(target)
            progress(InstallProgress("weights", f"FFmpeg shared runtime 已安装: {target}"))
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _hf_module(self):
        try:
            from huggingface_hub import hf_hub_download, snapshot_download
        except ImportError as exc:
            raise ModelInstallError(
                "当前模型需要 Hugging Face 下载工具，但模型服务环境中没有 huggingface_hub。"
                "请先按 BoboGenServer 的安装流程准备内部服务环境。"
            ) from exc
        return hf_hub_download, snapshot_download

    def _hf_source_kwargs(self) -> dict[str, str]:
        kwargs: dict[str, str] = {}
        if self._source_config.enabled and self._source_config.hf_endpoint:
            kwargs["endpoint"] = self._source_config.hf_endpoint
        if self._hf_token:
            kwargs["token"] = self._hf_token
        return kwargs

    def _download_hf_snapshot_local(self, resource: dict, progress: ProgressCallback) -> None:
        _, snapshot_download = self._hf_module()
        target = self._safe_path(resource["target"])
        target.mkdir(parents=True, exist_ok=True)
        progress(InstallProgress("weights", f"从 Hugging Face 下载 {resource['repo_id']} 到受管目录"))
        kwargs = {
            "repo_id": resource["repo_id"],
            "local_dir": str(target),
        }
        if resource.get("revision"):
            kwargs["revision"] = resource["revision"]
        kwargs.update(self._hf_source_kwargs())
        snapshot_download(**kwargs)

    def _download_hf_snapshot_cache(self, resource: dict, progress: ProgressCallback) -> None:
        _, snapshot_download = self._hf_module()
        cache_dir = self._safe_path(resource["cache_dir"])
        cache_dir.mkdir(parents=True, exist_ok=True)
        progress(InstallProgress("weights", f"写入 Hugging Face 缓存 {resource['repo_id']}"))
        kwargs = {
            "repo_id": resource["repo_id"],
            "cache_dir": str(cache_dir),
        }
        if resource.get("revision"):
            kwargs["revision"] = resource["revision"]
        kwargs.update(self._hf_source_kwargs())
        snapshot_download(**kwargs)

    def _download_hf_files(self, resource: dict, progress: ProgressCallback) -> None:
        hf_hub_download, _ = self._hf_module()
        cache_dir = self._safe_path("runtime/model-download-cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        files = resource["files"]
        for index, item in enumerate(files, start=1):
            target = self._safe_path(item["target"])
            if is_resource_path_ready(self.repo_root, item["target"]):
                progress(InstallProgress("weights", f"文件已存在，跳过 {index}/{len(files)}: {target.name}"))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            progress(InstallProgress("weights", f"下载文件 {index}/{len(files)}: {item['source']}"))
            download_kwargs = {
                "repo_id": resource["repo_id"],
                "filename": item["source"],
                "cache_dir": str(cache_dir),
            }
            if resource.get("revision"):
                download_kwargs["revision"] = resource["revision"]
            download_kwargs.update(self._hf_source_kwargs())
            cached_path = Path(hf_hub_download(**download_kwargs))
            partial_path = target.with_name(f".{target.name}.part")
            shutil.copyfile(cached_path, partial_path)
            partial_path.replace(target)

    def _download_modelscope_cache(self, resource: dict, progress: ProgressCallback) -> None:
        try:
            from modelscope import snapshot_download
        except ImportError as exc:
            raise ModelInstallError(
                "CAM++ 需要 ModelScope 下载工具；当前内部 Python 环境没有 modelscope。"
                "请先安装 speaker-diarization-service 的专属环境后再下载。"
            ) from exc
        cache_dir = self._safe_path(resource["cache_dir"])
        cache_dir.mkdir(parents=True, exist_ok=True)
        progress(InstallProgress("weights", f"写入 ModelScope 缓存 {resource['model_id']}"))
        kwargs = {
            "revision": resource.get("revision"),
            "cache_dir": str(cache_dir),
        }
        if self._source_config.enabled and self._source_config.modelscope_domain:
            # ModelScope's SDK reads MODELSCOPE_DOMAIN when resolving its
            # endpoint; unlike huggingface_hub it does not expose an endpoint
            # keyword in the supported versions.
            previous_domain = os.environ.get("MODELSCOPE_DOMAIN")
            os.environ["MODELSCOPE_DOMAIN"] = self._source_config.modelscope_domain
            try:
                local_path = Path(snapshot_download(resource["model_id"], **kwargs))
            finally:
                if previous_domain is None:
                    os.environ.pop("MODELSCOPE_DOMAIN", None)
                else:
                    os.environ["MODELSCOPE_DOMAIN"] = previous_domain
        else:
            local_path = Path(snapshot_download(resource["model_id"], **kwargs))
        # 不同 ModelScope 版本的缓存布局不同（旧版 models/<owner>/<name>，
        # 新版 models/<owner>--<name>/snapshots/<revision>），因此直接校验
        # 下载返回的本地快照目录，避免把某个版本的布局写死在清单里
        if not local_path.is_dir() or not any(local_path.iterdir()):
            raise ModelInstallError(f"ModelScope 下载后目录为空: {resource['model_id']}")

    def _run_command(
        self,
        args: list[str],
        cwd: Path,
        progress: ProgressCallback,
        env: dict[str, str] | None = None,
    ) -> None:
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise ModelInstallError(f"无法执行安装命令 {args[0]}: {exc}") from exc

        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip()
            if line:
                progress(InstallProgress("command", line))
        return_code = process.wait()
        if return_code != 0:
            raise ModelInstallError(f"安装命令失败（退出码 {return_code}）: {' '.join(args)}")


class ModelInstallManager:
    """Serialize model resource jobs and expose JSON-safe job snapshots."""

    def __init__(
        self,
        repo_root: Path,
        catalog: Iterable[dict],
        log_path: Path | None = None,
        source_config_store: ModelSourceConfigStore | None = None,
        huggingface_token_store: HuggingFaceTokenStore | None = None,
        prefetch: Callable[[str], Awaitable[None]] | None = None,
    ):
        self._catalog = {model["id"]: model for model in catalog}
        self._installer = ModelInstaller(repo_root)
        self._log_path = log_path
        self._source_config_store = source_config_store
        self._huggingface_token_store = huggingface_token_store
        self._prefetch = prefetch
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._order: list[str] = []
        self._active_job_id: str | None = None

    def start(
        self,
        model_id: str,
        operation: str,
        mirror: str | None = None,
        source_config: ModelSourceConfig | Mapping[str, object] | None = None,
        main_loop: asyncio.AbstractEventLoop | None = None,
    ) -> dict:
        if operation not in {"download", "repair"}:
            raise ModelInstallError(f"不支持的资源操作: {operation}")
        if model_id not in self._catalog:
            raise KeyError(model_id)

        if mirror is not None:
            source_config = ModelInstaller._resolve_source_config(mirror, None)
        elif source_config is None and self._source_config_store is not None:
            source_config = self._source_config_store.get()
        elif source_config is None:
            source_config = ModelSourceConfig()
        elif not isinstance(source_config, ModelSourceConfig):
            source_config = ModelInstaller._resolve_source_config(None, source_config)

        hf_token = None
        if self._huggingface_token_store is not None and requires_huggingface_token(model_id):
            hf_token = self._huggingface_token_store.get()

        with self._lock:
            if self._active_job_id:
                active = self._jobs[self._active_job_id]
                raise ModelInstallBusyError(self._snapshot(active))

            job_id = f"model-{uuid.uuid4().hex[:12]}"
            now = _utc_now()
            job = {
                "id": job_id,
                "model_id": model_id,
                "operation": operation,
                "mirror": mirror,
                "source_config": source_config.to_dict(),
                "state": "queued",
                "step": "queued",
                "message": "已排队，等待开始",
                "logs": [],
                "created_at": now,
                "started_at": None,
                "finished_at": None,
                "error": None,
            }
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._active_job_id = job_id
            self._loop = main_loop
            self._trim_jobs()

        thread = threading.Thread(target=self._run_job, args=(job_id, hf_token), daemon=True)
        thread.start()
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._snapshot(job) if job else None

    def list(self, limit: int = 20) -> list[dict]:
        with self._lock:
            ids = list(reversed(self._order[-limit:]))
            return [self._snapshot(self._jobs[job_id]) for job_id in ids]

    def active_for(self, model_id: str) -> dict | None:
        with self._lock:
            if not self._active_job_id:
                return None
            job = self._jobs[self._active_job_id]
            if job["model_id"] != model_id:
                return None
            return self._snapshot(job)

    def _run_job(self, job_id: str, hf_token: str | None = None) -> None:
        self._update(job_id, state="running", step="check", started_at=_utc_now(), message="开始处理模型资源")

        def progress(event: InstallProgress) -> None:
            self._update(job_id, state="running", step=event.step, message=event.message, append_log=True)

        try:
            with self._lock:
                model_id = self._jobs[job_id]["model_id"]
                operation = self._jobs[job_id]["operation"]
                mirror = self._jobs[job_id].get("mirror")
                source_config = self._jobs[job_id].get("source_config")
                model = self._catalog[model_id]
            self._installer.run(
                model,
                operation,
                progress,
                mirror=mirror,
                source_config=source_config,
                hf_token=hf_token,
            )
            if model.get("runtime_weight_policy") == "upstream_managed":
                self._prefetch_official_weights(job_id, model)
        except Exception as exc:  # keep the concrete error visible to the UI
            LOGGER.exception("模型资源任务失败: %s", job_id)
            self._update(
                job_id,
                state="failed",
                step="failed",
                message=str(exc),
                error=str(exc),
                finished_at=_utc_now(),
                append_log=True,
            )
        else:
            self._update(
                job_id,
                state="succeeded",
                step="done",
                message="模型资源已准备完成",
                finished_at=_utc_now(),
                append_log=True,
            )
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None
                self._loop = None

    def _prefetch_official_weights(self, job_id: str, model: dict) -> None:
        """对 upstream_managed 模型，安装完成后立即预取官方权重。

        权重由官方运行时在首次加载时下载；这里在安装任务内主动触发一次
        warmup，让“下载”真的把权重拉下来，并让任务状态如实反映耗时。
        只有 warmup 成功后才写入权重标记；失败则不写，状态回落为未安装。
        """
        if self._prefetch is None or self._loop is None:
            raise ModelInstallError("缺少权重预取环境，无法确认模型权重是否可用")
        self._update(
            job_id,
            state="running",
            step="weights",
            message="正在预取官方权重，首次会下载并加载…",
            append_log=True,
        )
        future = asyncio.run_coroutine_threadsafe(self._prefetch(model["id"]), self._loop)
        future.result()
        self._installer.write_weights_marker(model["id"])

    def _update(self, job_id: str, append_log: bool = False, **values) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(values)
            if append_log:
                line = f"[{_utc_now()}] [{job['model_id']}] {job['message']}"
                job["logs"].append(line)
                self._append_log(line)

    def _append_log(self, line: str) -> None:
        if self._log_path is None:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _trim_jobs(self) -> None:
        while len(self._order) > 20:
            old_id = self._order.pop(0)
            self._jobs.pop(old_id, None)

    @staticmethod
    def _snapshot(job: dict) -> dict:
        return json.loads(json.dumps(job, ensure_ascii=False))
