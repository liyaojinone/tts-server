import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import REPO_ROOT
from app.core.exceptions import GatewayError
from app.services.model_installer import (
    ModelInstallBusyError,
    ModelInstallError,
    ModelInstallManager,
    is_resource_path_ready,
)
from app.services.model_source import (
    ModelSourceConfigError,
    source_profile,
)
from app.services.huggingface_token import HuggingFaceTokenError
from app.services.huggingface_token import requires_huggingface_token


router = APIRouter()
WEB_PAGE = Path(__file__).resolve().parents[1] / "web" / "index.html"
GATEWAY_LOG = REPO_ROOT / "bobogen-gateway" / "logs" / "gateway.log"
INSTALLER_LOG = REPO_ROOT / "bobogen-gateway" / "logs" / "model-installer.log"


# 这是服务端内置目录，和 configs/providers/*-windows.yaml 中的模型一一对应。
# 安装器接入后，这些信息会迁移到版本化安装清单；页面只消费清单结果，
# 不会根据 README 或用户输入猜测启动方式。
MODEL_CATALOG = [
    {
        "id": "cosyvoice2",
        "name": "CosyVoice2",
        "task": "语音合成",
        "version": "CosyVoice2",
        "parameter_size": "0.5B",
        "purpose": "中文语音合成、预置音色和参考音频克隆",
        "weight_size": "约 5.2 GB",
        "disk_estimate": "约 6 GB（含环境和缓存）",
        "service_port": 5101,
        "resource_root": "models/cosyvoice/repo/pretrained_models/CosyVoice2-0.5B",
        "official_repo": "https://github.com/FunAudioLLM/CosyVoice",
        "other_links": [
            {
                "label": "ModelScope 模型",
                "url": "https://www.modelscope.cn/models/iic/CosyVoice2-0.5B",
            }
        ],
        "installation_environment": "services/cosyvoice-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/cosyvoice2.json",
        "required_paths": [
            "models/cosyvoice/repo/pretrained_models/CosyVoice2-0.5B",
        ],
    },
    {
        "id": "f5_tts",
        "name": "F5-TTS",
        "task": "语音合成",
        "version": "v1 Base",
        "parameter_size": "335M",
        "purpose": "参考音频驱动的语音合成和声音克隆",
        "weight_size": "约 1.4 GB",
        "disk_estimate": "官方仓库就绪；启动后由官方原生机制自动下载并缓存权重",
        "service_port": 5102,
        "resource_root": "models/f5-tts/repo",
        "official_repo": "https://github.com/SWivid/F5-TTS",
        "official_revision": "9c614e9657089213efc6a7421b30630be138a3f5",
        "runtime_weight_policy": "upstream_managed",
        "installation_environment": "services/f5tts-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/f5_tts.json",
        "other_links": [
            {
                "label": "Hugging Face 模型",
                "url": "https://huggingface.co/SWivid/F5-TTS",
            }
        ],
        "required_paths": [
            "models/f5-tts/repo",
        ],
    },
    {
        "id": "gpt_sovits_v2pro",
        "name": "GPT-SoVITS V2Pro",
        "task": "语音合成",
        "version": "V2Pro",
        "parameter_size": "133M + 77M",
        "purpose": "参考音频驱动的语音合成、声音克隆和多语言支持",
        "weight_size": "约 3 GB",
        "disk_estimate": "约 3 GB（含环境和缓存）",
        "service_port": 5103,
        "resource_root": "models/gpt-sovits/checkpoints/gpt_sovits_v2pro",
        "installation_environment": "services/gptsovits-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/gpt_sovits_v2pro.json",
        "official_repo": "https://github.com/RVC-Boss/GPT-SoVITS",
        "other_links": [
            {
                "label": "官方预训练资源",
                "url": "https://huggingface.co/XXXXRT/GPT-SoVITS-Pretrained/tree/main/pretrained_models",
            }
        ],
        "required_paths": [
            "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/s1v3.ckpt",
            "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/v2Pro/s2Gv2Pro.pth",
            "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-roberta-wwm-ext-large",
            "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/chinese-hubert-base",
            "models/gpt-sovits/checkpoints/gpt_sovits_v2pro/sv/pretrained_eres2netv2w24s4ep4.ckpt",
            "models/gpt-sovits/repo/GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin",
            "services/gptsovits-service/.venv/ffmpeg",
            "services/gptsovits-service/.venv/nltk_data",
        ],
    },
    {
        "id": "index_tts_2",
        "name": "IndexTTS2",
        "task": "语音合成",
        "version": "IndexTTS2",
        "purpose": "参考音频驱动的语音合成和多维情绪表达",
        "weight_size": "约 5.9 GB",
        "disk_estimate": "约 5.9 GB（含权重）",
        "service_port": 5104,
        "resource_root": "models/index-tts/checkpoints",
        "official_repo": "https://github.com/index-tts/index-tts",
        "installation_environment": "services/index-tts-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/index_tts_2.json",
        "other_links": [
            {
                "label": "Hugging Face 权重",
                "url": "https://huggingface.co/IndexTeam/IndexTTS-2",
            }
        ],
        "required_paths": [
            "models/index-tts/repo",
            "models/index-tts/checkpoints/config.yaml",
            "models/index-tts/checkpoints/gpt.pth",
            "models/index-tts/checkpoints/s2mel.pth",
            "models/index-tts/checkpoints/feat1.pt",
            "models/index-tts/checkpoints/feat2.pt",
            "models/index-tts/checkpoints/wav2vec2bert_stats.pt",
            "models/index-tts/checkpoints/qwen0.6bemo4-merge/model.safetensors",
        ],
    },
    {
        "id": "voxcpm2",
        "name": "VoxCPM2",
        "task": "语音合成",
        "version": "VoxCPM2",
        "parameter_size": "2B",
        "purpose": "文本指令驱动的语音合成、克隆和设计模式",
        "weight_size": "约 5.0 GB",
        "disk_estimate": "需预留约 6 GB",
        "service_port": 5105,
        "resource_root": "models/voxcpm/checkpoints",
        "official_repo": "https://github.com/OpenBMB/VoxCPM",
        "installation_environment": "services/voxcpm-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/voxcpm2.json",
        "other_links": [
            {
                "label": "ModelScope 权重",
                "url": "https://www.modelscope.cn/models/OpenBMB/VoxCPM2",
            }
        ],
        "required_paths": [
            "models/voxcpm/repo",
            "models/voxcpm/checkpoints/config.json",
            "models/voxcpm/checkpoints/model.safetensors",
            "models/voxcpm/checkpoints/audiovae.pth",
            "models/voxcpm/checkpoints/tokenizer.json",
        ],
    },
    {
        "id": "stable_audio_3_small_sfx",
        "name": "Stable Audio 3 Small-SFX",
        "task": "音效生成",
        "version": "Small-SFX",
        "parameter_size": "0.6B",
        "purpose": "根据文字描述生成短音效和声音素材",
        "weight_size": "约 2.3 GB",
        "disk_estimate": "需检测 Hugging Face 缓存",
        "service_port": 5106,
        "resource_root": "models/stable-audio-3/hf-home/hub/models--stabilityai--stable-audio-3-small-sfx",
        "official_repo": "https://github.com/Stability-AI/stable-audio-3",
        "other_links": [
            {
                "label": "Hugging Face 权重",
                "url": "https://huggingface.co/stabilityai/stable-audio-3-small-sfx",
            }
        ],
        "required_paths": [
            "models/stable-audio-3/repo",
            "models/stable-audio-3/hf-home/hub/models--stabilityai--stable-audio-3-small-sfx/snapshots",
        ],
    },
    {
        "id": "stable_audio_3_small_music",
        "name": "Stable Audio 3 Small-Music",
        "task": "音乐生成",
        "version": "Small-Music",
        "parameter_size": "0.6B",
        "purpose": "根据文字描述生成短音乐片段和背景音乐素材",
        "weight_size": "约 2.3 GB",
        "disk_estimate": "需检测 Hugging Face 缓存",
        "service_port": 5108,
        "resource_root": "models/stable-audio-3/hf-home/hub/models--stabilityai--stable-audio-3-small-music",
        "official_repo": "https://github.com/Stability-AI/stable-audio-3",
        "other_links": [
            {
                "label": "Hugging Face 权重",
                "url": "https://huggingface.co/stabilityai/stable-audio-3-small-music",
            }
        ],
        "required_paths": [
            "models/stable-audio-3/repo",
            "models/stable-audio-3/hf-home/hub/models--stabilityai--stable-audio-3-small-music/snapshots",
        ],
    },
    {
        "id": "stable_audio_3_medium",
        "name": "Stable Audio 3 Medium",
        "task": "音乐生成",
        "version": "Medium",
        "parameter_size": "2B",
        "purpose": "根据文字描述生成更长、更复杂的音乐素材",
        "weight_size": "约 9.2 GB",
        "disk_estimate": "需检测 Hugging Face 缓存",
        "service_port": 5107,
        "resource_root": "models/stable-audio-3/hf-home/hub/models--stabilityai--stable-audio-3-medium",
        "official_repo": "https://github.com/Stability-AI/stable-audio-3",
        "other_links": [
            {
                "label": "Hugging Face 权重",
                "url": "https://huggingface.co/stabilityai/stable-audio-3-medium",
            }
        ],
        "required_paths": [
            "models/stable-audio-3/repo",
            "models/stable-audio-3/hf-home/hub/models--stabilityai--stable-audio-3-medium/snapshots",
        ],
    },
    {
        "id": "qwen3_asr_0_6b",
        "name": "Qwen3-ASR 0.6B",
        "task": "语音识别",
        "version": "Qwen3-ASR",
        "parameter_size": "0.6B",
        "purpose": "将音频转成文字，适合普通语音识别任务",
        "weight_size": "约 1.9 GB",
        "disk_estimate": "官方仓库就绪；启动后由官方原生机制自动下载并缓存权重",
        "service_port": 5110,
        "resource_root": "models/qwen3-asr/repo",
        "installation_environment": "services/qwen3-asr-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/qwen3_asr_0_6b.json",
        "official_repo": "https://github.com/QwenLM/Qwen3-ASR",
        "official_revision": "7c6daf77a2421100f5fb066495372c00129d39ff",
        "runtime_weight_policy": "upstream_managed",
        "other_links": [
            {
                "label": "Hugging Face 模型",
                "url": "https://huggingface.co/Qwen/Qwen3-ASR-0.6B",
            }
        ],
        "required_paths": [
            "models/qwen3-asr/repo",
        ],
    },
    {
        "id": "qwen3_asr_1_7b",
        "name": "Qwen3-ASR 1.7B",
        "task": "语音识别",
        "version": "Qwen3-ASR",
        "parameter_size": "1.7B",
        "purpose": "将音频转成文字，较大模型适合更复杂的识别场景",
        "weight_size": "约 4.7 GB",
        "disk_estimate": "官方仓库就绪；启动后由官方原生机制自动下载并缓存权重",
        "service_port": 5111,
        "resource_root": "models/qwen3-asr/repo",
        "installation_environment": "services/qwen3-asr-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/qwen3_asr_1_7b.json",
        "official_repo": "https://github.com/QwenLM/Qwen3-ASR",
        "official_revision": "7c6daf77a2421100f5fb066495372c00129d39ff",
        "runtime_weight_policy": "upstream_managed",
        "other_links": [
            {
                "label": "Hugging Face 权重",
                "url": "https://huggingface.co/Qwen/Qwen3-ASR-1.7B",
            }
        ],
        "required_paths": [
            "models/qwen3-asr/repo",
        ],
    },
    {
        "id": "qwen3_forced_aligner_0_6b",
        "name": "Qwen3 ForcedAligner 0.6B",
        "task": "字幕对齐",
        "version": "ForcedAligner",
        "parameter_size": "0.6B",
        "purpose": "把文字和音频时间轴对齐，生成字词级时间戳",
        "weight_size": "约 1.9 GB",
        "disk_estimate": "官方仓库就绪；启动后由官方原生机制自动下载并缓存权重",
        "service_port": 5112,
        "resource_root": "models/qwen3-asr/repo",
        "installation_environment": "services/qwen3-asr-service/.venv-aligner/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/qwen3_forced_aligner_0_6b.json",
        "official_repo": "https://github.com/QwenLM/Qwen3-ASR",
        "official_revision": "7c6daf77a2421100f5fb066495372c00129d39ff",
        "runtime_weight_policy": "upstream_managed",
        "other_links": [
            {
                "label": "Hugging Face 模型",
                "url": "https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B-hf",
            }
        ],
        "required_paths": [
            "models/qwen3-asr/repo",
        ],
    },
    {
        "id": "campplus_speaker_diarization",
        "name": "CAM++ Speaker Diarization",
        "task": "说话人分离",
        "version": "common",
        "parameter_size": "7.2M",
        "purpose": "识别一段音频里有几个人，以及每个人何时说话",
        "weight_size": "约 400 MB",
        "disk_estimate": "约 400 MB（含 ModelScope 缓存）",
        "service_port": 5113,
        "resource_root": "models/speaker-diarization/modelscope-cache/models/iic--speech_campplus_speaker-diarization_common/snapshots",
        "official_repo": "https://github.com/modelscope/3D-Speaker",
        "installation_environment": "services/speaker-diarization-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/campplus_speaker_diarization.json",
        "other_links": [
            {
                "label": "ModelScope 模型",
                "url": "https://modelscope.cn/models/iic/speech_campplus_speaker-diarization_common",
            }
        ],
        # 新版 ModelScope 使用 HF 风格缓存布局：models/<owner>--<name>/snapshots/<revision>/
        "required_paths": [
            "models/speaker-diarization/modelscope-cache/models/iic--speech_campplus_speaker-diarization_common/snapshots/master/config.yaml",
            "models/speaker-diarization/modelscope-cache/models/iic--speech_campplus_speaker-diarization_common/snapshots/master/onnx",
            "models/speaker-diarization/modelscope-cache/models/damo--speech_campplus_sv_zh-cn_16k-common/snapshots/master/campplus_cn_common.bin",
            "models/speaker-diarization/modelscope-cache/models/damo--speech_campplus-transformer_scl_zh-cn_16k-common/snapshots/master/transformer_backend.pt",
            "models/speaker-diarization/modelscope-cache/models/damo--speech_fsmn_vad_zh-cn-16k-common-pytorch/snapshots/v2.0.2/model.pb",
        ],
    },
    {
        "id": "tiger-dnr",
        "name": "TIGER-DnR",
        "task": "对白/背景分离",
        "version": "DnR",
        "parameter_size": "4.22M",
        "purpose": "把影视混音拆成对白和背景声两个音轨",
        "weight_size": "约 17 MB",
        "disk_estimate": "约 17 MB（含 Hugging Face 缓存）",
        "service_port": 5114,
        "resource_root": "models/tiger/TIGER-DnR",
        "official_repo": "https://github.com/JusperLee/TIGER",
        "installation_environment": "services/tiger-dnr-service/.venv/Scripts/python.exe",
        "installation_marker": "runtime/model-install-state/tiger-dnr.json",
        "other_links": [
            {
                "label": "Hugging Face 权重",
                "url": "https://huggingface.co/JusperLee/TIGER-DnR",
            }
        ],
        "required_paths": [
            "models/tiger/repo",
            "models/tiger/TIGER-DnR/models--JusperLee--TIGER-DnR/snapshots/b7a59560bbca10febbcd46fb01600f868e587f57/config.json",
            "models/tiger/TIGER-DnR/models--JusperLee--TIGER-DnR/snapshots/b7a59560bbca10febbcd46fb01600f868e587f57/model.safetensors",
            "services/tiger-dnr-service/.venv/ffmpeg/ffmpeg.exe",
        ],
    },
]


