from pydantic import BaseModel, Field


class VoiceResponse(BaseModel):
    voice_id: str
    name: str
    language: list[str] = Field(default_factory=list)
    gender: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class VoicesResponse(BaseModel):
    voices: list[VoiceResponse]
    total: int
    page: int = 1
    page_size: int = 100
