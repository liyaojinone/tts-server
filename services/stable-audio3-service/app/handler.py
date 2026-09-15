from dataclasses import dataclass
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
DEFAULT_MODEL_ID = "stable_audio_3_small_sfx"
DEFAULT_UPSTREAM_MODEL_NAME = "small-sfx"
MODEL_ID_BY_UPSTREAM_NAME = {
    "small-sfx": "stable_audio_3_small_sfx",
    "small-music": "stable_audio_3_small_music",
    "medium": "stable_audio_3_medium",
}
HF_REPO_ID_BY_MODEL_ID = {
    "stable_audio_3_small_sfx": "stabilityai/stable-audio-3-small-sfx",
    "stable_audio_3_small_music": "stabilityai/stable-audio-3-small-music",
    "stable_audio_3_medium": "stabilityai/stable-audio-3-medium",
}
DEFAULT_SAMPLE_RATE = 44100
TOKENIZER_FILENAMES = [
    "t5gemma-b-b-ul2/config.json",
    "t5gemma-b-b-ul2/generation_config.json",
    "t5gemma-b-b-ul2/model.safetensors",
    "t5gemma-b-b-ul2/special_tokens_map.json",
    "t5gemma-b-b-ul2/tokenizer.json",
    "t5gemma-b-b-ul2/tokenizer.model",
    "t5gemma-b-b-ul2/tokenizer_config.json",
]
logger = logging.getLogger("stable_audio3.generate")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)


def _truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _model_id_from_env(model_name: str) -> str:
    return os.environ.get("STABLE_AUDIO3_MODEL_ID") or MODEL_ID_BY_UPSTREAM_NAME.get(
        model_name,
        DEFAULT_MODEL_ID,
    )


def _hf_repo_id_from_env(model_id: str) -> str:
    return os.environ.get("STABLE_AUDIO3_HF_REPO_ID") or HF_REPO_ID_BY_MODEL_ID.get(
        model_id,
        f"stabilityai/{model_id}",
    )


