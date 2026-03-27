from typing import Protocol

from neocortex.ingestion.models import IngestionResult


class IngestionProcessor(Protocol):
    """Abstract interface for ingestion processing backends."""

    async def process_text(self, agent_id: str, text: str, metadata: dict) -> IngestionResult: ...

    async def process_document(
        self, agent_id: str, filename: str, content: bytes, content_type: str, metadata: dict
    ) -> IngestionResult: ...

    async def process_events(self, agent_id: str, events: list[dict], metadata: dict) -> IngestionResult: ...
