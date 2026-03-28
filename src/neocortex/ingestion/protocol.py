from typing import Protocol

from neocortex.ingestion.media_models import MediaIngestionResult
from neocortex.ingestion.models import IngestionResult


class IngestionProcessor(Protocol):
    """Abstract interface for ingestion processing backends."""

    async def process_text(
        self,
        agent_id: str,
        text: str,
        metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult: ...

    async def process_document(
        self,
        agent_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult: ...

    async def process_events(
        self,
        agent_id: str,
        events: list[dict],
        metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult: ...

    async def process_audio(
        self,
        agent_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict,
        target_schema: str | None = None,
    ) -> MediaIngestionResult: ...

    async def process_video(
        self,
        agent_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict,
        target_schema: str | None = None,
    ) -> MediaIngestionResult: ...
