from __future__ import annotations

import json
from typing import TYPE_CHECKING

import procrastinate
from loguru import logger

from neocortex.db.protocol import MemoryRepository
from neocortex.ingestion.models import IngestionResult

if TYPE_CHECKING:
    from neocortex.embedding_service import EmbeddingService


class EpisodeProcessor:
    """Ingestion processor that stores episodes and enqueues extraction jobs.

    After each episode is stored and embedded, an async extraction job is
    deferred via Procrastinate (if a job_app is provided and extraction is
    enabled). The extraction worker in the MCP server process picks up these
    jobs.
    """

    def __init__(
        self,
        repo: MemoryRepository,
        embeddings: EmbeddingService | None = None,
        job_app: procrastinate.App | None = None,
        extraction_enabled: bool = True,
    ) -> None:
        self._repo = repo
        self._embeddings = embeddings
        self._job_app = job_app
        self._extraction_enabled = extraction_enabled

    async def _embed_episode(self, episode_id: int, text: str, agent_id: str) -> None:
        if self._embeddings is None:
            return
        vector = await self._embeddings.embed(text)
        if vector:
            await self._repo.update_episode_embedding(episode_id, vector, agent_id)

    async def _enqueue_extraction(self, agent_id: str, episode_id: int) -> int | None:
        if not self._job_app or not self._extraction_enabled:
            return None
        job_id = await self._job_app.configure_task("extract_episode").defer_async(
            agent_id=agent_id, episode_ids=[episode_id]
        )
        logger.bind(action_log=True).info(
            "extraction_enqueued",
            job_id=job_id,
            episode_id=episode_id,
            agent_id=agent_id,
            source="ingestion",
        )
        return job_id

    async def process_text(self, agent_id: str, text: str, metadata: dict) -> IngestionResult:
        episode_id = await self._repo.store_episode(agent_id, text, source_type="ingestion_text")
        await self._embed_episode(episode_id, text, agent_id)
        await self._enqueue_extraction(agent_id, episode_id)
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
        await self._enqueue_extraction(agent_id, episode_id)
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
                await self._enqueue_extraction(agent_id, episode_id)
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


# Backward-compatible alias
StubProcessor = EpisodeProcessor
