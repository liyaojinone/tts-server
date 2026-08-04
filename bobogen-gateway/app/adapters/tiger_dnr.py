from collections.abc import AsyncIterator

import httpx

from app.adapters.base import BaseProviderAdapter
from app.core.exceptions import GatewayError, ProviderUnavailableError
from app.schemas.generate import GenerateRequest


class TigerDNRAdapter(BaseProviderAdapter):
    provider_type = "tiger-dnr"

    def _timeout(self, provider) -> float:
        return provider.runtime.request_timeout_ms / 1000

    async def _request(
        self,
        provider,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=provider.network.base_url,
                timeout=self._timeout(provider),
                trust_env=False,
            ) as client:
                return await client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(
                "TIGER-DnR provider is unavailable",
                {
                    "provider_id": provider.provider_id,
                    "reason": str(exc),
                },
                status_code=503,
            ) from exc

    async def _json_request(
        self,
        provider,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        response = await self._request(
            provider,
            method,
            path,
            **kwargs,
        )
        if response.is_error:
            self._raise_provider_error(response)
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise GatewayError(
                "TIGER-DnR provider returned invalid JSON",
                {
                    "provider_id": provider.provider_id,
                    "content_type": response.headers.get(
                        "content-type"
                    ),
                },
                status_code=502,
            ) from exc
        if not isinstance(payload, dict):
            raise GatewayError(
                "TIGER-DnR provider returned a non-object response",
                {"provider_id": provider.provider_id},
                status_code=502,
            )
        return payload

    def _raise_provider_error(self, response: httpx.Response) -> None:
        try:
            error = response.json().get("error", {})
        except (TypeError, ValueError):
            error = {}
        raise GatewayError(
            error.get("message")
            or f"Provider request failed with HTTP {response.status_code}",
            {
                "provider_error_code": error.get("code"),
                "provider_details": error.get("details") or {},
            },
            status_code=response.status_code,
        )

    async def create_job(
        self,
        provider,
        job_id: str,
        request: GenerateRequest,
    ) -> dict:
        return await self._json_request(
            provider,
            "POST",
            "/v1/jobs",
            json={
                "job_id": job_id,
                "request": request.model_dump(mode="json"),
            },
        )

    async def get_job(self, provider, job_id: str) -> dict:
        return await self._json_request(
            provider,
            "GET",
            f"/v1/jobs/{job_id}",
        )

    async def cancel_job(self, provider, job_id: str) -> dict:
        return await self._json_request(
            provider,
            "POST",
            f"/v1/jobs/{job_id}/cancel",
        )

    async def delete_job(self, provider, job_id: str) -> None:
        response = await self._request(
            provider,
            "DELETE",
            f"/v1/jobs/{job_id}",
        )
        if response.is_error:
            self._raise_provider_error(response)

    async def get_artifact(
        self,
        provider,
        job_id: str,
        artifact_id: str,
    ) -> dict:
        job = await self.get_job(provider, job_id)
        artifact = next(
            (
                item
                for item in job.get("artifacts", [])
                if item.get("id") == artifact_id
            ),
            None,
        )
        if artifact is None:
            raise GatewayError(
                f"Artifact not found: {artifact_id}",
                {"job_id": job_id, "artifact_id": artifact_id},
                status_code=404,
            )

        client = httpx.AsyncClient(
            base_url=provider.network.base_url,
            timeout=None,
            trust_env=False,
        )
        request = client.build_request(
            "GET",
            f"/v1/jobs/{job_id}/artifacts/{artifact_id}",
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.RequestError as exc:
            await client.aclose()
            raise ProviderUnavailableError(
                "TIGER-DnR provider is unavailable",
                {
                    "provider_id": provider.provider_id,
                    "reason": str(exc),
                },
                status_code=503,
            ) from exc
        except BaseException:
            await client.aclose()
            raise

        if response.is_error:
            try:
                await response.aread()
                self._raise_provider_error(response)
            finally:
                try:
                    await response.aclose()
                finally:
                    await client.aclose()

        async def stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                try:
                    await response.aclose()
                finally:
                    await client.aclose()

        return {
            "stream": stream(),
            "content_type": artifact["content_type"],
            "filename": artifact["filename"],
            "size_bytes": artifact["size_bytes"],
        }
