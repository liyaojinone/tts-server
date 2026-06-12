from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    root_dir: str
    cwd: str
    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)
    startup_timeout_ms: int = 90000
    request_timeout_ms: int = 180000
    idle_shutdown_seconds: int = 0


class NetworkConfig(BaseModel):
    host: str
    port: int
    base_url: str
    healthcheck_path: str = "/health"


class CapabilityConfig(BaseModel):
    voices: bool = True
    synthesize: bool = True
    clone: bool = False
    stream: bool = False


class VoiceConfig(BaseModel):
    voice_id: str
    name: str
    language: list[str] = Field(default_factory=list)
    gender: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ProviderConfig(BaseModel):
    provider_id: str
    model_id: str | None = None
    provider_type: str
    display_name: str
    enabled: bool = True
    tasks: list[str] = Field(default_factory=list)
    runtime: RuntimeConfig
    network: NetworkConfig
    capabilities: CapabilityConfig
    voices: list[VoiceConfig] = Field(default_factory=list)
    mapping: dict = Field(default_factory=dict)
