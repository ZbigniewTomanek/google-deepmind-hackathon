import json
from unittest.mock import AsyncMock

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.ingestion.stub_processor import StubProcessor


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def processor(repo: InMemoryRepository) -> StubProcessor:
    return StubProcessor(repo=repo)


@pytest.mark.asyncio
async def test_process_text_stores_one_episode(processor, repo):
    result = await processor.process_text("agent-a", "hello world", {})

    assert result.status == "stored"
    assert result.episodes_created == 1

    stats = await repo.get_stats(agent_id="agent-a")
    assert stats.total_episodes == 1

    items = await repo.recall("hello", agent_id="agent-a")
    assert len(items) == 1
    assert items[0].source == "ingestion_text"


@pytest.mark.asyncio
async def test_process_document_stores_raw_content(processor, repo):
    content = b"# My Document\n\nSome content here."
    result = await processor.process_document("agent-a", "readme.md", content, "text/markdown", {})

    assert result.status == "stored"
    assert result.episodes_created == 1
    assert "readme.md" in result.message

    items = await repo.recall("My Document", agent_id="agent-a")
    assert len(items) == 1
    assert items[0].source == "ingestion_document"
    assert items[0].content == content.decode("utf-8")


@pytest.mark.asyncio
async def test_process_document_handles_non_utf8(processor, repo):
    content = b"\xff\xfe invalid bytes"
    result = await processor.process_document("agent-a", "binary.bin", content, "text/plain", {})

    assert result.status == "stored"
    assert result.episodes_created == 1


@pytest.mark.asyncio
async def test_process_events_stores_all(processor, repo):
    events = [{"type": "click", "ts": 1}, {"type": "view", "ts": 2}, {"type": "submit", "ts": 3}]
    result = await processor.process_events("agent-a", events, {})

    assert result.status == "stored"
    assert result.episodes_created == 3

    stats = await repo.get_stats(agent_id="agent-a")
    assert stats.total_episodes == 3

    items = await repo.recall("click", agent_id="agent-a")
    assert len(items) == 1
    assert items[0].source == "ingestion_event"
    assert json.loads(items[0].content) == {"type": "click", "ts": 1}


@pytest.mark.asyncio
async def test_process_events_partial_failure():
    """When store_episode raises mid-batch, result is partial."""
    repo = AsyncMock()
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise RuntimeError("DB connection lost")
        return call_count

    repo.store_episode = AsyncMock(side_effect=side_effect)

    processor = StubProcessor(repo=repo)
    events = [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]
    result = await processor.process_events("agent-a", events, {})

    assert result.status == "partial"
    assert result.episodes_created == 2
    assert "2/4" in result.message
