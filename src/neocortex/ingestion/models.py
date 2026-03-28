from typing import Literal

from pydantic import BaseModel, Field


class TextIngestionRequest(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    target_graph: str | None = Field(
        default=None,
        description="Target shared graph schema. If omitted, stores to agent's personal graph.",
    )


class EventsIngestionRequest(BaseModel):
    events: list[dict] = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    target_graph: str | None = Field(
        default=None,
        description="Target shared graph schema. If omitted, stores to agent's personal graph.",
    )


class IngestionResult(BaseModel):
    status: Literal["stored", "failed", "partial"]
    episodes_created: int
    message: str
