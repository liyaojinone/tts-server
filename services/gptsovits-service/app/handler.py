from pathlib import Path
import json
import os
import re
import sys
import tempfile
from typing import Optional

from local_tts_protocol.models import CloneResponse, CloneStatusResponse, HealthResponse, Voice, VoicesResponse


ROOT_DIR = Path(__file__).resolve().parents[3]
GPTSOVITS_ROOT = ROOT_DIR / "GPT-SoVITS-v2-240821"
if not GPTSOVITS_ROOT.exists():
    GPTSOVITS_ROOT = Path(r"E:\AiModel\tts\GPT-SoVITS-v2-240821")

if str(GPTSOVITS_ROOT) not in sys.path:
    sys.path.insert(0, str(GPTSOVITS_ROOT))
gpt_pkg = GPTSOVITS_ROOT / "GPT_SoVITS"
if str(gpt_pkg) not in sys.path:
    sys.path.insert(0, str(gpt_pkg))


def find_default_gpt_weights() -> Optional[str]:
    for directory in [GPTSOVITS_ROOT / "GPT_weights_v2", GPTSOVITS_ROOT / "GPT_weights"]:
        if not directory.exists():
            continue
        candidates = sorted(directory.glob("*.ckpt"))
        if candidates:
            return str(candidates[0])
    return None


def find_default_sovits_weights() -> Optional[str]:
    for directory in [GPTSOVITS_ROOT / "SoVITS_weights_v2", GPTSOVITS_ROOT / "SoVITS_weights"]:
        if not directory.exists():
            continue
        candidates = sorted(list(directory.glob("*.pth")) + list(directory.glob("*.ckpt")))
        if candidates:
            return str(candidates[0])
    return None


def slugify_voice_id(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())
    normalized = normalized.strip("-_").lower()
    return normalized or "voice"


class GPTSoVITSHandler:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.pipeline = None
        self.ready = False
        self.last_error = None
        profile_dir = os.environ.get("GPTSOVITS_PROFILE_DIR")
        self.profile_dir = Path(profile_dir) if profile_dir else ROOT_DIR / "services" / "gptsovits-service" / "data" / "profiles"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    async def startup(self):
        if self.test_mode:
            self.ready = True
            return
        try:
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
            from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

            config_path = str(GPTSOVITS_ROOT / "GPT_SoVITS" / "configs" / "tts_infer.yaml")
            original_cwd = os.getcwd()
            os.chdir(str(GPTSOVITS_ROOT))
            try:
                tts_config = TTS_Config(config_path)
            finally:
                os.chdir(original_cwd)

            bert_base_path = GPTSOVITS_ROOT / "GPT_SoVITS" / "pretrained_models" / "chinese-roberta-wwm-ext-large"
            cnhuhbert_base_path = GPTSOVITS_ROOT / "GPT_SoVITS" / "pretrained_models" / "chinese-hubert-base"
            if bert_base_path.exists():
                tts_config.bert_base_path = str(bert_base_path)
            if cnhuhbert_base_path.exists():
                tts_config.cnhuhbert_base_path = str(cnhuhbert_base_path)

            gpt_weights = find_default_gpt_weights()
            sovits_weights = find_default_sovits_weights()
            if gpt_weights:
                tts_config.t2s_weights_path = gpt_weights
            if sovits_weights:
                tts_config.vits_weights_path = sovits_weights
            original_cwd = os.getcwd()
            os.chdir(str(GPTSOVITS_ROOT))
            try:
                self.pipeline = TTS(tts_config)
            finally:
                os.chdir(original_cwd)
        return self.pipeline

    async def health(self):
        payload = HealthResponse(status="ok", model="GPT-SoVITS", version="local").model_dump()
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
        voice_id = slugify_voice_id(request.name or "voice")
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
                metadata={"gpt_weights": find_default_gpt_weights(), "sovits_weights": find_default_sovits_weights()},
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
        if request.voice_id != "default":
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

        with tempfile.NamedTemporaryFile(suffix=f".{media_type}", delete=False) as temp_out:
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
