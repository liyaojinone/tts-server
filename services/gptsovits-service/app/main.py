import os

from bobogen_service_kit.app import create_service_app

from app.handler import GPTSoVITSHandler


def create_app(test_mode: bool = False):
    handler = GPTSoVITSHandler(test_mode=test_mode)
    app = create_service_app(
        "gptsovits-service",
        handler,
        api_key=os.environ.get("BOBOGEN_API_KEY") or os.environ.get("LOCAL_TTS_API_KEY"),
    )

    @app.post("/v1/warmup")
    async def warmup():
        return await handler.warmup()

    return app
