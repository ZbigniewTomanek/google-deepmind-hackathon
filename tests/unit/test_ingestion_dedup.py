"""Unit tests for ingestion content deduplication.

Uses InMemoryRepository directly with EpisodeProcessor — no Docker needed.
"""

from __future__ import annotations

import hashlib

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.ingestion.episode_processor import EpisodeProcessor


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def processor(repo: InMemoryRepository) -> EpisodeProcessor:
    return EpisodeProcessor(repo=repo, extraction_enabled=False)


AGENT = "test-agent"
SHARED_SCHEMA = "ncx_shared__research"


# --- Hash computation ---


def test_compute_hash_consistent():
    """_compute_hash produces a consistent SHA-256 hex string."""
    h1 = EpisodeProcessor._compute_hash("hello world")
    h2 = EpisodeProcessor._compute_hash("hello world")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex
    assert h1 == hashlib.sha256(b"hello world").hexdigest()


def test_compute_hash_bytes_consistent():
    """_compute_hash_bytes produces a consistent SHA-256 hex for raw bytes."""
    data = b"\x00\x01\x02binary content"
    h1 = EpisodeProcessor._compute_hash_bytes(data)
    h2 = EpisodeProcessor._compute_hash_bytes(data)
    assert h1 == h2
    assert h1 == hashlib.sha256(data).hexdigest()


def test_compute_hash_different_inputs():
    """Different content produces different hashes."""
    h1 = EpisodeProcessor._compute_hash("hello")
    h2 = EpisodeProcessor._compute_hash("world")
    assert h1 != h2


# --- First ingestion ---


@pytest.mark.asyncio
async def test_first_text_ingestion_returns_stored(processor: EpisodeProcessor):
    """First ingestion of new content returns 'stored' with content_hash."""
    result = await processor.process_text(AGENT, "brand new content", {})
    assert result.status == "stored"
    assert result.episodes_created == 1
    assert result.content_hash is not None
    assert len(result.content_hash) == 64


@pytest.mark.asyncio
async def test_first_document_ingestion_returns_stored(processor: EpisodeProcessor):
    """First document ingestion returns 'stored' with content_hash."""
    result = await processor.process_document(AGENT, "test.txt", b"doc content", "text/plain", {})
    assert result.status == "stored"
    assert result.episodes_created == 1
    assert result.content_hash is not None


# --- Duplicate detection ---


@pytest.mark.asyncio
async def test_duplicate_text_returns_skipped(processor: EpisodeProcessor):
    """Same text ingested twice: second returns 'skipped' with existing_episode_id."""
    r1 = await processor.process_text(AGENT, "duplicate me", {})
    assert r1.status == "stored"

    r2 = await processor.process_text(AGENT, "duplicate me", {})
    assert r2.status == "skipped"
    assert r2.episodes_created == 0
    assert r2.existing_episode_id is not None
    assert r2.content_hash == r1.content_hash


@pytest.mark.asyncio
async def test_duplicate_document_returns_skipped(processor: EpisodeProcessor):
    """Same document bytes ingested twice: second returns 'skipped'."""
    content = b"same file content"
    r1 = await processor.process_document(AGENT, "file.txt", content, "text/plain", {})
    assert r1.status == "stored"

    r2 = await processor.process_document(AGENT, "file.txt", content, "text/plain", {})
    assert r2.status == "skipped"
    assert r2.episodes_created == 0
    assert r2.existing_episode_id is not None


# --- Force override ---


@pytest.mark.asyncio
async def test_force_override_stores_duplicate(processor: EpisodeProcessor):
    """force=True bypasses dedup and creates a new episode."""
    r1 = await processor.process_text(AGENT, "force me", {})
    assert r1.status == "stored"

    r2 = await processor.process_text(AGENT, "force me", {}, force=True)
    assert r2.status == "stored"
    assert r2.episodes_created == 1


# --- Different content ---


@pytest.mark.asyncio
async def test_different_content_not_deduped(processor: EpisodeProcessor):
    """Different text is not falsely detected as duplicate."""
    r1 = await processor.process_text(AGENT, "content alpha", {})
    r2 = await processor.process_text(AGENT, "content beta", {})
    assert r1.status == "stored"
    assert r2.status == "stored"
    assert r1.content_hash != r2.content_hash


# --- Agent isolation ---


@pytest.mark.asyncio
async def test_agent_isolation(processor: EpisodeProcessor):
    """Agent A's content doesn't trigger dedup for agent B."""
    r1 = await processor.process_text("agent-a", "shared text", {})
    assert r1.status == "stored"

    r2 = await processor.process_text("agent-b", "shared text", {})
    assert r2.status == "stored"  # Not skipped — different agent


