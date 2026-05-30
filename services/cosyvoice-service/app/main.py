import os

from local_tts_service_kit.app import create_service_app

from app.handler import CosyVoiceHandler


def create_app(test_mode: bool = False):
    return create_service_app("cosyvoice-service", CosyVoiceHandler(test_mode=test_mode), api_key=os.environ.get("LOCAL_TTS_API_KEY"))
