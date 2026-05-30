from contextlib import contextmanager
from pathlib import Path
import os
import sys
import tempfile

from local_tts_protocol.models import CloneResponse, CloneStatusResponse, HealthResponse, Voice, VoicesResponse
from local_tts_service_kit.profiles import ProfileStore


ROOT_DIR = Path(__file__).resolve().parents[3]
INDEXTTS_REPO_DIR = Path(os.environ.get("INDEXTTS_REPO_DIR", ROOT_DIR / "models" / "index-tts" / "repo"))
INDEXTTS_MODEL_DIR = Path(os.environ.get("INDEXTTS_MODEL_DIR", ROOT_DIR / "models" / "index-tts" / "checkpoints"))

if str(INDEXTTS_REPO_DIR) not in sys.path:
    sys.path.insert(0, str(INDEXTTS_REPO_DIR))


def env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def pushd(path: Path):
    original_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original_cwd)


class IndexTTSHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.tts = None
        self.ready = False
        self.last_error = None
        profile_dir = os.environ.get("INDEXTTS_PROFILE_DIR")
        self.profile_store = ProfileStore(
            Path(profile_dir) if profile_dir else ROOT_DIR / "services" / "index-tts-service" / "data" / "profiles"
        )
        output_dir = os.environ.get("INDEXTTS_OUTPUT_DIR")
        self.output_dir = Path(output_dir) if output_dir else ROOT_DIR / "models" / "index-tts" / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def startup(self):
        if self.test_mode:
            self.ready = True
            return
        self.ready = INDEXTTS_REPO_DIR.exists() and INDEXTTS_MODEL_DIR.exists()
        if not self.ready:
            self.last_error = "IndexTTS repository or checkpoints directory is missing"
            return
        if env_flag("INDEXTTS_PRELOAD_ON_STARTUP", True):
            self._ensure_tts()

    async def health(self):
        payload = HealthResponse(status="ok", model="IndexTTS2", version="local").model_dump()
        payload["ready"] = self.ready
        if self.last_error:
            payload["last_error"] = self.last_error
        return payload

    async def clone(self, request, audio):
        profile = await self.profile_store.create(request, audio)
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
        profile = self.profile_store.load(task_id)
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
                voice_id="index-default",
                name="IndexTTS Default",
                language=["zh", "en"],
                description="Reference-driven IndexTTS2 synthesis mode",
                tags=["reference", "default"],
                metadata={
                    "repo_dir": str(INDEXTTS_REPO_DIR),
                    "model_dir": str(INDEXTTS_MODEL_DIR),
                },
            )
        ]
        for profile in self.profile_store.list():
            if language and profile.get("language") and profile["language"] != language:
                continue
            voices.append(
                Voice(
                    voice_id=profile["voice_id"],
                    name=profile.get("name") or profile["voice_id"],
                    language=[profile.get("language") or "zh"],
                    description="IndexTTS cloned voice profile backed by reference audio",
                    tags=["clone", "reference"],
                    metadata={
                        "reference_audio": profile.get("reference_audio"),
                        "reference_text": profile.get("reference_text"),
                        "emotion": profile.get("emotion"),
                    },
                )
            )
        return VoicesResponse(voices=voices, total=len(voices), page=page, page_size=page_size).model_dump()

    def _ensure_tts(self):
        if self.test_mode:
            return None
        if self.tts is None:
            # 强制离线，避免从 HF 重新下载
            if not os.environ.get("HF_HUB_OFFLINE"):
                os.environ["HF_HUB_OFFLINE"] = "1"
            if not os.environ.get("TRANSFORMERS_OFFLINE"):
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

            from indextts.infer_v2 import IndexTTS2

            with pushd(INDEXTTS_REPO_DIR):
                self.tts = IndexTTS2(
                    cfg_path=str(INDEXTTS_MODEL_DIR / "config.yaml"),
                    model_dir=str(INDEXTTS_MODEL_DIR),
                    use_fp16=env_flag("INDEXTTS_USE_FP16", True),
                    use_cuda_kernel=env_flag("INDEXTTS_USE_CUDA_KERNEL", False),
                    use_deepspeed=env_flag("INDEXTTS_USE_DEEPSPEED", False),
                    use_accel=env_flag("INDEXTTS_USE_ACCEL", False),
                    use_torch_compile=env_flag("INDEXTTS_USE_TORCH_COMPILE", False),
                    device=os.environ.get("INDEXTTS_DEVICE") or None,
                )
            self.ready = True
            self.last_error = None
        return self.tts

    async def synthesize(self, request, reference_audio=None, reference_text=None):
        profile = None
        if request.voice_id != "index-default":
            profile = self.profile_store.load(request.voice_id)
            if profile is None:
                raise ValueError("unknown voice_id")

        ref_audio_path = request.parameters.reference_audio or (profile or {}).get("reference_audio")
        cleanup_path = None
        emotion_cleanup_path = None
        emotion_audio_path = request.parameters.extra.get("emotion_reference_audio")
        emotion_reference_audio = request.parameters.extra.get("_emotion_reference_audio_upload")
        if reference_audio is not None:
            suffix = Path(reference_audio.filename or "").suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_ref:
                temp_ref.write(await reference_audio.read())
                ref_audio_path = temp_ref.name
                cleanup_path = temp_ref.name
        if emotion_reference_audio is not None:
            suffix = Path(emotion_reference_audio.filename or "").suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_emo:
                temp_emo.write(await emotion_reference_audio.read())
                emotion_audio_path = temp_emo.name
                emotion_cleanup_path = temp_emo.name

        if not ref_audio_path:
            raise ValueError("IndexTTS requires reference audio")

        if request.output.format != "wav":
            raise ValueError("unsupported format")

        if self.test_mode:
            headers = {"X-Audio-Duration": "1.0"}
            if ref_audio_path:
                headers["X-Debug-Reference-Audio"] = str(ref_audio_path)
            if emotion_audio_path:
                headers["X-Debug-Emotion-Reference-Audio"] = str(emotion_audio_path)
            if reference_text or request.parameters.reference_text or (profile or {}).get("reference_text"):
                headers["X-Debug-Reference-Text-Length"] = str(
                    len(reference_text or request.parameters.reference_text or (profile or {}).get("reference_text") or "")
                )
            return {"content": b"RIFF", "content_type": "audio/wav", "headers": headers}

        tts = self._ensure_tts()
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=self.output_dir, delete=False) as temp_output:
            output_path = temp_output.name

        try:
            with pushd(INDEXTTS_REPO_DIR):
                tts.infer(
                    spk_audio_prompt=str(ref_audio_path),
                    text=request.text,
                    output_path=output_path,
                    emo_audio_prompt=str(emotion_audio_path) if emotion_audio_path else None,
                    emo_text=request.parameters.extra.get("emo_text"),
                    use_emo_text=bool(request.parameters.extra.get("use_emo_text", False)),
                    emo_vector=request.parameters.extra.get("emo_vector"),
                    emo_alpha=float(request.parameters.extra.get("emo_alpha", 1.0)),
                    use_random=bool(request.parameters.extra.get("use_random", False)),
                    interval_silence=int(request.parameters.extra.get("interval_silence", 200)),
                    max_text_tokens_per_segment=int(request.parameters.extra.get("max_text_tokens_per_segment", 120)),
                    verbose=bool(request.parameters.extra.get("verbose", False)),
                )
            content = Path(output_path).read_bytes()
        finally:
            if cleanup_path and Path(cleanup_path).exists():
                os.unlink(cleanup_path)
            if emotion_cleanup_path and Path(emotion_cleanup_path).exists():
                os.unlink(emotion_cleanup_path)

        return {"content": content, "content_type": "audio/wav"}