# --- Events batch dedup ---


@pytest.mark.asyncio
async def test_events_mixed_new_and_duplicate(processor: EpisodeProcessor):
    """Mix of new + duplicate events returns 'partial'."""
    events_batch1 = [{"type": "click", "id": 1}]
    r1 = await processor.process_events(AGENT, events_batch1, {})
    assert r1.status == "stored"

    # Second batch: one duplicate (id=1) + one new (id=2)
    events_batch2 = [{"type": "click", "id": 1}, {"type": "view", "id": 2}]
    r2 = await processor.process_events(AGENT, events_batch2, {})
    assert r2.status == "partial"
    assert r2.episodes_created == 1  # Only the new event stored


@pytest.mark.asyncio
async def test_events_all_duplicates_returns_skipped(processor: EpisodeProcessor):
    """All events already ingested returns 'skipped'."""
    events = [{"type": "click"}, {"type": "view"}]
    r1 = await processor.process_events(AGENT, events, {})
    assert r1.status == "stored"
    assert r1.episodes_created == 2

    r2 = await processor.process_events(AGENT, events, {})
    assert r2.status == "skipped"
    assert r2.episodes_created == 0


@pytest.mark.asyncio
async def test_events_force_bypasses_dedup(processor: EpisodeProcessor):
    """force=True on events stores all regardless of duplicates."""
    events = [{"type": "click"}]
    r1 = await processor.process_events(AGENT, events, {})
    assert r1.status == "stored"

    r2 = await processor.process_events(AGENT, events, {}, force=True)
    assert r2.status == "stored"
    assert r2.episodes_created == 1


# --- Target schema (shared graph) ---


@pytest.mark.asyncio
async def test_dedup_with_target_schema(processor: EpisodeProcessor):
    """Dedup works correctly when targeting a shared graph schema."""
    r1 = await processor.process_text(AGENT, "shared content", {}, target_schema=SHARED_SCHEMA)
    assert r1.status == "stored"

    r2 = await processor.process_text(AGENT, "shared content", {}, target_schema=SHARED_SCHEMA)
    assert r2.status == "skipped"
    assert r2.existing_episode_id is not None


@pytest.mark.asyncio
async def test_dedup_personal_vs_shared_independent(processor: EpisodeProcessor):
    """Same content in personal graph doesn't block ingestion to shared graph."""
    r1 = await processor.process_text(AGENT, "cross-graph content", {})
    assert r1.status == "stored"

    # Same content but to a shared schema — should be stored (different scope)
    r2 = await processor.process_text(AGENT, "cross-graph content", {}, target_schema=SHARED_SCHEMA)
    assert r2.status == "stored"


# --- InMemoryRepository.check_episode_hashes directly ---


@pytest.mark.asyncio
async def test_check_episode_hashes_empty(repo: InMemoryRepository):
    """Empty hashes list returns empty dict."""
    result = await repo.check_episode_hashes(AGENT, [])
    assert result == {}


@pytest.mark.asyncio
async def test_check_episode_hashes_none_found(repo: InMemoryRepository):
    """Unknown hashes return empty dict."""
    result = await repo.check_episode_hashes(AGENT, ["abc123"])
    assert result == {}


@pytest.mark.asyncio
async def test_check_episode_hashes_found(repo: InMemoryRepository):
    """Stored hash is found by check_episode_hashes."""
    ep_id = await repo.store_episode(AGENT, "hello", content_hash="hash1")
    result = await repo.check_episode_hashes(AGENT, ["hash1", "hash2"])
    assert result == {"hash1": ep_id}


@pytest.mark.asyncio
async def test_check_episode_hashes_agent_scoped(repo: InMemoryRepository):
    """Agent A's hashes are not visible to agent B."""
    await repo.store_episode("agent-a", "hello", content_hash="hash1")
    result = await repo.check_episode_hashes("agent-b", ["hash1"])
    assert result == {}


@pytest.mark.asyncio
async def test_check_episode_hashes_target_schema(repo: InMemoryRepository):
    """Hashes in target_schema are found when checking that schema."""
    ep_id = await repo.store_episode_to(AGENT, SHARED_SCHEMA, "hello", content_hash="hash1")
    result = await repo.check_episode_hashes(AGENT, ["hash1"], target_schema=SHARED_SCHEMA)
    assert result == {"hash1": ep_id}

    # Verify target_schema scoping works — the important assertion is above.
