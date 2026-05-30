from pathlib import Path
import os
import sys
import tempfile

from local_tts_protocol.models import CloneResponse, CloneStatusResponse, HealthResponse, Voice, VoicesResponse
from local_tts_service_kit.profiles import ProfileStore


ROOT_DIR = Path(__file__).resolve().parents[3]
COSYVOICE_ROOT = ROOT_DIR / "CosyVoice2" / "CosyVoice"
if not COSYVOICE_ROOT.exists():
    COSYVOICE_ROOT = Path(r"E:\AiModel\tts\CosyVoice2\CosyVoice")

THIRD_PARTY_DIR = str(COSYVOICE_ROOT / "third_party" / "Matcha-TTS")
if THIRD_PARTY_DIR not in sys.path:
    sys.path.insert(0, THIRD_PARTY_DIR)
if str(COSYVOICE_ROOT) not in sys.path:
    sys.path.insert(0, str(COSYVOICE_ROOT))


class CosyVoiceHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.sft_model = None
        self.zero_shot_model = None
        profile_dir = os.environ.get("COSYVOICE_PROFILE_DIR")
        self.profile_store = ProfileStore(
            Path(profile_dir) if profile_dir else ROOT_DIR / "services" / "cosyvoice-service" / "data" / "profiles"
        )

    def _load_sft_model(self):
        if self.sft_model is None:
            from cosyvoice.cli.cosyvoice import CosyVoice2

            self.sft_model = CosyVoice2(
                model_dir=str(COSYVOICE_ROOT / "pretrained_models" / "CosyVoice2-0.5B"),
                load_jit=False,
                load_trt=False,
                fp16=True,
            )
        return self.sft_model

    def _load_zero_shot_model(self):
        if self.zero_shot_model is None:
            from cosyvoice.cli.cosyvoice import CosyVoice2

            self.zero_shot_model = CosyVoice2(
                model_dir=str(COSYVOICE_ROOT / "pretrained_models" / "CosyVoice2-0.5B"),
                load_jit=False,
                load_trt=False,
                fp16=True,
            )
        return self.zero_shot_model

    async def health(self):
        return HealthResponse(status="ok", model="CosyVoice", version="local").model_dump()

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
                "mode": "zero_shot",
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
                voice_id="中文女",
                name="中文女",
                language=["zh"],
                gender="female",
                description="CosyVoice preset mode",
                tags=["preset"],
                metadata={"mode": "sft"},
            ),
            Voice(
                voice_id="clone",
                name="Zero-shot Clone",
                language=["zh", "en", "ja", "yue", "ko"],
                description="CosyVoice zero-shot cloning mode",
                tags=["reference", "clone"],
                metadata={"mode": "zero_shot"},
            ),
        ]
        for profile in self.profile_store.list():
            if language and profile.get("language") and profile["language"] != language:
                continue
            voices.append(
                Voice(
                    voice_id=profile["voice_id"],
                    name=profile.get("name") or profile["voice_id"],
                    language=[profile.get("language") or "zh"],
                    description="CosyVoice cloned voice profile backed by reference audio",
                    tags=["clone", "reference"],
                    metadata={
                        "mode": "zero_shot",
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

        text = request.text
        speed = request.parameters.speed
        profile = None
        if request.voice_id not in {"clone", "中文女"}:
            profile = self.profile_store.load(request.voice_id)
        mode = "zero_shot" if request.voice_id == "clone" or profile else "sft"

        if mode == "sft":
            model = self._load_sft_model()
            audio_chunks = []
            for item in model.inference_sft(text, request.voice_id, stream=False, speed=speed):
                audio_chunks.append(item["tts_speech"])
        else:
            profile_reference_audio = (profile or {}).get("reference_audio")
            if reference_audio is None and not request.parameters.reference_audio and not profile_reference_audio:
                raise ValueError("CosyVoice clone mode requires reference audio")

            if reference_audio is not None:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_ref:
                    temp_ref.write(await reference_audio.read())
                    reference_audio_path = temp_ref.name
            else:
                reference_audio_path = request.parameters.reference_audio or (profile or {}).get("reference_audio")

            from cosyvoice.utils.file_utils import load_wav

            model = self._load_zero_shot_model()
            prompt_speech_16k = load_wav(str(reference_audio_path), 16000)
            prompt_text = reference_text or request.parameters.reference_text or (profile or {}).get("reference_text") or ""
            audio_chunks = []
            for item in model.inference_zero_shot(text, prompt_text, prompt_speech_16k, stream=False, speed=speed):
                audio_chunks.append(item["tts_speech"])

        import torch
        import torchaudio

        output = torch.concat(audio_chunks, dim=1)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_output:
            output_path = temp_output.name
        torchaudio.save(output_path, output, 22050, format="wav")
        content = Path(output_path).read_bytes()
        os.unlink(output_path)
        return {"content": content, "content_type": "audio/wav", "headers": {"X-Sample-Rate": "22050"}}
