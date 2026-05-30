import asyncio
import os
import subprocess
from datetime import datetime

import httpx

from app.core.exceptions import ProviderDisabledError, ProviderNotFoundError, ProviderStartTimeoutError
from app.core.state import ProviderRuntimeState


class ProcessManager:
    def __init__(self, providers: dict):
        self.providers = providers
        self._states: dict[str, ProviderRuntimeState] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._locks = {provider_id: asyncio.Lock() for provider_id in providers}

    def get_state(self, provider_id: str) -> ProviderRuntimeState:
        provider = self.providers.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(f"Provider not found: {provider_id}", {"provider_id": provider_id})
        if provider_id not in self._states:
            self._states[provider_id] = ProviderRuntimeState(
                provider_id=provider_id,
                status="stopped",
                port=provider.network.port,
            )
        return self._states[provider_id]

    def list_states(self) -> list[ProviderRuntimeState]:
        return [self.get_state(provider_id) for provider_id in self.providers]

    async def ensure_started(self, provider_id: str) -> ProviderRuntimeState:
        provider = self.providers.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(f"Provider not found: {provider_id}", {"provider_id": provider_id})
        if not provider.enabled:
            raise ProviderDisabledError(f"Provider disabled: {provider_id}", {"provider_id": provider_id})
        async with self._locks[provider_id]:
            state = self.get_state(provider_id)
            if state.status == "healthy":
                state.last_used_at = datetime.now()
                return state
            return await self.start(provider_id)

    async def start(self, provider_id: str) -> ProviderRuntimeState:
        provider = self.providers[provider_id]
        state = self.get_state(provider_id)
        state.status = "starting"
        state.startup_attempts += 1
        state.pid = await self._launch_process(provider)
        state.started_at = datetime.now()
        healthy = await self._wait_until_healthy(provider_id)
        if not healthy:
            state.status = "failed"
            state.last_error = "healthcheck timeout"
            raise ProviderStartTimeoutError(
                f"Provider {provider_id} failed to become healthy within {provider.runtime.startup_timeout_ms} ms",
                {"provider_id": provider_id},
            )
        state.status = "healthy"
        state.last_health_at = datetime.now()
        state.last_used_at = datetime.now()
        return state

    async def stop(self, provider_id: str) -> None:
        process = self._processes.get(provider_id)
        if process is not None and process.poll() is None:
            process.terminate()
        state = self.get_state(provider_id)
        state.status = "stopped"

    async def restart(self, provider_id: str) -> ProviderRuntimeState:
        await self.stop(provider_id)
        return await self.start(provider_id)

    async def healthcheck(self, provider_id: str) -> bool:
        provider = self.providers[provider_id]
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"{provider.network.base_url}{provider.network.healthcheck_path}")
            return response.status_code == 200

    async def _wait_until_healthy(self, provider_id: str) -> bool:
        provider = self.providers[provider_id]
        timeout_seconds = provider.runtime.startup_timeout_ms / 1000
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                if await self.healthcheck(provider_id):
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.1)
        return False

    async def _launch_process(self, provider) -> int:
        env = os.environ.copy()
        env.update(provider.runtime.env)
        process = subprocess.Popen(
            provider.runtime.command,
            cwd=provider.runtime.cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes[provider.provider_id] = process
        return process.pid
