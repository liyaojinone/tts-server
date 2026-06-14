from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
import struct
import sys
import wave

from bobogen_protocol.models import GenerateRequest


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_REPO_DIR = ROOT_DIR / "models" / "stable-audio-3" / "repo"
MODEL_ID = "stable-audio-3-small-sfx"
HF_REPO_ID = "stabilityai/stable-audio-3-small-sfx"
UPSTREAM_MODEL_NAME = "small-sfx"
DEFAULT_SAMPLE_RATE = 44100
logger = logging.getLogger("stable_audio3.generate")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _shorten(value: str, limit: int = 360) -> str | dict:
    if value.startswith("data:"):
        return {"kind": "data-uri", "length": len(value)}
    if len(value) <= limit:
        return value
    return {"preview": value[:limit], "length": len(value)}


def _sanitize(value, key: str = ""):
    if isinstance(value, (bytes, bytearray)):
        return {"kind": "bytes", "length": len(value)}
    if isinstance(value, str):
        if key.lower() in {"data", "audio", "content", "bytes", "blob"}:
            return _shorten(value, limit=120)
        return _shorten(value)
    if isinstance(value, dict):
        return {item_key: _sanitize(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _sanitize(value.model_dump(mode="json"))
    return value


def _describe_wav_bytes(content: bytes) -> dict:
    summary = {"bytes": len(content)}
    if not content.startswith(b"RIFF"):
        return summary
    try:
        with wave.open(BytesIO(content), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            frame_bytes = wav.readframes(frames)
    except (EOFError, wave.Error) as exc:
        summary["wavError"] = str(exc)
        return summary

    summary.update(
        {
            "format": "wav",
            "channels": channels,
            "sampleRate": sample_rate,
            "sampleWidth": sample_width,
            "frames": frames,
            "durationSeconds": round(frames / sample_rate, 3) if sample_rate else None,
        }
    )

    peak = 0.0
    sum_squares = 0.0
    sample_count = 0
    if sample_width == 2:
        for (sample,) in struct.iter_unpack("<h", frame_bytes[: len(frame_bytes) - (len(frame_bytes) % 2)]):
            normalized = sample / 32768.0
            peak = max(peak, abs(normalized))
            sum_squares += normalized * normalized
            sample_count += 1
    elif sample_width == 4:
        for (sample,) in struct.iter_unpack("<i", frame_bytes[: len(frame_bytes) - (len(frame_bytes) % 4)]):
            normalized = sample / 2147483648.0
            peak = max(peak, abs(normalized))
            sum_squares += normalized * normalized
            sample_count += 1
    elif sample_width == 1:
        for sample in frame_bytes:
            normalized = (sample - 128) / 128.0
            peak = max(peak, abs(normalized))
            sum_squares += normalized * normalized
            sample_count += 1

    if sample_count:
        summary["peak"] = round(peak, 6)
        summary["rms"] = round(math.sqrt(sum_squares / sample_count), 6)
        summary["silent"] = peak == 0
    return summary


def _describe_generated_audio(audio) -> dict:
    try:
        import numpy as np
    except ImportError:
        return {"error": "numpy unavailable"}

    if hasattr(audio, "detach"):
        audio = audio.detach().cpu()
    if hasattr(audio, "numpy"):
        audio = audio.numpy()
    array = np.asarray(audio, dtype=np.float32)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return {"shape": list(array.shape), "dtype": str(array.dtype), "finiteSamples": 0}
    peak = float(np.max(np.abs(finite)))
    rms = float(np.sqrt(np.mean(np.square(finite))))
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "finiteSamples": int(finite.size),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "silent": peak == 0,
    }


def _log_event(event: str, payload: dict) -> None:
    logger.info("%s %s", event, json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _silent_wav(duration_seconds: float, sample_rate: int) -> bytes:
    frames = max(1, int(duration_seconds * sample_rate))
    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00\x00\x00" * frames)
    return out.getvalue()


def _encode_wav(audio, sample_rate: int) -> bytes:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required to encode Stable Audio 3 output") from exc

    if hasattr(audio, "detach"):
        audio = audio.detach().cpu()
    if hasattr(audio, "numpy"):
        audio = audio.numpy()
    audio = np.asarray(audio, dtype=np.float32)

    if audio.ndim == 3:
        audio = audio[0]
    if audio.ndim == 1:
        audio = audio.reshape(1, -1)
    if audio.ndim != 2:
        raise RuntimeError(f"Unsupported generated audio shape: {audio.shape}")
    if not np.isfinite(audio).all():
        raise RuntimeError("Stable Audio 3 generated non-finite audio samples")

    channels, samples = audio.shape
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio.T * 32767.0).astype("<i2")

    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return out.getvalue()


class StableAudio3Handler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode or _truthy(os.environ.get("STABLE_AUDIO3_TEST_MODE"))
        self.repo_dir = Path(os.environ.get("STABLE_AUDIO3_REPO_DIR", DEFAULT_REPO_DIR))
        self.model_name = os.environ.get("STABLE_AUDIO3_MODEL_NAME", UPSTREAM_MODEL_NAME)
        self.device = os.environ.get("STABLE_AUDIO3_DEVICE") or None
        self.model_half = not _truthy(os.environ.get("STABLE_AUDIO3_DISABLE_HALF"))
        self._model = None

    def health(self):
        return {
            "status": "ok",
            "model": MODEL_ID,
            "version": "local",
            "ready": self.test_mode or self._model is not None,
            "testMode": self.test_mode,
        }

    def generate(self, request: GenerateRequest) -> dict:
        if request.model != MODEL_ID:
            raise ValueError(f"Unsupported model: {request.model}")
        if request.task != "audio.generate":
            raise ValueError(f"Unsupported task: {request.task}")
        if request.output.format != "wav":
            raise ValueError("Stable Audio 3 service currently supports wav output only")

        prompt = request.input.get("prompt")
        if not prompt:
            raise ValueError("input.prompt is required")

        duration = float(
            request.parameters.get("duration")
            or request.parameters.get("duration_seconds")
            or 7
        )
        sample_rate = request.output.sample_rate or DEFAULT_SAMPLE_RATE
        _log_event(
            "stableAudio3.generate.request",
            {
                "model": request.model,
                "task": request.task,
                "testMode": self.test_mode,
                "repoDir": str(self.repo_dir),
                "repoExists": self.repo_dir.exists(),
                "prompt": _sanitize(prompt),
                "parameters": _sanitize(request.parameters),
                "output": _sanitize(request.output),
            },
        )

        if self.test_mode:
            content = _silent_wav(duration, sample_rate)
            _log_event(
                "stableAudio3.generate.testMode",
                {
                    "testMode": True,
                    "silent": True,
                    "reason": "test mode returns a synthetic silent wav",
                    "audio": _describe_wav_bytes(content),
                },
            )
            return self._audio_result(content, sample_rate, duration)

        model = self._load_model()
        audio = model.generate(
            prompt=prompt,
            negative_prompt=request.parameters.get("negative_prompt"),
            duration=duration,
            steps=int(request.parameters.get("steps", 8)),
            cfg_scale=float(request.parameters.get("cfg_scale", 1.0)),
            seed=int(request.parameters.get("seed", -1)),
            batch_size=int(request.parameters.get("batch_size", 1)),
            truncate_output_to_duration=bool(request.parameters.get("truncate_output_to_duration", True)),
        )
        _log_event("stableAudio3.generate.modelOutput", _describe_generated_audio(audio))
        model_sample_rate = int(getattr(model.model, "sample_rate", DEFAULT_SAMPLE_RATE))
        content = _encode_wav(audio, model_sample_rate)
        _log_event(
            "stableAudio3.generate.response",
            {
                "testMode": False,
                "audio": _describe_wav_bytes(content),
                "sampleRate": model_sample_rate,
                "durationSeconds": duration,
            },
        )
        return self._audio_result(content, model_sample_rate, duration)

    def _load_model(self):
        if self._model is not None:
            return self._model
        if not self.repo_dir.exists():
            raise RuntimeError(f"Stable Audio 3 repository not found: {self.repo_dir}")
        if str(self.repo_dir) not in sys.path:
            sys.path.insert(0, str(self.repo_dir))
        try:
            import torch
            from huggingface_hub import hf_hub_download
            from stable_audio_3.loading_utils import load_diffusion_cond
            from stable_audio_3.model import StableAudioModel
        except ImportError as exc:
            raise RuntimeError(
                "stable_audio_3 dependencies are not installed. Run uv sync in models/stable-audio-3/repo first."
            ) from exc

        device = self.device
        if device is None and torch.cuda.is_available():
            device = "cuda"
        elif device is None and torch.backends.mps.is_available():
            device = "mps"
        elif device is None:
            device = "cpu"

        model_half = self.model_half and torch.cuda.is_available()
        config_path = hf_hub_download(repo_id=HF_REPO_ID, filename="model_config.json")
        checkpoint_path = hf_hub_download(repo_id=HF_REPO_ID, filename="model.safetensors")
        tokenizer_dir = Path(config_path).parent / "t5gemma-b-b-ul2"
        if not tokenizer_dir.exists():
            for filename in [
                "t5gemma-b-b-ul2/config.json",
                "t5gemma-b-b-ul2/generation_config.json",
                "t5gemma-b-b-ul2/model.safetensors",
                "t5gemma-b-b-ul2/special_tokens_map.json",
                "t5gemma-b-b-ul2/tokenizer.json",
                "t5gemma-b-b-ul2/tokenizer.model",
                "t5gemma-b-b-ul2/tokenizer_config.json",
            ]:
                hf_hub_download(repo_id=HF_REPO_ID, filename=filename)

        with open(config_path, encoding="utf-8") as file:
            model_config = json.load(file)
        conditioning_configs = []
        conditioning_configs.extend(model_config.get("conditioning", {}).get("configs", []))
        conditioning_configs.extend(model_config.get("model", {}).get("conditioning", {}).get("configs", []))
        for conditioner in conditioning_configs:
            if conditioner.get("type") == "t5gemma":
                config = conditioner.setdefault("config", {})
                config["model_path"] = str(tokenizer_dir)
                config.pop("repo_id", None)
                config.pop("subfolder", None)

        model = load_diffusion_cond(
            model_config,
            checkpoint_path,
            device=device,
            model_half=model_half,
        )
        model.use_lora = False
        model.lora_names = []
        self._model = StableAudioModel(model, model_config, device, model_half)
        return self._model

    def _audio_result(self, content: bytes, sample_rate: int, duration_seconds: float) -> dict:
        return {
            "content": content,
            "content_type": "audio/wav",
            "headers": {
                "X-Model-Id": MODEL_ID,
                "X-Task": "audio.generate",
                "X-Sample-Rate": str(sample_rate),
                "X-Audio-Duration": str(duration_seconds),
            },
        }
