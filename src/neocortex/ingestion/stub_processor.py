from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from neocortex.db.protocol import MemoryRepository
from neocortex.ingestion.models import IngestionResult

if TYPE_CHECKING:
    from neocortex.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class StubProcessor:
    """Stub ingestion processor that stores raw episodes via MemoryRepository.

    Note: ``metadata`` is accepted but intentionally not persisted — a future
    ``ExtractionPipeline`` implementation will handle metadata propagation.
    """

    def __init__(self, repo: MemoryRepository, embeddings: EmbeddingService | None = None) -> None:
        self._repo = repo
        self._embeddings = embeddings

    async def _embed_episode(self, episode_id: int, text: str, agent_id: str) -> None:
        if self._embeddings is None:
            return
        vector = await self._embeddings.embed(text)
        if vector:
            await self._repo.update_episode_embedding(episode_id, vector, agent_id)

    async def process_text(self, agent_id: str, text: str, metadata: dict) -> IngestionResult:
        episode_id = await self._repo.store_episode(agent_id, text, source_type="ingestion_text")
        await self._embed_episode(episode_id, text, agent_id)
        return IngestionResult(
            status="stored",
            episodes_created=1,
            message="Text stored as episode",
        )

    async def process_document(
        self, agent_id: str, filename: str, content: bytes, content_type: str, metadata: dict
    ) -> IngestionResult:
        text = content.decode("utf-8", errors="replace")
        episode_id = await self._repo.store_episode(agent_id, text, source_type="ingestion_document")
        await self._embed_episode(episode_id, text, agent_id)
        return IngestionResult(
            status="stored",
            episodes_created=1,
            message=f"Document '{filename}' stored as episode",
        )

    async def process_events(self, agent_id: str, events: list[dict], metadata: dict) -> IngestionResult:
        stored = 0
        for event in events:
            try:
                event_text = json.dumps(event)
                episode_id = await self._repo.store_episode(agent_id, event_text, source_type="ingestion_event")
                await self._embed_episode(episode_id, event_text, agent_id)
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
