import json

from neocortex.db.protocol import MemoryRepository
from neocortex.ingestion.models import IngestionResult


class StubProcessor:
    """Stub ingestion processor that stores raw episodes via MemoryRepository."""

    def __init__(self, repo: MemoryRepository) -> None:
        self._repo = repo

    async def process_text(self, agent_id: str, text: str, metadata: dict) -> IngestionResult:
        await self._repo.store_episode(agent_id, text, source_type="ingestion_text")
        return IngestionResult(
            status="stored",
            episodes_created=1,
            message="Text stored as episode",
        )

    async def process_document(
        self, agent_id: str, filename: str, content: bytes, content_type: str, metadata: dict
    ) -> IngestionResult:
        text = content.decode("utf-8", errors="replace")
        await self._repo.store_episode(agent_id, text, source_type="ingestion_document")
        return IngestionResult(
            status="stored",
            episodes_created=1,
            message=f"Document '{filename}' stored as episode",
        )

    async def process_events(self, agent_id: str, events: list[dict], metadata: dict) -> IngestionResult:
        stored = 0
        for event in events:
            try:
                await self._repo.store_episode(agent_id, json.dumps(event), source_type="ingestion_event")
                stored += 1
            except Exception as exc:
                return IngestionResult(
                    status="partial",
                    episodes_created=stored,
                    message=f"Failed after {stored}/{len(events)} events: {exc}",
                )
        return IngestionResult(
            status="stored",
            episodes_created=stored,
            message=f"All {stored} events stored",
        )
