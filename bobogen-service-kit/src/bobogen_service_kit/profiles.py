from pathlib import Path
import json
import re
from typing import Optional


def slugify_voice_id(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())
    normalized = normalized.strip("-_").lower()
    return normalized or "voice"


class ProfileStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def profile_path(self, voice_id: str) -> Path:
        return self.root / voice_id / "profile.json"

    def load(self, voice_id: str) -> Optional[dict]:
        profile_path = self.profile_path(voice_id)
        if not profile_path.exists():
            return None
        return json.loads(profile_path.read_text(encoding="utf-8"))

    def list(self) -> list[dict]:
        profiles = []
        for profile_path in sorted(self.root.glob("*/profile.json")):
            profiles.append(json.loads(profile_path.read_text(encoding="utf-8")))
        return profiles

    async def create(self, request, audio) -> dict:
        voice_id = slugify_voice_id(request.name or "voice")
        profile_root = self.root / voice_id
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
        self.profile_path(voice_id).write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return profile