@dataclass(frozen=True)
class StableAudio3ModelFiles:
    config_path: Path
    checkpoint_path: Path
    tokenizer_dir: Path


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
        self.model_name = os.environ.get("STABLE_AUDIO3_MODEL_NAME", DEFAULT_UPSTREAM_MODEL_NAME)
        self.model_id = _model_id_from_env(self.model_name)
        self.hf_repo_id = _hf_repo_id_from_env(self.model_id)
        model_dir = os.environ.get("STABLE_AUDIO3_MODEL_DIR")
        self.model_dir = Path(model_dir) if model_dir else None
        self.device = os.environ.get("STABLE_AUDIO3_DEVICE") or None
        self.model_half = not _truthy(os.environ.get("STABLE_AUDIO3_DISABLE_HALF"))
        self._model = None

    def health(self):
        return {
            "status": "ok",
            "model": self.model_id,
            "upstreamModel": self.model_name,
            "hfRepoId": self.hf_repo_id,
            "modelDir": str(self.model_dir) if self.model_dir else None,
            "version": "local",
            "ready": self.test_mode or self._model is not None,
            "testMode": self.test_mode,
        }

    def warmup(self) -> dict:
        if self.test_mode:
            return {"status": "ok", "mode": "test"}
        self._load_model()
        return {"status": "ready", "model": self.model_id, "hfRepoId": self.hf_repo_id}

    def generate(self, request: GenerateRequest) -> dict:
        if request.model != self.model_id:
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
                "upstreamModel": self.model_name,
                "hfRepoId": self.hf_repo_id,
                "modelDir": str(self.model_dir) if self.model_dir else None,
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
                "stable_audio_3 dependencies are not installed. Reinstall the model from the client so the "
                "managed virtual environment under services/stable-audio3-service/.venv is rebuilt."
            ) from exc

        device = self.device
        if device is None and torch.cuda.is_available():
            device = "cuda"
        elif device is None and torch.backends.mps.is_available():
            device = "mps"
        elif device is None:
            device = "cpu"

        model_half = self.model_half and torch.cuda.is_available()
        model_files = self._resolve_model_files(hf_hub_download)
        config_path = model_files.config_path
        checkpoint_path = model_files.checkpoint_path
        tokenizer_dir = model_files.tokenizer_dir

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

        if self.model_name == "medium" and _truthy(
            os.environ.get("STABLE_AUDIO3_LOW_MEMORY_LOAD", "1")
        ):
            model = self._load_diffusion_cond_low_memory(
                model_config,
                checkpoint_path,
                device=device,
                model_half=model_half,
            )
        else:
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

    def _load_diffusion_cond_low_memory(
        self,
        model_config: dict,
        checkpoint_path: Path,
        *,
        device: str,
        model_half: bool,
    ):
        """Load the official model graph without duplicating its full FP32 state dict.

        Stable Audio 3's upstream loader creates the complete graph, reads the
        complete safetensors file into a second CPU-side state dict, then moves
        the graph to the target device. That transient peak is larger than the
        available RAM/VRAM on common 6 GB Windows GPUs. The graph and model
        configuration remain upstream; this adapter only streams each checkpoint
        tensor, casts it before the device transfer, and assigns it to the graph.
        """
        import torch
        from torch import nn
        from safetensors import safe_open
        from stable_audio_3.factory import (
            create_multi_conditioner_from_conditioning_config,
            create_pretransform_from_config,
        )
        from stable_audio_3.models.diffusion import (
            ConditionedDiffusionModelWrapper,
            DiTWrapper,
        )

        root_model_config = model_config["model"]
        diffusion_config = root_model_config.get("diffusion")
        diffusion_model_config = diffusion_config.get("config")
        diffusion_objective = diffusion_config.get("diffusion_objective", "v")
        modular_local_cond_configs = diffusion_config.get("modular_local_cond_configs", [])

        # Keep the large diffusion graph and autoencoder on meta while the
        # conditioner is constructed on CPU (its official T5 weights are loaded
        # lazily from the already-resolved tokenizer directory).
        with torch.device("meta"):
            diffusion_model = DiTWrapper(
                diffusion_objective=diffusion_objective,
                modular_local_cond_configs=modular_local_cond_configs,
                **diffusion_model_config,
            )
            pretransform = create_pretransform_from_config(
                root_model_config,
                model_config.get("sample_rate"),
            )

        io_channels = root_model_config.get("io_channels")
        sample_rate = model_config.get("sample_rate")
        cross_attention_ids = diffusion_config.get("cross_attention_cond_ids", [])
        global_cond_ids = diffusion_config.get("global_cond_ids", [])
        input_concat_ids = diffusion_config.get("input_concat_ids", [])
        local_add_cond_ids = diffusion_config.get("local_add_cond_ids", [])
        modular_local_cond_ids = [c["id"] for c in modular_local_cond_configs]
        prepend_cond_ids = diffusion_config.get("prepend_cond_ids", [])
        distribution_shift_options = diffusion_config.get("distribution_shift_options")
        sampling_distribution_shift_options = diffusion_config.get("sampling_distribution_shift_options")
        mask_padding_attention = diffusion_config.get("mask_padding_attention", False)
        use_effective_length_for_schedule = diffusion_config.get(
            "use_effective_length_for_schedule", False
        )
        conditioning = root_model_config.get("conditioning")
        conditioner = create_multi_conditioner_from_conditioning_config(conditioning)
        min_input_length = pretransform.downsampling_ratio * diffusion_model.model.patch_size

        model = ConditionedDiffusionModelWrapper(
            diffusion_model,
            conditioner,
            min_input_length=min_input_length,
            sample_rate=sample_rate,
            cross_attn_cond_ids=cross_attention_ids,
            global_cond_ids=global_cond_ids,
            input_concat_ids=input_concat_ids,
            local_add_cond_ids=local_add_cond_ids,
            modular_local_cond_ids=modular_local_cond_ids,
            prepend_cond_ids=prepend_cond_ids,
            pretransform=pretransform,
            io_channels=io_channels,
            distribution_shift_options=distribution_shift_options,
            sampling_distribution_shift_options=sampling_distribution_shift_options,
            mask_padding_attention=mask_padding_attention,
            diffusion_objective=diffusion_objective,
            use_effective_length_for_schedule=use_effective_length_for_schedule,
        )

        target_state = model.state_dict()
        matched = 0
        with safe_open(str(checkpoint_path), framework="pt", device="cpu") as source:
            for source_key in source.keys():
                target_key = self._remap_checkpoint_key(source_key, target_state)
                if target_key not in target_state:
                    logger.warning("Checkpoint key not found in Stable Audio 3 graph: %s", source_key)
                    continue

                expected = target_state[target_key]
                tensor = source.get_tensor(source_key)
                if tuple(tensor.shape) != tuple(expected.shape):
                    logger.warning(
                        "Skipping Stable Audio 3 checkpoint key with shape mismatch: %s (%s != %s)",
                        source_key,
                        tuple(tensor.shape),
                        tuple(expected.shape),
                    )
                    continue
                if model_half:
                    tensor = tensor.to(dtype=torch.float16)
                tensor = tensor.to(device)
                self._assign_checkpoint_tensor(model, target_key, tensor, nn)
                matched += 1

        if matched == 0:
            raise RuntimeError(f"Stable Audio 3 checkpoint contains no matching tensors: {checkpoint_path}")
        meta_keys = [
            name
            for name, value in model.state_dict().items()
            if getattr(value, "device", None) is not None and value.device.type == "meta"
        ]
        if meta_keys:
            raise RuntimeError(
                "Stable Audio 3 low-memory load left uninitialized tensors: "
                + ", ".join(meta_keys[:5])
            )
        return model.eval().requires_grad_(False)

    @staticmethod
    def _remap_checkpoint_key(source_key: str, target_state: dict) -> str:
        if source_key in target_state:
            return source_key
        parts = source_key.split(".")
        for index in range(1, len(parts)):
            candidate = ".".join(parts[:index]) + "." + ".".join(parts[index + 1 :])
            if candidate in target_state:
                return candidate
        return source_key

    @staticmethod
    def _assign_checkpoint_tensor(model, target_key: str, tensor, nn_module) -> None:
        parent_path, _, attribute = target_key.rpartition(".")
        parent = model.get_submodule(parent_path) if parent_path else model
        if attribute in parent._parameters:
            parent._parameters[attribute] = nn_module.Parameter(tensor, requires_grad=False)
        elif attribute in parent._buffers:
            parent._buffers[attribute] = tensor
        else:
            raise RuntimeError(f"Stable Audio 3 checkpoint target is not a parameter or buffer: {target_key}")

    def _resolve_model_files(self, hf_hub_download) -> StableAudio3ModelFiles:
        if self.model_dir is not None and self.model_dir.exists():
            config_path = self.model_dir / "model_config.json"
            checkpoint_path = self.model_dir / "model.safetensors"
            tokenizer_dir = self.model_dir / "t5gemma-b-b-ul2"
            required_paths = [config_path, checkpoint_path, *[self.model_dir / filename for filename in TOKENIZER_FILENAMES]]
            missing = [str(path) for path in required_paths if not path.exists()]
            if missing:
                raise RuntimeError(
                    "Stable Audio 3 local model directory is incomplete. Missing files: "
                    + ", ".join(missing[:5])
                )
            return StableAudio3ModelFiles(config_path, checkpoint_path, tokenizer_dir)

        config_path = Path(hf_hub_download(repo_id=self.hf_repo_id, filename="model_config.json"))
        checkpoint_path = Path(hf_hub_download(repo_id=self.hf_repo_id, filename="model.safetensors"))
        tokenizer_dir = config_path.parent / "t5gemma-b-b-ul2"
        if not tokenizer_dir.exists():
            for filename in TOKENIZER_FILENAMES:
                hf_hub_download(repo_id=self.hf_repo_id, filename=filename)
        return StableAudio3ModelFiles(config_path, checkpoint_path, tokenizer_dir)

    def _audio_result(self, content: bytes, sample_rate: int, duration_seconds: float) -> dict:
        return {
            "content": content,
            "content_type": "audio/wav",
            "headers": {
                "X-Model-Id": self.model_id,
                "X-Task": "audio.generate",
                "X-Sample-Rate": str(sample_rate),
                "X-Audio-Duration": str(duration_seconds),
            },
        }
