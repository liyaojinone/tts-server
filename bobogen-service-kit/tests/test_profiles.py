import asyncio

import pytest


def test_profile_store_preserves_explicit_voice_id(tmp_path):
    from bobogen_protocol.models import CloneRequest
    from bobogen_service_kit.profiles import ProfileStore

    store = ProfileStore(tmp_path)
    profile = asyncio.run(
        store.create(
            CloneRequest(voice_id="shared-voice-001", name="同一音色", language="zh"),
            DummyAudio(),
        )
    )

    assert profile["voice_id"] == "shared-voice-001"
    assert (tmp_path / "shared-voice-001" / "profile.json").exists()


def test_profile_store_rejects_path_traversal_voice_id(tmp_path):
    from bobogen_protocol.models import CloneRequest
    from bobogen_service_kit.profiles import ProfileStore

    store = ProfileStore(tmp_path)
    with pytest.raises(ValueError, match="voice_id"):
        asyncio.run(
            store.create(
                CloneRequest(voice_id="../outside", name="不安全"),
                DummyAudio(),
            )
        )


class DummyAudio:
    filename = "reference.wav"

    async def read(self):
        return b"RIFF"
