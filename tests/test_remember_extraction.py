"""Tests for extraction job wiring in remember tool and ingestion processor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.mcp_settings import MCPSettings
from neocortex.schemas.memory import RememberResult


# ── Fixtures ──


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def settings() -> MCPSettings:
    return MCPSettings(mock_db=True, extraction_enabled=True)


# ── Remember tool tests ──


@pytest.mark.asyncio
async def test_remember_skips_extraction_when_no_job_app(repo: InMemoryRepository, settings: MCPSettings):
    """Without job_app, remember stores episode but doesn't enqueue extraction."""
    ctx = MagicMock()
    ctx.lifespan_context = {
        "repo": repo,
        "settings": settings,
        "embeddings": None,
        "job_app": None,
    }

    # Need to mock get_agent_id_from_context
    with patch("neocortex.tools.remember.get_agent_id_from_context", return_value="test-agent"):
        from neocortex.tools.remember import remember

        result = await remember("Test memory", ctx=ctx)

    assert isinstance(result, RememberResult)
    assert result.status == "stored"
    assert result.episode_id > 0
    assert result.extraction_job_id is None


@pytest.mark.asyncio
async def test_remember_skips_extraction_when_disabled(repo: InMemoryRepository):
    """With extraction_enabled=False, no job is enqueued even with job_app."""
    settings = MCPSettings(mock_db=True, extraction_enabled=False)
    ctx = MagicMock()
    ctx.lifespan_context = {
        "repo": repo,
        "settings": settings,
        "embeddings": None,
        "job_app": MagicMock(),  # job_app present but extraction disabled
    }

    with patch("neocortex.tools.remember.get_agent_id_from_context", return_value="test-agent"):
        from neocortex.tools.remember import remember

        result = await remember("Test memory", ctx=ctx)

    assert result.extraction_job_id is None


@pytest.mark.asyncio
async def test_remember_enqueues_extraction_job(repo: InMemoryRepository, settings: MCPSettings):
    """With job_app and extraction enabled, remember defers an extraction job."""
    mock_job_app = MagicMock()

    ctx = MagicMock()
    ctx.lifespan_context = {
        "repo": repo,
        "settings": settings,
        "embeddings": None,
        "job_app": mock_job_app,
    }

    # Mock the defer_async call on the task
    with (
        patch("neocortex.tools.remember.get_agent_id_from_context", return_value="test-agent"),
        patch("neocortex.jobs.tasks.extract_episode.defer_async", new_callable=AsyncMock, return_value=42) as mock_defer,
    ):
        from neocortex.tools.remember import remember

        result = await remember("Test memory about serotonin", ctx=ctx)

    assert result.status == "stored"
    assert result.episode_id > 0
    assert result.extraction_job_id == 42

    # Verify defer was called with the correct arguments
    mock_defer.assert_called_once_with(
        mock_job_app,
        agent_id="test-agent",
        episode_ids=[result.episode_id],
    )


# ── EpisodeProcessor tests ──


@pytest.mark.asyncio
async def test_processor_skips_extraction_when_no_job_app(repo: InMemoryRepository):
    """EpisodeProcessor without job_app stores but doesn't enqueue."""
    processor = EpisodeProcessor(repo=repo, job_app=None)
    result = await processor.process_text("agent-a", "hello world", {})

    assert result.status == "stored"
    assert result.episodes_created == 1


@pytest.mark.asyncio
async def test_processor_skips_extraction_when_disabled(repo: InMemoryRepository):
    """EpisodeProcessor with extraction_enabled=False doesn't enqueue."""
    mock_job_app = MagicMock()
    processor = EpisodeProcessor(repo=repo, job_app=mock_job_app, extraction_enabled=False)
    result = await processor.process_text("agent-a", "hello world", {})

    assert result.status == "stored"
    assert result.episodes_created == 1


@pytest.mark.asyncio
async def test_processor_enqueues_extraction_on_text(repo: InMemoryRepository):
    """EpisodeProcessor with job_app defers extraction after storing text."""
    mock_job_app = MagicMock()

    with patch(
        "neocortex.jobs.tasks.extract_episode.defer_async",
        new_callable=AsyncMock,
        return_value=99,
    ) as mock_defer:
        processor = EpisodeProcessor(repo=repo, job_app=mock_job_app, extraction_enabled=True)
        result = await processor.process_text("agent-a", "serotonin modulates mood", {})

    assert result.status == "stored"
    assert result.episodes_created == 1
    mock_defer.assert_called_once()
    call_kwargs = mock_defer.call_args
    assert call_kwargs[1]["agent_id"] == "agent-a"
    assert len(call_kwargs[1]["episode_ids"]) == 1


@pytest.mark.asyncio
async def test_processor_enqueues_extraction_on_document(repo: InMemoryRepository):
    """EpisodeProcessor defers extraction after storing a document."""
    mock_job_app = MagicMock()

    with patch(
        "neocortex.jobs.tasks.extract_episode.defer_async",
        new_callable=AsyncMock,
        return_value=101,
    ) as mock_defer:
        processor = EpisodeProcessor(repo=repo, job_app=mock_job_app, extraction_enabled=True)
        result = await processor.process_document(
            "agent-a", "doc.txt", b"Medical text about SSRIs", "text/plain", {}
        )

    assert result.status == "stored"
    mock_defer.assert_called_once()


@pytest.mark.asyncio
async def test_processor_enqueues_extraction_on_events(repo: InMemoryRepository):
    """EpisodeProcessor defers extraction for each event in a batch."""
    mock_job_app = MagicMock()

    with patch(
        "neocortex.jobs.tasks.extract_episode.defer_async",
        new_callable=AsyncMock,
        return_value=200,
    ) as mock_defer:
        processor = EpisodeProcessor(repo=repo, job_app=mock_job_app, extraction_enabled=True)
        events = [{"type": "note", "text": "fact 1"}, {"type": "note", "text": "fact 2"}]
        result = await processor.process_events("agent-a", events, {})

    assert result.status == "stored"
    assert result.episodes_created == 2
    assert mock_defer.call_count == 2


@pytest.mark.asyncio
async def test_processor_backward_compat_stub_import():
    """StubProcessor import from old module still works."""
    from neocortex.ingestion.stub_processor import StubProcessor

    assert StubProcessor is EpisodeProcessor
