from pathlib import Path
import os
import sys
import tempfile
from typing import Optional

from bobogen_protocol.models import CloneResponse, CloneStatusResponse, HealthResponse, Voice, VoicesResponse
from bobogen_service_kit.profiles import ProfileStore


ROOT_DIR = Path(__file__).resolve().parents[3]
F5_ROOT = Path(os.environ.get("F5TTS_REPO_DIR", ROOT_DIR / "models" / "f5-tts" / "repo"))

SCRIPT_DIR = str(F5_ROOT)
HF_CACHE_DIR = str(F5_ROOT / "huggingface" / "hub")
VOCAB_FILE = str(F5_ROOT / "src" / "f5_tts" / "infer" / "examples" / "vocab.txt")
SRC_DIR = str(F5_ROOT / "src")
MODEL_NAME = os.environ.get("F5_MODEL", "F5TTS_Base")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def find_local_vocoder_path() -> Optional[str]:
    snapshot_root = Path(HF_CACHE_DIR) / "models--charactr--vocos-mel-24khz" / "snapshots"
    if not snapshot_root.exists():
        return None
    for snapshot_dir in sorted(snapshot_root.iterdir(), reverse=True):
        if (snapshot_dir / "config.yaml").exists() and (snapshot_dir / "pytorch_model.bin").exists():
            return str(snapshot_dir)
    return None


def find_local_ckpt_file() -> Optional[str]:
    env_ckpt = os.environ.get("F5_CKPT_FILE")
    if env_ckpt and Path(env_ckpt).exists():
        return env_ckpt

    official_base_root = Path(HF_CACHE_DIR) / "models--SWivid--F5-TTS" / "snapshots"
    if official_base_root.exists():
        official_candidates = list(official_base_root.rglob("F5TTS_Base/model_1200000.safetensors"))
        if official_candidates:
            official_candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            return str(official_candidates[0])

    candidates = list((F5_ROOT / "ckpts").rglob("*.safetensors")) + list((F5_ROOT / "ckpts").rglob("*.pt"))
    if not candidates:
        return None
    candidates.sort(key=lambda path: ("pretrained" not in path.name.lower(), "model_last" not in path.name.lower(), -path.stat().st_size))
    return str(candidates[0])


class F5TTSHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.tts = None
        profile_dir = os.environ.get("F5TTS_PROFILE_DIR")
        self.profile_store = ProfileStore(
            Path(profile_dir) if profile_dir else ROOT_DIR / "services" / "f5tts-service" / "data" / "profiles"
        )

    def _ensure_tts(self):
        if self.test_mode:
            return None
        if self.tts is None:
            from f5_tts.api import F5TTS

            self.tts = F5TTS(
                model=MODEL_NAME,
                hf_cache_dir=HF_CACHE_DIR,
                vocab_file=VOCAB_FILE,
                ckpt_file=find_local_ckpt_file(),
                vocoder_local_path=find_local_vocoder_path(),
            )
        return self.tts

    async def health(self):
        return HealthResponse(status="ok", model="F5-TTS", version="local").model_dump()

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
                voice_id="f5-default",
                name="F5 Default",
                language=["zh", "en"],
                description="Reference-driven F5-TTS voice mode",
                tags=["reference", "default"],
                metadata={},
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
                    description="F5-TTS cloned voice profile backed by reference audio",
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
        profile = None
        if request.voice_id != "f5-default":
            profile = self.profile_store.load(request.voice_id)
        ref_audio_path = request.parameters.reference_audio or (profile or {}).get("reference_audio")
        if reference_audio is not None:
            suffix = Path(reference_audio.filename or "").suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_ref:
                temp_ref.write(await reference_audio.read())
                ref_audio_path = temp_ref.name

        ref_text = (
            reference_text
            or request.parameters.reference_text
            or (profile or {}).get("reference_text")
            or ""
        )
        ref_text_source = (
            "upload"
            if reference_text
            else "request"
            if request.parameters.reference_text
            else "profile"
            if (profile or {}).get("reference_text")
            else "empty"
        )

        if self.test_mode:
            headers = {"X-Audio-Duration": "1.0"}
            if ref_audio_path:
                headers["X-Debug-Reference-Audio"] = str(ref_audio_path)
            if ref_text:
                headers["X-Debug-Reference-Text-Source"] = ref_text_source
                headers["X-Debug-Reference-Text-Length"] = str(len(str(ref_text)))
            return {"content": b"RIFF", "content_type": "audio/wav", "headers": headers}

        tts = self._ensure_tts()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_output:
            output_path = temp_output.name

        _, sr, _ = tts.infer(
            gen_text=request.text,
            ref_file=str(ref_audio_path),
            ref_text=ref_text,
            nfe_step=int(request.parameters.extra.get("nfe_step", 32)),
            file_wave=output_path,
            speed=request.parameters.speed,
            remove_silence=bool(request.parameters.extra.get("remove_silence", False)),
            cross_fade_duration=float(request.parameters.extra.get("cross_fade_duration", 0.15)),
            cfg_strength=float(request.parameters.extra.get("cfg_strength", 2.0)),
            sway_sampling_coef=-1.0,
        )
        content = Path(output_path).read_bytes()
        os.unlink(output_path)
        return {"content": content, "content_type": "audio/wav", "headers": {"X-Sample-Rate": str(sr)}}
