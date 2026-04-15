"""Tests for episodic session tagging, neighbor expansion, and cluster sorting.

All tests run against InMemoryRepository — no Docker needed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from neocortex.db.adapter import _sort_session_clusters_chronologically
from neocortex.db.mock import InMemoryRepository
from neocortex.schemas.memory import RecallItem

AGENT = "test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


# ── Session tagging tests ──


@pytest.mark.anyio
async def test_store_episode_with_session_id(repo: InMemoryRepository) -> None:
    """Episodes stored with session_id retain it."""
    eid = await repo.store_episode(AGENT, "hello world", session_id="sess-1")
    ep = await repo.get_episode(AGENT, eid)
    assert ep is not None
    assert ep.session_id == "sess-1"


@pytest.mark.anyio
async def test_store_episode_without_session_id(repo: InMemoryRepository) -> None:
    """Episodes stored without session_id have None."""
    eid = await repo.store_episode(AGENT, "hello world")
    ep = await repo.get_episode(AGENT, eid)
    assert ep is not None
    assert ep.session_id is None


# ── Recall with expand_neighbors parameter ──


@pytest.mark.anyio
async def test_recall_accepts_expand_neighbors(repo: InMemoryRepository) -> None:
    """Mock recall accepts expand_neighbors without error."""
    await repo.store_episode(AGENT, "test content about cats")
    results = await repo.recall("cats", AGENT, limit=10, expand_neighbors=True)
    assert len(results) >= 1
    results_no_expand = await repo.recall("cats", AGENT, limit=10, expand_neighbors=False)
    assert len(results_no_expand) >= 1


# ── Cluster sort tests ──


def _make_episode_item(
    item_id: int,
    session_id: str | None = None,
    session_sequence: int | None = None,
    score: float = 1.0,
    graph_name: str = "ncx_test__personal",
    neighbor_of: int | None = None,
    created_at: datetime | None = None,
) -> RecallItem:
    return RecallItem(
        item_id=item_id,
        name=f"Episode #{item_id}",
        content=f"content {item_id}",
        item_type="Episode",
        score=score,
        source_kind="episode",
        graph_name=graph_name,
        session_id=session_id,
        session_sequence=session_sequence,
        neighbor_of=neighbor_of,
        created_at=created_at,
    )


def _make_node_item(item_id: int, score: float = 1.0) -> RecallItem:
    return RecallItem(
        item_id=item_id,
        name=f"Node #{item_id}",
        content=f"node content {item_id}",
        item_type="Entity",
        score=score,
        source_kind="node",
        graph_name="ncx_test__personal",
    )


def test_cluster_sort_chronological_order() -> None:
    """Episodes in the same session are reordered chronologically, even if scores differ."""
    now = datetime.now(UTC)
    items = [
        _make_episode_item(3, "sess-1", 3, score=0.9, created_at=now + timedelta(minutes=2)),
        _make_episode_item(2, "sess-1", 2, score=0.5, created_at=now + timedelta(minutes=1), neighbor_of=3),
        _make_episode_item(4, "sess-1", 4, score=0.5, created_at=now + timedelta(minutes=3), neighbor_of=3),
    ]
    sorted_items = _sort_session_clusters_chronologically(items)
    assert [i.item_id for i in sorted_items] == [2, 3, 4]


def test_cluster_sort_preserves_non_episode_order() -> None:
    """Nodes and episodes without sessions pass through in original order."""
    items = [
        _make_node_item(100, score=0.9),
        _make_episode_item(1, session_id=None, score=0.8),
        _make_node_item(200, score=0.7),
    ]
    sorted_items = _sort_session_clusters_chronologically(items)
    assert [i.item_id for i in sorted_items] == [100, 1, 200]


def test_cluster_sort_different_sessions_separate() -> None:
    """Episodes from different sessions form separate clusters."""
    now = datetime.now(UTC)
    items = [
        _make_episode_item(3, "sess-A", 2, score=0.9, created_at=now + timedelta(minutes=2)),
        _make_episode_item(1, "sess-A", 1, score=0.5, created_at=now, neighbor_of=3),
        _make_episode_item(10, "sess-B", 1, score=0.8, created_at=now),
        _make_episode_item(11, "sess-B", 2, score=0.4, created_at=now + timedelta(minutes=1), neighbor_of=10),
    ]
    sorted_items = _sort_session_clusters_chronologically(items)
    # sess-A cluster first (hit first in iteration), then sess-B
    assert [i.item_id for i in sorted_items] == [1, 3, 10, 11]


def test_cluster_sort_mixed_nodes_and_sessions() -> None:
    """Interleaved nodes and session episodes maintain correct grouping."""
    now = datetime.now(UTC)
    items = [
        _make_node_item(100, score=0.95),
        _make_episode_item(3, "sess-1", 3, score=0.9, created_at=now + timedelta(minutes=2)),
        _make_node_item(200, score=0.85),
        _make_episode_item(2, "sess-1", 2, score=0.5, created_at=now + timedelta(minutes=1), neighbor_of=3),
    ]
    sorted_items = _sort_session_clusters_chronologically(items)
    assert sorted_items[0].item_id == 100  # node stays first
    # session cluster: 2, 3
    assert sorted_items[1].item_id == 2
    assert sorted_items[2].item_id == 3
    assert sorted_items[3].item_id == 200  # node stays after cluster


def test_cluster_sort_fallback_to_created_at() -> None:
    """Episodes with None session_sequence sort by created_at."""
    now = datetime.now(UTC)
    items = [
        _make_episode_item(3, "sess-1", session_sequence=None, score=0.9, created_at=now + timedelta(minutes=2)),
        _make_episode_item(1, "sess-1", session_sequence=None, score=0.5, created_at=now, neighbor_of=3),
    ]
    sorted_items = _sort_session_clusters_chronologically(items)
    assert [i.item_id for i in sorted_items] == [1, 3]
