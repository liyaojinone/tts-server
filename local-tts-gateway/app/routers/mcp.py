"""MCP Server for Local TTS Gateway — stdio + SSE 双模式"""
import base64
import httpx
from mcp.server.fastmcp import FastMCP

# Gateway 注入的共享对象
_registry = None
_manager = None
_gateway_base = "http://127.0.0.1:6006"


def init(registry, manager, gateway_base="http://127.0.0.1:6006"):
    global _registry, _manager, _gateway_base
    _registry = registry
    _manager = manager
    _gateway_base = gateway_base


mcp = FastMCP(
    "local-tts",
    instructions="语音合成、音色注册、引擎管理。reference_audio / emotion_reference_audio 支持 base64 data URI。",  # noqa: E501
)


@mcp.tool()
async def tts_synthesize(
    text: str,
    voice_id: str = "index-default",
    provider_id: str = "local_index_tts",
    language: str = "zh",
    speed: float = 1.0,
    reference_audio: str | None = None,
    emotion_reference_audio: str | None = None,
    emo_alpha: float = 1.0,
):
    """语音合成。返回 base64 编码的 WAV 音频。"""
    provider = _registry.get_provider(provider_id)

    body: dict = {
        "text": text,
        "voice_id": voice_id,
        "language": language,
        "parameters": {
            "speed": speed,
            "reference_audio": reference_audio,
            "extra": {
                "emotion_reference_audio": emotion_reference_audio,
                "emo_alpha": emo_alpha,
            },
        },
        "output": {"format": "wav"},
    }

    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
        resp = await client.post(f"{provider.network.base_url}/v1/synthesize", json=body)
        resp.raise_for_status()

    return {
        "audio_base64": base64.b64encode(resp.content).decode("ascii"),
        "content_type": resp.headers.get("content-type", "audio/wav"),
        "duration_seconds": float(d) if (d := resp.headers.get("x-audio-duration")) else None,
        "sample_rate": int(s) if (s := resp.headers.get("x-sample-rate")) else None,
    }


@mcp.tool()
async def tts_clone_voice(
    audio_base64: str,
    name: str,
    text: str = "",
    language: str = "zh",
    emotion: str = "",
    provider_id: str = "local_index_tts",
):
    """注册新音色。上传参考音频（base64），返回 voice_id。"""
    provider = _registry.get_provider(provider_id)

    audio_bytes = base64.b64decode(audio_base64)
    files = {"audio": ("reference.wav", audio_bytes, "audio/wav")}
    data = {"name": name, "text": text, "language": language, "emotion": emotion}

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        resp = await client.post(f"{provider.network.base_url}/v1/clone", files=files, data=data)
        resp.raise_for_status()
    return resp.json()


@mcp.tool()
async def tts_list_voices(provider_id: str = "local_index_tts"):
    """列出所有音色（含已注册的 clone/design profile）。"""
    provider = _registry.get_provider(provider_id)
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        resp = await client.get(f"{provider.network.base_url}/v1/voices")
        resp.raise_for_status()
    return resp.json()


@mcp.tool()
async def tts_list_providers():
    """列出所有已配置的 TTS 引擎。"""
    return {
        "providers": [
            {"provider_id": p.provider_id, "provider_type": p.provider_type,
             "display_name": p.display_name, "enabled": p.enabled}
            for p in _registry.list_providers()
        ]
    }


@mcp.tool()
async def tts_provider_status(provider_id: str = "local_index_tts"):
    """查看引擎运行时状态（healthy/stopped）。"""
    state = _manager.get_state(provider_id)
    return {"provider_id": provider_id, "status": state.status, "pid": state.pid}


@mcp.tool()
async def tts_start_provider(provider_id: str = "local_index_tts"):
    """启动指定引擎。"""
    state = await _manager.start(provider_id)
    return {"provider_id": provider_id, "status": state.status}


@mcp.tool()
async def tts_stop_provider(provider_id: str = "local_index_tts"):
    """停止指定引擎。"""
    await _manager.stop(provider_id)
    return {"provider_id": provider_id, "status": "stopped"}


@mcp.tool()
async def tts_restart_provider(provider_id: str = "local_index_tts"):
    """重启指定引擎。"""
    state = await _manager.restart(provider_id)
    return {"provider_id": provider_id, "status": state.status}


@mcp.tool()
async def tts_provider_logs(provider_id: str = "local_index_tts", stream: str = "stderr", lines: int = 50):
    """查看引擎运行日志。"""
    return {"provider_id": provider_id, "stream": stream, "content": _manager.get_logs(provider_id, stream, lines)}
