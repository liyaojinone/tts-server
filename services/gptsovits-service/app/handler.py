from pathlib import Path
import json
import os
import sys
import tempfile
from typing import Optional

from bobogen_protocol.models import CloneResponse, CloneStatusResponse, HealthResponse, Voice, VoicesResponse
from bobogen_service_kit.profiles import resolve_voice_id


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_ID = "gpt_sovits_v2pro"
DEFAULT_UPSTREAM_VERSION = "v2Pro"


def get_repo_dir() -> Path:
    return Path(os.environ.get("GPTSOVITS_REPO_DIR", ROOT_DIR / "models" / "gpt-sovits" / "repo"))


def get_model_id() -> str:
    return os.environ.get("GPTSOVITS_MODEL_ID", DEFAULT_MODEL_ID)


def get_model_dir() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_MODEL_DIR",
            ROOT_DIR / "models" / "gpt-sovits" / "checkpoints" / get_model_id(),
        )
    )


def get_gpt_weights_path() -> Path:
    return Path(os.environ.get("GPTSOVITS_GPT_WEIGHTS_PATH", get_model_dir() / "s1v3.ckpt"))


def get_sovits_weights_path() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_SOVITS_WEIGHTS_PATH",
            get_model_dir() / "v2Pro" / "s2Gv2Pro.pth",
        )
    )


def get_bert_base_path() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_BERT_BASE_PATH",
            get_model_dir() / "chinese-roberta-wwm-ext-large",
        )
    )


def get_cnhuhbert_base_path() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_CNHUBERT_BASE_PATH",
            get_model_dir() / "chinese-hubert-base",
        )
    )


def get_sv_weights_path() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_SV_WEIGHTS_PATH",
            get_model_dir() / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt",
        )
    )


def get_profile_dir() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_PROFILE_DIR",
            ROOT_DIR / "services" / "gptsovits-service" / "data" / "profiles" / get_model_id(),
        )
    )


def get_output_dir() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_OUTPUT_DIR",
            ROOT_DIR / "models" / "gpt-sovits" / "outputs" / get_model_id(),
        )
    )


def get_runtime_config_path() -> Path:
    return Path(
        os.environ.get(
            "GPTSOVITS_RUNTIME_CONFIG_PATH",
            ROOT_DIR
            / "services"
            / "gptsovits-service"
            / "data"
            / "runtime"
            / get_model_id()
            / "tts_infer.yaml",
        )
    )


def env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


GPTSOVITS_ROOT = get_repo_dir()

if str(GPTSOVITS_ROOT) not in sys.path:
    sys.path.insert(0, str(GPTSOVITS_ROOT))
gpt_pkg = GPTSOVITS_ROOT / "GPT_SoVITS"
if str(gpt_pkg) not in sys.path:
    sys.path.insert(0, str(gpt_pkg))


class GPTSoVITSHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.pipeline = None
        self.ready = False
        self.last_error = None
        self.model_id = get_model_id()
        self.upstream_version = os.environ.get("GPTSOVITS_UPSTREAM_VERSION", DEFAULT_UPSTREAM_VERSION)
        self.repo_dir = get_repo_dir()
        self.model_dir = get_model_dir()
        self.gpt_weights_path = get_gpt_weights_path()
        self.sovits_weights_path = get_sovits_weights_path()
        self.bert_base_path = get_bert_base_path()
        self.cnhuhbert_base_path = get_cnhuhbert_base_path()
        self.sv_weights_path = get_sv_weights_path()
        self.profile_dir = get_profile_dir()
        self.output_dir = get_output_dir()
        self.runtime_config_path = get_runtime_config_path()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _required_paths(self) -> dict[str, Path]:
        return {
            "GPTSOVITS_REPO_DIR": self.repo_dir,
            "GPTSOVITS_SOURCE_DIR": self.repo_dir / "GPT_SoVITS",
            "GPTSOVITS_GPT_WEIGHTS_PATH": self.gpt_weights_path,
            "GPTSOVITS_SOVITS_WEIGHTS_PATH": self.sovits_weights_path,
            "GPTSOVITS_BERT_BASE_PATH": self.bert_base_path,
            "GPTSOVITS_CNHUBERT_BASE_PATH": self.cnhuhbert_base_path,
            "GPTSOVITS_SV_WEIGHTS_PATH": self.sv_weights_path,
        }

    def _validate_required_paths(self) -> None:
        missing = [f"{name}={path}" for name, path in self._required_paths().items() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                f"GPT-SoVITS {self.model_id} requires version-matched local model files: "
                + "; ".join(missing)
            )

    async def startup(self):
        if self.test_mode:
            self.ready = True
            return
        try:
            if env_flag("GPTSOVITS_PRELOAD_ON_STARTUP", False):
                self._ensure_pipeline()
            self.ready = True
            self.last_error = None
        except Exception as exc:
            self.ready = False
            self.last_error = str(exc)
            raise

    def _ensure_pipeline(self):
        if self.test_mode:
            return None
        if self.pipeline is None:
            self._validate_required_paths()
            for path in [self.repo_dir, self.repo_dir / "GPT_SoVITS"]:
                if str(path) not in sys.path:
                    sys.path.insert(0, str(path))
            original_cwd = os.getcwd()
            os.chdir(str(self.repo_dir))
            try:
                # The upstream TTS module imports ``sv.py`` during module loading.
                # ``sv.py`` resolves ``GPT_SoVITS/eres2net`` relative to the current
                # working directory, so this must happen before either upstream
                # module is imported rather than only around pipeline construction.
                from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
                import sv as speaker_encoder_module

                speaker_encoder_module.sv_path = str(self.sv_weights_path)

                tts_config = TTS_Config(
                    {
                        "custom": {
                            "device": os.environ.get("GPTSOVITS_DEVICE", "cuda"),
                            "is_half": os.environ.get("GPTSOVITS_IS_HALF", "true").strip().lower()
                            in {"1", "true", "yes", "on"},
                            "version": self.upstream_version,
                            "t2s_weights_path": str(self.gpt_weights_path),
                            "vits_weights_path": str(self.sovits_weights_path),
                            "bert_base_path": str(self.bert_base_path),
                            "cnhuhbert_base_path": str(self.cnhuhbert_base_path),
                        }
                    }
                )
                self.runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
                tts_config.configs_path = str(self.runtime_config_path)
            finally:
                os.chdir(original_cwd)
            original_cwd = os.getcwd()
            os.chdir(str(self.repo_dir))
            try:
                self.pipeline = TTS(tts_config)
            finally:
                os.chdir(original_cwd)
        return self.pipeline

    async def health(self):
        payload = HealthResponse(status="ok", model="GPT-SoVITS", version=self.model_id).model_dump()
        payload["ready"] = self.ready
        if self.last_error:
            payload["last_error"] = self.last_error
        return payload

    def _profile_path(self, voice_id: str) -> Path:
        return self.profile_dir / voice_id / "profile.json"

    def _load_profile(self, voice_id: str) -> Optional[dict]:
        profile_path = self._profile_path(voice_id)
        if not profile_path.exists():
            return None
        return json.loads(profile_path.read_text(encoding="utf-8"))

    def _list_profiles(self) -> list[dict]:
        profiles = []
        for profile_path in sorted(self.profile_dir.glob("*/profile.json")):
            profiles.append(json.loads(profile_path.read_text(encoding="utf-8")))
        return profiles

    async def clone(self, request, audio):
        voice_id = resolve_voice_id(request)
        profile_root = self.profile_dir / voice_id
        profile_root.mkdir(parents=True, exist_ok=True)

        suffix = Path(audio.filename or "reference.wav").suffix or ".wav"
        reference_audio_path = profile_root / f"reference{suffix}"
        content = await audio.read()
        reference_audio_path.write_bytes(content)

        profile = {
            "voice_id": voice_id,
            "name": request.name or voice_id,
            "language": request.language or "zh",
            "reference_audio": str(reference_audio_path),
            "reference_text": request.text,
            "emotion": request.emotion,
            "source_filename": audio.filename,
        }
        self._profile_path(voice_id).write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return CloneResponse(
            voice_id=voice_id,
            status="ready",
            name=profile["name"],
            metadata={
                "language": profile["language"],
                "reference_audio": profile["reference_audio"],
                "reference_text": profile["reference_text"],
                "emotion": profile["emotion"],
            },
        ).model_dump()

    async def clone_status(self, task_id: str):
        profile = self._load_profile(task_id)
        if profile is None:
            raise ValueError("unknown voice_id")
        return CloneStatusResponse(
            task_id=task_id,
            status="ready",
            voice_id=profile["voice_id"],
            name=profile.get("name"),
            metadata={"reference_audio": profile.get("reference_audio")},
        ).model_dump()

    async def list_voices(self, language=None, page=1, page_size=100):
        voices = [
            Voice(
                voice_id="default",
                name="GPT-SoVITS Default",
                language=["zh", "en", "ja", "ko", "yue"],
                description="Reference-driven GPT-SoVITS mode",
                tags=["reference", "default"],
                metadata={
                    "model_id": self.model_id,
                    "upstream_version": self.upstream_version,
                    "gpt_weights": str(self.gpt_weights_path),
                    "sovits_weights": str(self.sovits_weights_path),
                },
            )
        ]
        for profile in self._list_profiles():
            if language and profile.get("language") and profile["language"] != language:
                continue
            voices.append(
                Voice(
                    voice_id=profile["voice_id"],
                    name=profile.get("name") or profile["voice_id"],
                    language=[profile.get("language") or "zh"],
                    description="Cloned voice profile backed by reference audio",
                    tags=["clone", "reference"],
                    metadata={
                        "reference_audio": profile.get("reference_audio"),
                        "reference_text": profile.get("reference_text"),
                        "emotion": profile.get("emotion"),
                    },
                )
            )
        return VoicesResponse(voices=voices, total=len(voices), page=page, page_size=page_size).model_dump()

    async def synthesize(self, request, reference_audio=None, reference_text=None):
        if self.test_mode:
            return {"content": b"RIFF", "content_type": "audio/wav", "headers": {"X-Audio-Duration": "1.0"}}

        pipeline = self._ensure_pipeline()
        profile = None
        has_reference_audio = request.parameters.reference_audio or reference_audio is not None
        if request.voice_id != "default" and not has_reference_audio:
            profile = self._load_profile(request.voice_id)
            if profile is None:
                raise ValueError("Unknown voice_id and no cloned profile found")

        if reference_audio is not None:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_ref:
                temp_ref.write(await reference_audio.read())
                ref_audio_path = temp_ref.name
        else:
            ref_audio_path = request.parameters.reference_audio or (profile or {}).get("reference_audio")

        if not ref_audio_path:
            raise ValueError("GPT-SoVITS requires reference audio")

        prompt_text = reference_text or request.parameters.reference_text or (profile or {}).get("reference_text") or ""
        lang = request.language or (profile or {}).get("language") or "zh"
        media_type = request.output.format or "wav"

        with tempfile.NamedTemporaryFile(suffix=f".{media_type}", dir=self.output_dir, delete=False) as temp_out:
            output_path = temp_out.name

        req = {
            "text": request.text,
            "text_lang": lang,
            "ref_audio_path": str(ref_audio_path),
            "prompt_text": prompt_text,
            "prompt_lang": lang,
            "top_k": int(request.parameters.extra.get("top_k", 5)),
            "top_p": float(request.parameters.extra.get("top_p", 1.0)),
            "temperature": float(request.parameters.extra.get("temperature", 1.0)),
            "text_split_method": request.parameters.extra.get("text_split_method", "cut5"),
            "batch_size": int(request.parameters.extra.get("batch_size", 1)),
            "batch_threshold": float(request.parameters.extra.get("batch_threshold", 0.75)),
            "split_bucket": bool(request.parameters.extra.get("split_bucket", True)),
            "speed_factor": request.parameters.speed,
            "fragment_interval": float(request.parameters.extra.get("fragment_interval", 0.3)),
            "seed": int(request.parameters.extra.get("seed", -1)),
            "media_type": media_type,
            "streaming_mode": bool(request.parameters.extra.get("streaming_mode", False)),
            "parallel_infer": bool(request.parameters.extra.get("parallel_infer", True)),
            "repetition_penalty": float(request.parameters.extra.get("repetition_penalty", 1.35)),
        }

        result = pipeline.run(req)
        if hasattr(result, "__iter__") and not isinstance(result, (bytes, bytearray)):
            chunks = list(result)
            if chunks and isinstance(chunks[-1], tuple):
                sample_rate, audio_data = chunks[-1]
            else:
                sample_rate, audio_data = chunks[0]
        else:
            sample_rate, audio_data = result

        import soundfile as sf

        sf.write(output_path, audio_data, sample_rate, format=media_type)
        content = Path(output_path).read_bytes()
        os.unlink(output_path)
        return {
            "content": content,
            "content_type": "audio/wav" if media_type == "wav" else "application/octet-stream",
            "headers": {"X-Sample-Rate": str(sample_rate)},
        }