def _resolve_provider_id(process_manager, model_id: str):
    if process_manager is None:
        return None
    providers = getattr(process_manager, "providers", None)
    if not isinstance(providers, dict):
        return model_id
    if model_id in providers:
        return model_id
    normalized = model_id.replace("-", "_")
    if normalized in providers:
        return normalized
    return None


def _public_model(model: dict) -> dict:
    internal_keys = {
        "required_paths",
        "installation_environment",
        "installation_marker",
    }
    public = {
        key: value
        for key, value in model.items()
        if key not in internal_keys
    }
    profile = source_profile(model["id"])
    public.update(
        {
            "source_platforms": profile["platforms"],
            "source_support": profile["support"],
            "source_note": profile["note"],
            "huggingface_token_required": requires_huggingface_token(model["id"]),
        }
    )
    return public


def _legacy_installation_completed(model_id: str) -> bool:
    """Recognize installs completed before per-model receipts were added."""
    if not INSTALLER_LOG.is_file():
        return False
    completion = f"] [{model_id}] 模型资源已准备完成"
    try:
        return any(completion in line for line in INSTALLER_LOG.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return False


def _detect_model(model: dict, process_manager=None) -> dict:
    required_paths = list(model["required_paths"])
    expected_paths = list(required_paths)
    missing_paths = [
        relative_path
        for relative_path in required_paths
        if not is_resource_path_ready(REPO_ROOT, relative_path)
    ]
    installation_environment = model.get("installation_environment")
    environment_ready = not installation_environment or is_resource_path_ready(
        REPO_ROOT, installation_environment
    )
    if installation_environment:
        expected_paths.append(installation_environment)
        if not environment_ready:
            missing_paths.append(installation_environment)

    installation_marker = model.get("installation_marker")
    if installation_marker:
        expected_paths.append(installation_marker)
        marker_ready = is_resource_path_ready(REPO_ROOT, installation_marker)
        legacy_ready = environment_ready and _legacy_installation_completed(model["id"])
        if not marker_ready and not legacy_ready:
            missing_paths.append(installation_marker)

    # upstream_managed 模型的权重不在安装清单里，必须等官方 warmup 成功、
    # 写入权重标记后才算“已安装”，否则显示未安装。
    if model.get("runtime_weight_policy") == "upstream_managed":
        weights_marker = f"runtime/model-install-state/{model['id']}.weights.json"
        expected_paths.append(weights_marker)
        if not is_resource_path_ready(REPO_ROOT, weights_marker):
            missing_paths.append(weights_marker)

    if not missing_paths:
        status = "ready"
    elif len(missing_paths) == len(expected_paths):
        status = "missing"
    else:
        status = "partial"

    endpoint = (
        os.environ.get(f"{model['id'].upper()}_HF_ENDPOINT")
        or os.environ.get("HF_ENDPOINT")
        or "https://huggingface.co"
    )
    runtime_weight_policy = model.get("runtime_weight_policy", "platform_managed")

    runtime_state = "stopped"
    runtime_message = "服务未启动"

    if process_manager is not None:
        provider_id = _resolve_provider_id(process_manager, model["id"])

        if hasattr(process_manager, "get_process"):
            try:
                proc = process_manager.get_process(model["id"])
                if proc and getattr(proc, "is_running", False):
                    health = getattr(proc, "health_status", None)
                    if isinstance(health, dict):
                        if health.get("ready"):
                            runtime_state = "ready" if runtime_weight_policy == "upstream_managed" else "running"
                            runtime_message = "服务运行中（权重已就绪）"
                        else:
                            if runtime_weight_policy == "upstream_managed":
                                runtime_state = "loading_weights"
                                runtime_message = "服务启动中，正在下载/加载权重..."
                            else:
                                runtime_state = "starting"
                                runtime_message = "服务启动中"
                    else:
                        runtime_state = "running"
                        runtime_message = "服务运行中"
            except Exception:
                pass

        if runtime_state == "stopped" and hasattr(process_manager, "get_state") and provider_id is not None:
            try:
                state_obj = process_manager.get_state(provider_id)
                if state_obj.status == "healthy":
                    runtime_state = "running"
                    runtime_message = "服务运行中"
                elif state_obj.status == "starting":
                    runtime_state = "starting"
                    runtime_message = "服务启动中"
                elif state_obj.status == "failed":
                    runtime_state = "failed"
                    runtime_message = f"服务启动失败: {state_obj.last_error or '未知错误'}"
            except Exception:
                pass

    return {
        **_public_model(model),
        "status": status,
        "missing_paths": missing_paths,
        "configured_endpoint": endpoint,
        "runtime_weight_policy": runtime_weight_policy,
        "runtime_state": runtime_state,
        "process_status": runtime_state,
        "runtime_message": runtime_message,
    }


def _read_log_file(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]


LOGS_DIR = REPO_ROOT / "bobogen-gateway" / "logs"


def _read_service_logs(lines: int) -> str:
    logs = _read_log_file(INSTALLER_LOG, lines)
    return "\n".join(logs) if logs else "暂无模型安装日志。"


@router.get("/", include_in_schema=False)
async def management_page():
    return FileResponse(
        WEB_PAGE,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get(
    "/api/model-services/catalog",
    tags=["06 模型服务管理"],
    summary="查看模型服务目录",
)
async def model_services_catalog():
    return {
        "service": {
            "name": "模型服务",
            "root": str(REPO_ROOT),
            "status": "running",
        },
        "models": [_public_model(model) for model in MODEL_CATALOG],
    }


@router.get(
    "/api/model-services/status",
    tags=["06 模型服务管理"],
    summary="检测模型服务和模型资源",
)
async def model_services_status(request: Request):
    process_manager = getattr(request.app.state, "process_manager", None)
    return {
        "service": {
            "name": "模型服务",
            "root": str(REPO_ROOT),
            "status": "running",
        },
        "models": [_detect_model(model, process_manager=process_manager) for model in MODEL_CATALOG],
    }


@router.get(
    "/api/model-services/logs",
    tags=["06 模型服务管理"],
    summary="查看模型服务控制台日志",
)
async def model_services_logs(lines: int = Query(default=100, ge=1, le=2000)):
    return {
        "lines": lines,
        "content": _read_service_logs(lines),
    }


def _model_manager(request: Request) -> ModelInstallManager:
    return request.app.state.model_install_manager


def _model_source_store(request: Request):
    return request.app.state.model_source_config_store


def _model_source_payload(request: Request) -> dict:
    store = _model_source_store(request)
    return {
        "config": store.get().to_dict(),
        "models": {model["id"]: source_profile(model["id"]) for model in MODEL_CATALOG},
        "restart_required": True,
    }


@router.get(
    "/api/model-source-config",
    tags=["06 模型服务管理"],
    summary="查看模型下载源配置",
)
async def model_source_config(request: Request):
    return _model_source_payload(request)


@router.put(
    "/api/model-source-config",
    tags=["06 模型服务管理"],
    summary="更新模型下载源配置",
)
async def update_model_source_config(request: Request, payload: dict = Body(...)):
    try:
        _model_source_store(request).update(payload)
    except ModelSourceConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _model_source_payload(request)


def _huggingface_token_store(request: Request):
    return request.app.state.huggingface_token_store


def _huggingface_credential_payload(request: Request) -> dict:
    return {"credential": _huggingface_token_store(request).metadata()}


@router.get(
    "/api/model-credentials/huggingface",
    tags=["06 模型服务管理"],
    summary="查看 Hugging Face Token 配置状态",
)
async def huggingface_credential(request: Request):
    return _huggingface_credential_payload(request)


@router.put(
    "/api/model-credentials/huggingface",
    tags=["06 模型服务管理"],
    summary="保存 Hugging Face Token",
)
async def update_huggingface_credential(request: Request, payload: dict = Body(...)):
    try:
        _huggingface_token_store(request).save(payload.get("token"))
    except HuggingFaceTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _huggingface_credential_payload(request)


@router.delete(
    "/api/model-credentials/huggingface",
    tags=["06 模型服务管理"],
    summary="删除 Hugging Face Token",
)
async def delete_huggingface_credential(request: Request):
    _huggingface_token_store(request).delete()
    return _huggingface_credential_payload(request)


def _start_model_job(
    request: Request,
    model_id: str,
    operation: str,
    mirror: str | None = None,
    main_loop: asyncio.AbstractEventLoop | None = None,
) -> dict:
    if requires_huggingface_token(model_id):
        try:
            token = _huggingface_token_store(request).get()
        except HuggingFaceTokenError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not token:
            raise HTTPException(
                status_code=400,
                detail="此模型需要先在管理页保存 Hugging Face Token，并在官方模型页接受使用条款。",
            )
    manager = _model_manager(request)
    try:
        job = manager.start(model_id, operation, mirror=mirror, main_loop=main_loop)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未知模型: {model_id}") from exc
    except ModelInstallBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "job": exc.job},
        ) from exc
    except ModelInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job


