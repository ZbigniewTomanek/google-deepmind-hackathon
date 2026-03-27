from typing import Literal

from pydantic import BaseModel, Field


class TextIngestionRequest(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)


class EventsIngestionRequest(BaseModel):
    events: list[dict] = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)


class IngestionResult(BaseModel):
    status: Literal["stored", "failed", "partial"]
    episodes_created: int
    message: str
