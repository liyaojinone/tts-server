from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


JobStatus = Literal[
    "queued",
    "running",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
]
JobPhase = Literal[
    "preparing",
    "decoding",
    "separating",
    "postprocessing",
    "encoding",
    "validating",
]
ArtifactRole = Literal["dialogue", "background"]


class JobProgress(BaseModel):
    phase: JobPhase
    fraction: float = Field(ge=0.0, le=1.0)
    message: str | None = None


class JobArtifact(BaseModel):
    id: str
    role: ArtifactRole
    filename: str
    content_type: str = "audio/wav"
    size_bytes: int = Field(ge=0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    frame_count: int = Field(ge=0)
    sha256: str


class JobError(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class JobResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    model: str
    task: str
    status: JobStatus
    progress: JobProgress
    artifacts: list[JobArtifact] = Field(default_factory=list)
    error: JobError | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GatewayJobRecord(BaseModel):
    id: str
    provider_id: str
    model: str
    task: str
    job_dir: str
