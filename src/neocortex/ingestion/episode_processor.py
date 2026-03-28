from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import TYPE_CHECKING

import procrastinate
from loguru import logger

from neocortex.db.protocol import MemoryRepository
from neocortex.ingestion.media_models import MediaIngestionResult, MediaRef
from neocortex.ingestion.models import IngestionResult

if TYPE_CHECKING:
    from neocortex.embedding_service import EmbeddingService
    from neocortex.ingestion.media_compressor import CompressedMedia, MediaCompressor
    from neocortex.ingestion.media_description import MediaDescription
    from neocortex.ingestion.media_description_mock import MockMediaDescriptionService
    from neocortex.ingestion.media_store import MediaFileStore


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
        # Media services
        media_store: MediaFileStore | None = None,
        media_compressor: MediaCompressor | None = None,
        media_describer: MockMediaDescriptionService | None = None,
    ) -> None:
        self._repo = repo
        self._embeddings = embeddings
        self._job_app = job_app
        self._extraction_enabled = extraction_enabled
        self._media_store = media_store
        self._media_compressor = media_compressor
        self._media_describer = media_describer

    async def _embed_episode(self, episode_id: int, text: str, agent_id: str, target_schema: str | None = None) -> None:
        if self._embeddings is None:
            return
        vector = await self._embeddings.embed(text)
        if vector:
            await self._repo.update_episode_embedding(episode_id, vector, agent_id, target_schema=target_schema)

    async def _enqueue_extraction(self, agent_id: str, episode_id: int, target_schema: str | None = None) -> int | None:
        if not self._job_app or not self._extraction_enabled:
            return None
        job_id = await self._job_app.configure_task("extract_episode").defer_async(
            agent_id=agent_id, episode_ids=[episode_id], target_schema=target_schema
        )
        logger.bind(action_log=True).info(
            "extraction_enqueued",
            job_id=job_id,
            episode_id=episode_id,
            agent_id=agent_id,
            target_schema=target_schema,
            source="ingestion",
        )
        return job_id

    async def _store_episode(self, agent_id: str, text: str, source_type: str, target_schema: str | None = None) -> int:
        if target_schema:
            return await self._repo.store_episode_to(agent_id, target_schema, text, source_type=source_type)
        return await self._repo.store_episode(agent_id, text, source_type=source_type)

    async def process_text(
        self, agent_id: str, text: str, metadata: dict, target_schema: str | None = None
    ) -> IngestionResult:
        episode_id = await self._store_episode(agent_id, text, "ingestion_text", target_schema)
        await self._embed_episode(episode_id, text, agent_id, target_schema)
        await self._enqueue_extraction(agent_id, episode_id, target_schema)
        return IngestionResult(
            status="stored",
            episodes_created=1,
            message="Text stored as episode",
        )

    async def process_document(
        self,
        agent_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult:
        text = content.decode("utf-8", errors="replace")
        episode_id = await self._store_episode(agent_id, text, "ingestion_document", target_schema)
        await self._embed_episode(episode_id, text, agent_id, target_schema)
        await self._enqueue_extraction(agent_id, episode_id, target_schema)
        return IngestionResult(
            status="stored",
            episodes_created=1,
            message=f"Document '{filename}' stored as episode",
        )

    async def process_events(
        self,
        agent_id: str,
        events: list[dict],
        metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult:
        stored = 0
        for event in events:
            try:
                event_text = json.dumps(event)
                episode_id = await self._store_episode(agent_id, event_text, "ingestion_event", target_schema)
                await self._embed_episode(episode_id, event_text, agent_id, target_schema)
                await self._enqueue_extraction(agent_id, episode_id, target_schema)
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

    async def process_audio(
        self,
        agent_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict,
        target_schema: str | None = None,
    ) -> MediaIngestionResult:
        """Compress audio -> describe via Gemini -> store file -> store episode."""
        if self._media_compressor is None:
            return MediaIngestionResult(status="failed", episodes_created=0, message="ffmpeg not available")

        describer = self._media_describer
        if describer is None:
            from neocortex.ingestion.media_description_mock import MockMediaDescriptionService

            describer = MockMediaDescriptionService()

        raw_path: str | None = None
        try:
            # 1. Write raw upload to temp file
            suffix = os.path.splitext(filename)[1] or ".bin"
            fd, raw_path = tempfile.mkstemp(suffix=suffix)
            os.write(fd, content)
            os.close(fd)

            # 2. Compress
            _, compressed_path = tempfile.mkstemp(suffix=".ogg")
            os.close(_)
            compressed = await self._media_compressor.compress_audio(raw_path, compressed_path)

            # 3. Describe
            context = metadata.get("context", "")
            description = await describer.describe_audio(compressed.path, compressed.mime_type, context=context)

            # 4. Save to media store
            media_ref = None
            if self._media_store is not None:
                media_ref = await self._media_store.save(
                    agent_id=agent_id,
                    source_path=compressed.path,
                    extension="ogg",
                    original_filename=filename,
                    content_type=content_type,
                    duration_seconds=compressed.duration_seconds,
                )

            # 5. Build episode text with embedded metadata
            episode_text = self._build_episode_text(
                media_type="audio",
                filename=filename,
                description=description,
                media_ref=media_ref,
                compressed=compressed,
            )

            # 6-8. Store, embed, enqueue
            episode_id = await self._store_episode(agent_id, episode_text, "ingestion_audio", target_schema)
            await self._embed_episode(episode_id, episode_text, agent_id, target_schema)
            await self._enqueue_extraction(agent_id, episode_id, target_schema)

            logger.bind(action_log=True).info(
                "media_ingested",
                media_type="audio",
                agent_id=agent_id,
                filename=filename,
                episode_id=episode_id,
                media_ref=media_ref.relative_path if media_ref else None,
            )

            return MediaIngestionResult(
                status="stored",
                episodes_created=1,
                message=f"Audio '{filename}' processed and stored as episode",
                media_ref=media_ref,
            )
        except Exception:
            logger.opt(exception=True).error("Audio ingestion failed for {}", filename)
            return MediaIngestionResult(
                status="failed",
                episodes_created=0,
                message=f"Audio ingestion failed for '{filename}'",
            )
        finally:
            if raw_path is not None:
                with contextlib.suppress(OSError):
                    os.unlink(raw_path)

    async def process_video(
        self,
        agent_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict,
        target_schema: str | None = None,
    ) -> MediaIngestionResult:
        """Compress video -> describe via Gemini -> store file -> store episode."""
        if self._media_compressor is None:
            return MediaIngestionResult(status="failed", episodes_created=0, message="ffmpeg not available")

        describer = self._media_describer
        if describer is None:
            from neocortex.ingestion.media_description_mock import MockMediaDescriptionService

            describer = MockMediaDescriptionService()

        raw_path: str | None = None
        try:
            # 1. Write raw upload to temp file
            suffix = os.path.splitext(filename)[1] or ".bin"
            fd, raw_path = tempfile.mkstemp(suffix=suffix)
            os.write(fd, content)
            os.close(fd)

            # 2. Compress
            _, compressed_path = tempfile.mkstemp(suffix=".mp4")
            os.close(_)
            compressed = await self._media_compressor.compress_video(raw_path, compressed_path)

            # 3. Describe
            context = metadata.get("context", "")
            description = await describer.describe_video(compressed.path, compressed.mime_type, context=context)

            # 4. Save to media store
            media_ref = None
            if self._media_store is not None:
                media_ref = await self._media_store.save(
                    agent_id=agent_id,
                    source_path=compressed.path,
                    extension="mp4",
                    original_filename=filename,
                    content_type=content_type,
                    duration_seconds=compressed.duration_seconds,
                )

            # 5. Build episode text with embedded metadata
            episode_text = self._build_episode_text(
                media_type="video",
                filename=filename,
                description=description,
                media_ref=media_ref,
                compressed=compressed,
            )

            # 6-8. Store, embed, enqueue
            episode_id = await self._store_episode(agent_id, episode_text, "ingestion_video", target_schema)
            await self._embed_episode(episode_id, episode_text, agent_id, target_schema)
            await self._enqueue_extraction(agent_id, episode_id, target_schema)

            logger.bind(action_log=True).info(
                "media_ingested",
                media_type="video",
                agent_id=agent_id,
                filename=filename,
                episode_id=episode_id,
                media_ref=media_ref.relative_path if media_ref else None,
            )

            return MediaIngestionResult(
                status="stored",
                episodes_created=1,
                message=f"Video '{filename}' processed and stored as episode",
                media_ref=media_ref,
            )
        except Exception:
            logger.opt(exception=True).error("Video ingestion failed for {}", filename)
            return MediaIngestionResult(
                status="failed",
                episodes_created=0,
                message=f"Video ingestion failed for '{filename}'",
            )
        finally:
            if raw_path is not None:
                with contextlib.suppress(OSError):
                    os.unlink(raw_path)

    @staticmethod
    def _build_episode_text(
        media_type: str,
        filename: str,
        description: MediaDescription,
        media_ref: MediaRef | None,
        compressed: CompressedMedia,
    ) -> str:
        """Build episode text with embedded structured metadata."""
        label = "Audio" if media_type == "audio" else "Video"
        lines = [
            f"[{label}: {filename}]",
            "",
            description.text,
            "",
            "---",
            "Media metadata:",
        ]

        if media_ref is not None:
            lines.append(f"- media_ref: {media_ref.relative_path}")
            lines.append(f"- original_filename: {media_ref.original_filename}")
            lines.append(f"- content_type: {media_ref.content_type}")
            lines.append(f"- compressed_size: {media_ref.compressed_size}")

        lines.append(f"- media_type: {media_type}")
        lines.append(f"- duration_seconds: {compressed.duration_seconds}")
        lines.append(f"- description_model: {description.model}")
        lines.append(f"- description_tokens: {description.token_count}")

        return "\n".join(lines) + "\n"


# Backward-compatible alias
StubProcessor = EpisodeProcessor
