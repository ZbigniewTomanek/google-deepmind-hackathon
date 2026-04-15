"""Tests for recall session output formatting and role-bias embedding (Stage 5, Plan 31).

Tests cover:
- _format_recall_context: session clustering, chronological sort, isolated episodes
- Role-bias embedding: "user:" prefix applied when query lacks role prefix
- RecallResult.formatted_context populated from tool execution
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.mcp_settings import MCPSettings
from neocortex.schemas.memory import RecallItem
from neocortex.tools.recall import _format_recall_context, recall

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 15, 12, 0, 0, tzinfo=UTC)
AGENT = "test-agent"


def _episode(
    item_id: int,
    content: str,
    score: float = 0.5,
    session_id: str | None = None,
    session_sequence: int | None = None,
    created_at: datetime | None = None,
    neighbor_of: int | None = None,
    graph_name: str | None = None,
) -> RecallItem:
    return RecallItem(
        item_id=item_id,
        name=f"Episode #{item_id}",
        content=content,
        item_type="Episode",
        score=score,
        source_kind="episode",
        session_id=session_id,
        session_sequence=session_sequence,
        created_at=created_at,
        neighbor_of=neighbor_of,
        graph_name=graph_name,
    )


def _node(item_id: int, name: str, score: float = 0.8) -> RecallItem:
    return RecallItem(
        item_id=item_id,
        name=name,
        content=f"Content of {name}",
        item_type="Concept",
        score=score,
        source_kind="node",
    )


def _make_mock_ctx(repo: InMemoryRepository, embeddings=None) -> AsyncMock:
    """Build a mock FastMCP context with the given repo and optional embedding service."""
    ctx = AsyncMock()
    ctx.lifespan_context = {
        "repo": repo,
        "settings": MCPSettings(auth_mode="none", mock_db=True),
        "embeddings": embeddings,
    }
    return ctx


# ---------------------------------------------------------------------------
# _format_recall_context tests
# ---------------------------------------------------------------------------


class TestFormatRecallContext:
    def test_no_episodes_returns_placeholder(self):
        """When results contain only nodes, return placeholder text."""
        result = _format_recall_context([_node(1, "Foo")])
        assert result == "(no episodes recalled)"

    def test_empty_results(self):
        result = _format_recall_context([])
        assert result == "(no episodes recalled)"

    def test_isolated_episode_renders_flat_json(self):
        """Episode without session_id renders as a standalone JSON object."""
        ep = _episode(10, "standalone memory", score=0.7, created_at=_NOW, graph_name="personal")
        result = _format_recall_context([ep])
        parsed = json.loads(result)

        assert parsed["id"] == 10
        assert parsed["content"] == "standalone memory"
        assert parsed["score"] == 0.7
        assert parsed["graph_name"] == "personal"
        assert parsed["created_at"] == _NOW.isoformat()
        # No session-related fields
        assert "session_id" not in parsed
        assert "episodes" not in parsed

    def test_session_cluster_groups_and_sorts_chronologically(self):
        """Episodes sharing a session_id are grouped; sorted by session_sequence."""
        ep1 = _episode(1, "first turn", session_id="s1", session_sequence=1, created_at=_NOW, score=0.6)
        ep3 = _episode(
            3, "third turn", session_id="s1", session_sequence=3, created_at=_NOW + timedelta(minutes=2), score=0.4
        )
        ep2 = _episode(
            2, "second turn", session_id="s1", session_sequence=2, created_at=_NOW + timedelta(minutes=1), score=0.9
        )

        # Pass in non-chronological order
        result = _format_recall_context([ep3, ep1, ep2])
        parsed = json.loads(result)

        assert parsed["session_id"] == "s1"
        episodes = parsed["episodes"]
        assert len(episodes) == 3
        assert [e["session_sequence"] for e in episodes] == [1, 2, 3]
        assert [e["id"] for e in episodes] == [1, 2, 3]

    def test_neighbor_episodes_flagged(self):
        """Context neighbors have is_context_neighbor=true and neighbor_of set."""
        ep1 = _episode(1, "direct hit", session_id="s1", session_sequence=1, created_at=_NOW, score=0.8)
        ep2 = _episode(
            2,
            "neighbor",
            session_id="s1",
            session_sequence=2,
            created_at=_NOW + timedelta(minutes=1),
            score=0.3,
            neighbor_of=1,
        )

        result = _format_recall_context([ep1, ep2])
        parsed = json.loads(result)
        episodes = parsed["episodes"]

        assert episodes[0]["is_context_neighbor"] is False
        assert episodes[0]["neighbor_of"] is None
        assert episodes[1]["is_context_neighbor"] is True
        assert episodes[1]["neighbor_of"] == 1

    def test_multiple_sessions_and_isolated_separated(self):
        """Multiple session clusters and isolated episodes are separated by ---."""
        ep_s1 = _episode(1, "session one", session_id="s1", session_sequence=1, created_at=_NOW, score=0.5)
        ep_s2 = _episode(2, "session two", session_id="s2", session_sequence=1, created_at=_NOW, score=0.5)
        ep_iso = _episode(3, "isolated", score=0.5, created_at=_NOW)

        result = _format_recall_context([ep_s1, ep_s2, ep_iso])
        parts = result.split("\n---\n")
        assert len(parts) == 3

        # First two are session clusters
        cluster1 = json.loads(parts[0])
        cluster2 = json.loads(parts[1])
        assert "session_id" in cluster1
        assert "session_id" in cluster2

        # Last is isolated
        isolated = json.loads(parts[2])
        assert "id" in isolated
        assert "session_id" not in isolated

    def test_nodes_are_excluded_from_formatted_context(self):
        """Node results are not included in the formatted episode context."""
        results = [
            _node(100, "SomeNode", score=0.9),
            _episode(1, "an episode", session_id="s1", session_sequence=1, created_at=_NOW, score=0.5),
        ]
        result = _format_recall_context(results)
        parsed = json.loads(result)
        # Should be the session cluster, not the node
        assert "session_id" in parsed
        assert parsed["episodes"][0]["content"] == "an episode"

    def test_fallback_sort_by_created_at_when_sequence_is_none(self):
        """When session_sequence is None, fall back to created_at ordering."""
        ep1 = _episode(1, "older", session_id="s1", session_sequence=None, created_at=_NOW, score=0.5)
        ep2 = _episode(
            2, "newer", session_id="s1", session_sequence=None, created_at=_NOW + timedelta(minutes=5), score=0.5
        )

        result = _format_recall_context([ep2, ep1])
        parsed = json.loads(result)
        assert [e["id"] for e in parsed["episodes"]] == [1, 2]

    def test_scores_rounded_to_four_decimals(self):
        ep = _episode(1, "test", score=0.123456789, session_id="s1", session_sequence=1, created_at=_NOW)
        result = _format_recall_context([ep])
        parsed = json.loads(result)
        assert parsed["episodes"][0]["score"] == 0.1235


# ---------------------------------------------------------------------------
# Role-bias embedding tests
# ---------------------------------------------------------------------------


class TestRoleBiasEmbedding:
    """Test that recall applies 'user:' prefix for episode vector search."""

    @pytest.mark.asyncio
    async def test_role_bias_applied_for_plain_query(self):
        """Plain query gets 'user:' prefix for episode embedding."""
        embedded_texts: list[str] = []

        class SpyEmbeddingService:
            async def embed(self, text: str) -> list[float]:
                embedded_texts.append(text)
                return [0.1] * 768

        repo = InMemoryRepository()
        await repo.store_episode(AGENT, "The user prefers dark mode")

        ctx = _make_mock_ctx(repo, embeddings=SpyEmbeddingService())
        with (
            patch("neocortex.tools.recall.get_agent_id_from_context", return_value=AGENT),
            patch("neocortex.tools.recall.ensure_provisioned", new_callable=AsyncMock),
        ):
            result = await recall("dark mode", ctx=ctx)

        # Should have embedded twice: original query + "user: " prefixed
        assert len(embedded_texts) == 2
        assert embedded_texts[0] == "dark mode"
        assert embedded_texts[1] == "user: dark mode"
        assert result.formatted_context is not None

    @pytest.mark.asyncio
    async def test_no_double_prefix_for_user_query(self):
        """Query already starting with 'user:' is not double-prefixed."""
        embedded_texts: list[str] = []

        class SpyEmbeddingService:
            async def embed(self, text: str) -> list[float]:
                embedded_texts.append(text)
                return [0.1] * 768

        repo = InMemoryRepository()
        await repo.store_episode(AGENT, "The user prefers dark mode")

        ctx = _make_mock_ctx(repo, embeddings=SpyEmbeddingService())
        with (
            patch("neocortex.tools.recall.get_agent_id_from_context", return_value=AGENT),
            patch("neocortex.tools.recall.ensure_provisioned", new_callable=AsyncMock),
        ):
            await recall("user: dark mode", ctx=ctx)

        # Should have embedded only once — no "user:" prefix added
        assert len(embedded_texts) == 1
        assert embedded_texts[0] == "user: dark mode"

    @pytest.mark.asyncio
    async def test_no_double_prefix_for_assistant_query(self):
        """Query starting with 'assistant:' is not double-prefixed."""
        embedded_texts: list[str] = []

        class SpyEmbeddingService:
            async def embed(self, text: str) -> list[float]:
                embedded_texts.append(text)
                return [0.1] * 768

        repo = InMemoryRepository()
        await repo.store_episode(AGENT, "The assistant helped with config")

        ctx = _make_mock_ctx(repo, embeddings=SpyEmbeddingService())
        with (
            patch("neocortex.tools.recall.get_agent_id_from_context", return_value=AGENT),
            patch("neocortex.tools.recall.ensure_provisioned", new_callable=AsyncMock),
        ):
            await recall("assistant: summarize the config", ctx=ctx)

        assert len(embedded_texts) == 1
        assert embedded_texts[0] == "assistant: summarize the config"


# ---------------------------------------------------------------------------
# Integration: formatted_context populated via direct recall call
# ---------------------------------------------------------------------------


class TestRecallResultFormattedContext:
    @pytest.mark.asyncio
    async def test_recall_populates_formatted_context(self):
        """Recall returns formatted_context field with episode data."""
        repo = InMemoryRepository()
        await repo.store_episode(AGENT, "Morning standup notes")

        ctx = _make_mock_ctx(repo)
        with (
            patch("neocortex.tools.recall.get_agent_id_from_context", return_value=AGENT),
            patch("neocortex.tools.recall.ensure_provisioned", new_callable=AsyncMock),
        ):
            result = await recall("standup", ctx=ctx)

        assert result.total == 1
        assert result.formatted_context is not None
        # Isolated episode (no session_id in basic mock store)
        parsed = json.loads(result.formatted_context)
        assert parsed["content"] == "Morning standup notes"

    @pytest.mark.asyncio
    async def test_empty_recall_has_placeholder_context(self):
        """Empty recall returns the placeholder string."""
        repo = InMemoryRepository()

        ctx = _make_mock_ctx(repo)
        with (
            patch("neocortex.tools.recall.get_agent_id_from_context", return_value=AGENT),
            patch("neocortex.tools.recall.ensure_provisioned", new_callable=AsyncMock),
        ):
            result = await recall("nonexistent", ctx=ctx)

        assert result.formatted_context == "(no episodes recalled)"
