from pathlib import Path
import json
import os
import sys
import tempfile

from bobogen_protocol.models import CloneResponse, CloneStatusResponse, DesignResponse, HealthResponse, Voice, VoicesResponse
from bobogen_service_kit.profiles import ProfileStore, slugify_voice_id


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_ID = "voxcpm2"
DEFAULT_EXPECTED_ARCHITECTURE = "voxcpm2"


def env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_repo_dir() -> Path:
    return Path(os.environ.get("VOXCPM_REPO_DIR", ROOT_DIR / "models" / "voxcpm" / "repo"))


def get_model_id() -> str:
    return os.environ.get("VOXCPM_MODEL_ID", DEFAULT_MODEL_ID)


def get_expected_architecture() -> str:
    return os.environ.get("VOXCPM_EXPECTED_ARCHITECTURE", DEFAULT_EXPECTED_ARCHITECTURE).strip().lower()


def get_model_dir() -> Path:
    return Path(os.environ.get("VOXCPM_MODEL_DIR", ROOT_DIR / "models" / "voxcpm" / "checkpoints"))


def get_config_path() -> Path:
    return Path(os.environ.get("VOXCPM_CONFIG_PATH", get_model_dir() / "config.json"))


def get_model_weights_path() -> Path:
    return Path(os.environ.get("VOXCPM_MODEL_WEIGHTS_PATH", get_model_dir() / "model.safetensors"))


def get_audiovae_weights_path() -> Path:
    return Path(os.environ.get("VOXCPM_AUDIOVAE_WEIGHTS_PATH", get_model_dir() / "audiovae.pth"))


def get_tokenizer_path() -> Path:
    return Path(os.environ.get("VOXCPM_TOKENIZER_PATH", get_model_dir() / "tokenizer.json"))


def get_profile_dir() -> Path:
    return Path(
        os.environ.get(
            "VOXCPM_PROFILE_DIR",
            ROOT_DIR / "services" / "voxcpm-service" / "data" / "profiles" / get_model_id(),
        )
    )


def get_output_dir() -> Path:
    return Path(
        os.environ.get(
            "VOXCPM_OUTPUT_DIR",
            ROOT_DIR / "models" / "voxcpm" / "outputs" / get_model_id(),
        )
    )


class DesignStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def profile_path(self, voice_id: str) -> Path:
        return self.root / voice_id / "profile.json"

    def load(self, voice_id: str) -> dict | None:
        path = self.profile_path(voice_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[dict]:
        profiles = []
        for path in sorted(self.root.glob("*/profile.json")):
            profiles.append(json.loads(path.read_text(encoding="utf-8")))
        return profiles

    def create(self, request) -> dict:
        voice_id = slugify_voice_id(request.name or "voice-design")
        profile_root = self.root / voice_id
        profile_root.mkdir(parents=True, exist_ok=True)
        profile = {
            "voice_id": voice_id,
            "name": request.name or voice_id,
            "base_voice_id": request.base_voice_id or "voxcpm2-default",
            "instruction": request.parameters.get("instruction"),
            "language": request.parameters.get("language") or "zh",
            "emotion": request.parameters.get("emotion"),
            "parameters": request.parameters,
        }
        self.profile_path(voice_id).write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return profile


class VoxCPMHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.model = None
        self.ready = False
        self.last_error = None
        self.model_id = get_model_id()
        self.expected_architecture = get_expected_architecture()
        self.repo_dir = get_repo_dir()
        self.model_dir = get_model_dir()
        self.config_path = get_config_path()
        self.model_weights_path = get_model_weights_path()
        self.audiovae_weights_path = get_audiovae_weights_path()
        self.tokenizer_path = get_tokenizer_path()
        self.profile_dir = get_profile_dir()
        self.output_dir = get_output_dir()
        self.clone_store = ProfileStore(self.profile_dir / "clones")
        self.design_store = DesignStore(self.profile_dir / "designs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _required_paths(self) -> dict[str, Path]:
        return {
            "VOXCPM_REPO_DIR": self.repo_dir,
            "VOXCPM_SOURCE_DIR": self.repo_dir / "src",
            "VOXCPM_CONFIG_PATH": self.config_path,
            "VOXCPM_MODEL_WEIGHTS_PATH": self.model_weights_path,
            "VOXCPM_AUDIOVAE_WEIGHTS_PATH": self.audiovae_weights_path,
            "VOXCPM_TOKENIZER_PATH": self.tokenizer_path,
        }

    def _validate_required_paths(self) -> None:
        missing = [f"{name}={path}" for name, path in self._required_paths().items() if not path.exists()]
        if missing:
            raise FileNotFoundError(
                f"VoxCPM {self.model_id} requires version-matched local model files: "
                + "; ".join(missing)
            )

        try:
            architecture = json.loads(self.config_path.read_text(encoding="utf-8")).get("architecture")
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"VoxCPM {self.model_id} requires a readable version-matched config: {self.config_path}"
            ) from exc

        if not isinstance(architecture, str) or architecture.strip().lower() != self.expected_architecture:
            raise ValueError(
                f"VoxCPM {self.model_id} requires architecture {self.expected_architecture!r}, "
                f"found {architecture!r} in {self.config_path}"
            )

    async def startup(self):
        if self.test_mode:
            self.ready = True
            return
        self.model_id = get_model_id()
        self.expected_architecture = get_expected_architecture()
        self.repo_dir = get_repo_dir()
        self.model_dir = get_model_dir()
        self.config_path = get_config_path()
        self.model_weights_path = get_model_weights_path()
        self.audiovae_weights_path = get_audiovae_weights_path()
        self.tokenizer_path = get_tokenizer_path()
        try:
            self.ready = True
            if env_flag("VOXCPM_PRELOAD_ON_STARTUP", False):
                self._ensure_model()
            self.last_error = None
        except Exception as exc:
            self.ready = False
            self.last_error = str(exc)
            raise

    async def health(self):
        payload = HealthResponse(status="ok", model="VoxCPM2", version=self.model_id).model_dump()
        payload["ready"] = self.ready
        if self.last_error:
            payload["last_error"] = self.last_error
        return payload

    async def warmup(self):
        if self.test_mode:
            return {"status": "ok", "mode": "test"}
        self._ensure_model()
        self.ready = True
        self.last_error = None
        return {"status": "ready", "model": "VoxCPM2", "version": self.model_id}

    async def list_voices(self, language=None, page=1, page_size=100):
        voices = [
            Voice(
                voice_id="voxcpm2-default",
                name="VoxCPM2 Default",
                language=["zh", "en", "ja", "ko"],
                description="Instruction-first VoxCPM2 synthesis mode",
                tags=["default", "design"],
                metadata={
                    "model_id": self.model_id,
                    "repo_dir": str(self.repo_dir),
                    "model_dir": str(self.model_dir),
                },
            )
        ]
        for profile in self.clone_store.list():
            if language and profile.get("language") and profile["language"] != language:
                continue
            voices.append(
                Voice(
                    voice_id=profile["voice_id"],
                    name=profile.get("name") or profile["voice_id"],
                    language=[profile.get("language") or "zh"],
                    description="VoxCPM2 cloned voice profile backed by reference audio",
                    tags=["clone", "reference"],
                    metadata={
                        "reference_audio": profile.get("reference_audio"),
                        "reference_text": profile.get("reference_text"),
                        "emotion": profile.get("emotion"),
                    },
                )
            )
        for profile in self.design_store.list():
            if language and profile.get("language") and profile["language"] != language:
                continue
            voices.append(
                Voice(
                    voice_id=profile["voice_id"],
                    name=profile.get("name") or profile["voice_id"],
                    language=[profile.get("language") or "zh"],
                    description="VoxCPM2 designed voice profile backed by control instruction",
                    tags=["design", "instruction"],
                    metadata={
                        "instruction": profile.get("instruction"),
                        "emotion": profile.get("emotion"),
                    },
                )
            )
        return VoicesResponse(voices=voices, total=len(voices), page=page, page_size=page_size).model_dump()

    async def clone(self, request, audio):
        profile = await self.clone_store.create(request, audio)
        return CloneResponse(
            voice_id=profile["voice_id"],
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
        profile = self.clone_store.load(task_id)
        if profile is None:
            raise ValueError("unknown voice_id")
        return CloneStatusResponse(
            task_id=task_id,
            status="ready",
            voice_id=profile["voice_id"],
            name=profile.get("name"),
            metadata={"reference_audio": profile.get("reference_audio")},
        ).model_dump()

    async def design(self, request):
        profile = self.design_store.create(request)
        return DesignResponse(
            voice_id=profile["voice_id"],
            name=profile["name"],
            status="ready",
            metadata={
                "instruction": profile.get("instruction"),
                "language": profile.get("language"),
                "emotion": profile.get("emotion"),
            },
        ).model_dump()

    def _ensure_model(self):
        if self.test_mode:
            return None
        if self.model is None:
            self._validate_required_paths()
            repo_src = self.repo_dir / "src"
            if str(repo_src) not in sys.path:
                sys.path.insert(0, str(repo_src))
            from voxcpm import VoxCPM

            self.model = VoxCPM.from_pretrained(
                hf_model_id=str(self.model_dir),
                load_denoiser=env_flag("VOXCPM_LOAD_DENOISER", False),
                optimize=env_flag("VOXCPM_OPTIMIZE", False),
                local_files_only=True,
            )
            self.ready = True
            self.last_error = None
        return self.model

    async def synthesize(self, request, reference_audio=None, reference_text=None):
        clone_profile = None
        design_profile = None
        has_reference_audio = request.parameters.reference_audio or reference_audio is not None
        if request.voice_id != "voxcpm2-default" and not has_reference_audio:
            clone_profile = self.clone_store.load(request.voice_id)
            if clone_profile is None:
                design_profile = self.design_store.load(request.voice_id)
            if clone_profile is None and design_profile is None:
                raise ValueError("unknown voice_id")

        ref_audio_path = request.parameters.reference_audio or (clone_profile or {}).get("reference_audio")
        prompt_text = (
            reference_text
            or request.parameters.reference_text
            or (clone_profile or {}).get("reference_text")
            or request.parameters.extra.get("prompt_text")
        )
        instruction = request.parameters.instruction or (design_profile or {}).get("instruction")
        language = request.language or (design_profile or {}).get("language") or (clone_profile or {}).get("language") or "zh"
        mode = "clone" if (ref_audio_path or clone_profile or reference_audio is not None) else "design"
        cleanup_path = None

        if reference_audio is not None:
            suffix = Path(reference_audio.filename or "").suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_ref:
                temp_ref.write(await reference_audio.read())
                ref_audio_path = temp_ref.name
                cleanup_path = temp_ref.name

        if request.output.format != "wav":
            raise ValueError("unsupported format")

        if self.test_mode:
            headers = {
                "X-Audio-Duration": "1.0",
                "X-Debug-Mode": mode,
            }
            if ref_audio_path:
                headers["X-Debug-Reference-Audio"] = str(ref_audio_path)
            if prompt_text:
                headers["X-Debug-Prompt-Text-Source"] = (
                    "upload"
                    if reference_text
                    else "request"
                    if request.parameters.reference_text
                    else "profile"
                    if (clone_profile or {}).get("reference_text")
                    else "extra"
                )
            if instruction:
                headers["X-Debug-Instruction-Length"] = str(len(instruction))
                headers["X-Debug-Instruction-Source"] = (
                    "request" if request.parameters.instruction else "profile" if design_profile else "request"
                )
            return {"content": b"RIFF", "content_type": "audio/wav", "headers": headers}

        if not instruction and mode == "design":
            raise ValueError("VoxCPM2 voice design requires instruction")

        model = self._ensure_model()
        text = request.text
        if instruction:
            text = f"({instruction}){text}"

        wav = model.generate(
            text=text,
            prompt_wav_path=(ref_audio_path if request.parameters.extra.get("use_prompt_as_reference") else None),
            prompt_text=prompt_text if request.parameters.extra.get("use_prompt_as_reference") else None,
            reference_wav_path=ref_audio_path,
            cfg_value=float(request.parameters.extra.get("cfg_value", 2.0)),
            inference_timesteps=int(request.parameters.extra.get("inference_timesteps", 10)),
            normalize=bool(request.parameters.extra.get("normalize", False)),
            denoise=bool(request.parameters.extra.get("denoise", False)),
        )

        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", dir=self.output_dir, delete=False) as temp_output:
            output_path = temp_output.name

        try:
            sf.write(output_path, wav, getattr(model.tts_model, "sample_rate", request.output.sample_rate or 48000))
            content = Path(output_path).read_bytes()
        finally:
            if Path(output_path).exists():
                os.unlink(output_path)
            if cleanup_path and Path(cleanup_path).exists():
                os.unlink(cleanup_path)

        return {"content": content, "content_type": "audio/wav", "headers": {"X-Language": language}}