@router.post(
    "/api/model-services/{model_id}/download",
    status_code=202,
    tags=["06 模型服务管理"],
    summary="下载模型源码和固定资源",
)
async def download_model(model_id: str, request: Request, mirror: str | None = Query(default=None)):
    return {
        "job": _start_model_job(
            request,
            model_id,
            "download",
            mirror=mirror,
            main_loop=asyncio.get_running_loop(),
        )
    }


@router.post(
    "/api/model-services/{model_id}/repair",
    status_code=202,
    tags=["06 模型服务管理"],
    summary="修复模型缺失资源",
)
async def repair_model(model_id: str, request: Request, mirror: str | None = Query(default=None)):
    return {
        "job": _start_model_job(
            request,
            model_id,
            "repair",
            mirror=mirror,
            main_loop=asyncio.get_running_loop(),
        )
    }


@router.get(
    "/api/model-services/jobs",
    tags=["06 模型服务管理"],
    summary="查看模型资源任务",
)
async def model_service_jobs(request: Request, limit: int = Query(default=20, ge=1, le=20)):
    return {"jobs": _model_manager(request).list(limit)}


@router.get(
    "/api/model-services/jobs/{job_id}",
    tags=["06 模型服务管理"],
    summary="查看模型资源任务状态",
)
async def model_service_job(job_id: str, request: Request):
    job = _model_manager(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"未知任务: {job_id}")
    return {"job": job}


