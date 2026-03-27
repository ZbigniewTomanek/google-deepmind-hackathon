import pytest

from neocortex.schemas.memory import GraphStats


@pytest.mark.asyncio
async def test_store_episode_returns_incrementing_ids(mock_repo) -> None:
    first_id = await mock_repo.store_episode(agent_id="agent-a", content="First memory")
    second_id = await mock_repo.store_episode(agent_id="agent-a", content="Second memory")

    assert first_id == 1
    assert second_id == 2


@pytest.mark.asyncio
async def test_recall_filters_by_substring_and_agent_id(mock_repo) -> None:
    await mock_repo.store_episode(agent_id="agent-a", content="Alice likes tea")
    await mock_repo.store_episode(agent_id="agent-a", content="Alice likes coffee")
    await mock_repo.store_episode(agent_id="agent-b", content="Alice likes tea")

    results = await mock_repo.recall(query="tea", agent_id="agent-a")

    assert len(results) == 1
    assert results[0].content == "Alice likes tea"
    assert results[0].item_id == 1
    assert results[0].source_kind == "episode"


@pytest.mark.asyncio
async def test_get_stats_reflects_stored_episode_count(mock_repo) -> None:
    await mock_repo.store_episode(agent_id="agent-a", content="First memory")
    await mock_repo.store_episode(agent_id="agent-a", content="Second memory")

    stats = await mock_repo.get_stats()

    assert stats == GraphStats(total_nodes=0, total_edges=0, total_episodes=2)
