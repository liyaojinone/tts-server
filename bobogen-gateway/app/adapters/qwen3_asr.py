import httpx

from app.adapters.base import BaseProviderAdapter
from app.schemas.generate import GenerateRequest
from app.services.generate_result import JsonResult


class Qwen3ASRAdapter(BaseProviderAdapter):
    provider_type = "qwen3-asr"

    def path_for_generate_task(self, task: str) -> str:
        if task == "asr.transcribe":
            return "/v1/transcribe"
        if task == "audio.align":
            return "/v1/align"
        raise ValueError(f"Unsupported Qwen3 generation task: {task}")

    async def generate(self, provider, request: GenerateRequest) -> JsonResult:
        timeout = provider.runtime.request_timeout_ms / 1000
        async with httpx.AsyncClient(base_url=provider.network.base_url, timeout=timeout, trust_env=False) as client:
            response = await client.post(self.path_for_generate_task(request.task), json=request.model_dump(mode="json"))
            response.raise_for_status()
        return JsonResult(payload=response.json())