@router.post(
    "/api/model-services/{model_id}/start",
    tags=["06 模型服务管理"],
    summary="启动模型服务",
)
async def start_model_service(model_id: str, request: Request):
    process_manager = getattr(request.app.state, "process_manager", None)
    if process_manager is None:
        raise HTTPException(status_code=500, detail="进程管理器未初始化")
    provider_id = _resolve_provider_id(process_manager, model_id)
    if provider_id is None:
        raise HTTPException(status_code=404, detail=f"未知模型服务: {model_id}")
    try:
        state = await process_manager.start(provider_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"model_id": model_id, "status": state.status, "pid": state.pid}


@router.post(
    "/api/model-services/{model_id}/stop",
    tags=["06 模型服务管理"],
    summary="停止模型服务",
)
async def stop_model_service(model_id: str, request: Request):
    process_manager = getattr(request.app.state, "process_manager", None)
    if process_manager is None:
        raise HTTPException(status_code=500, detail="进程管理器未初始化")
    provider_id = _resolve_provider_id(process_manager, model_id)
    if provider_id is None:
        raise HTTPException(status_code=404, detail=f"未知模型服务: {model_id}")
    try:
        await process_manager.stop(provider_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"model_id": model_id, "status": "stopped"}


@router.post(
    "/api/model-services/{model_id}/warmup",
    tags=["06 模型服务管理"],
    summary="测试调用模型服务（触发官方权重下载与载入）",
)
async def warmup_model_service(model_id: str, request: Request):
    process_manager = getattr(request.app.state, "process_manager", None)
    provider_registry = getattr(request.app.state, "provider_registry", None)
    if process_manager is None or provider_registry is None:
        raise HTTPException(status_code=500, detail="服务管理器未初始化")
    provider_id = _resolve_provider_id(process_manager, model_id)
    if provider_id is None:
        raise HTTPException(status_code=404, detail=f"未知模型服务: {model_id}")

    try:
        await process_manager.ensure_started(provider_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"启动服务失败: {exc}") from exc

    provider = None
    for candidate in [provider_id, model_id, model_id.replace("-", "_"), model_id.replace("_", "-")]:
        try:
            provider = provider_registry.get_provider(candidate)
            if provider:
                break
        except Exception:
            pass
        try:
            provider = provider_registry.get_provider_by_model(candidate)
            if provider:
                break
        except Exception:
            pass

    if provider is None:
        raise HTTPException(status_code=404, detail=f"未找到对应模型提供者: {model_id}")

    base_url = provider.network.base_url.rstrip("/")
    import httpx
    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            resp = await client.post(f"{base_url}/v1/warmup")
            if resp.status_code == 200:
                return {"model_id": model_id, "status": "succeeded", "detail": resp.json()}
            if resp.status_code != 404:
                try:
                    provider_payload = resp.json()
                except (TypeError, ValueError):
                    provider_payload = {}
                provider_error = provider_payload.get("error", {}) if isinstance(provider_payload, dict) else {}
                provider_message = provider_error.get("message") if isinstance(provider_error, dict) else None
                if not provider_message:
                    provider_message = resp.text.strip() or f"Provider returned HTTP {resp.status_code}"
                status_code = resp.status_code if 400 <= resp.status_code < 600 else 502
                raise HTTPException(status_code=status_code, detail=f"测试调用失败: {provider_message}")
        except httpx.RequestError as exc:
            message = str(exc).strip() or type(exc).__name__
            raise HTTPException(status_code=502, detail=f"测试调用失败: {message}") from exc

        try:
            health_path = provider.network.healthcheck_path or "/v1/health"
            resp = await client.get(f"{base_url}{health_path}")
            return {"model_id": model_id, "status": "succeeded", "detail": resp.json() if resp.status_code == 200 else "服务已就绪"}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"测试调用失败: {exc}") from exc
