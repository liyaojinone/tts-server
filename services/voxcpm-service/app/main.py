import os

from bobogen_service_kit.app import create_service_app

from app.handler import VoxCPMHandler


def create_app(test_mode: bool = False):
    return create_service_app(
        "voxcpm-service",
        VoxCPMHandler(test_mode=test_mode),
        api_key=os.environ.get("BOBOGEN_API_KEY") or os.environ.get("LOCAL_TTS_API_KEY"),
    )
