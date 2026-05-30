from dataclasses import dataclass
from datetime import datetime


@dataclass
class ProviderRuntimeState:
    provider_id: str
    status: str
    pid: int | None = None
    port: int | None = None
    started_at: datetime | None = None
    last_health_at: datetime | None = None
    last_used_at: datetime | None = None
    last_error: str | None = None
    startup_attempts: int = 0
