import json
import logging

from neocortex.db.protocol import MemoryRepository
from neocortex.ingestion.models import IngestionResult

logger = logging.getLogger(__name__)


class StubProcessor:
    """Stub ingestion processor that stores raw episodes via MemoryRepository.

    Note: ``metadata`` is accepted but intentionally not persisted — a future
    ``ExtractionPipeline`` implementation will handle metadata propagation.
    """

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
            except Exception:
                logger.exception("Event ingestion failed after %d/%d events", stored, len(events))
                return IngestionResult(
                    status="partial",
                    episodes_created=stored,
                    message=f"Failed after {stored}/{len(events)} events",
                )
        return IngestionResult(
            status="stored",
            episodes_created=stored,
            message=f"All {stored} events stored",
        )
