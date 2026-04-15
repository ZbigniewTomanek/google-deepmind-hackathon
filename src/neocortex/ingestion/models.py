from typing import Literal

from pydantic import BaseModel, Field


class TextIngestionRequest(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    target_graph: str | None = Field(
        default=None,
        description="Target shared graph schema. If omitted, stores to agent's personal graph.",
    )
    session_id: str | None = Field(
        default=None,
        description="Conversation/session grouping id. If omitted, one UUID is generated per ingestion request.",
    )
    force: bool = Field(
        default=False,
        description="If true, skip dedup check and ingest even if content was already processed.",
    )


class EventsIngestionRequest(BaseModel):
    events: list[dict] = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    target_graph: str | None = Field(
        default=None,
        description="Target shared graph schema. If omitted, stores to agent's personal graph.",
    )
    session_id: str | None = Field(
        default=None,
        description="Conversation/session grouping id. If omitted, one UUID is generated per ingestion request.",
    )
    force: bool = Field(
        default=False,
        description="If true, skip dedup check and ingest even if content was already processed.",
    )


class IngestionResult(BaseModel):
    status: Literal["stored", "failed", "partial", "skipped"]
    episodes_created: int
    message: str
    content_hash: str | None = None
    existing_episode_id: int | None = None


class HashCheckRequest(BaseModel):
    hashes: list[str] = Field(min_length=1, max_length=500)
    target_graph: str | None = Field(
        default=None,
        description="Check against a specific graph schema. If omitted, checks personal graph.",
    )


class HashCheckResult(BaseModel):
    existing: dict[str, int]  # {hash: episode_id} for hashes that exist
    missing: list[str]  # hashes not found
