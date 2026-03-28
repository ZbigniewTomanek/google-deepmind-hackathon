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


@pytest.mark.asyncio
async def test_get_type_detail_node(mock_repo) -> None:
    nt_person = await mock_repo.get_or_create_node_type("agent", "Person", "A person")
    nt_org = await mock_repo.get_or_create_node_type("agent", "Organization", "An org")
    et = await mock_repo.get_or_create_edge_type("agent", "WORKS_AT", "Employment relation")
    alice = await mock_repo.upsert_node("agent", "Alice", nt_person.id, content="Alice")
    await mock_repo.upsert_node("agent", "Bob", nt_person.id, content="Bob")
    acme = await mock_repo.upsert_node("agent", "Acme", nt_org.id, content="Acme Corp")
    await mock_repo.upsert_edge("agent", alice.id, acme.id, et.id)

    detail = await mock_repo.get_type_detail("agent", "Person", "any_graph", "node")
    assert detail is not None
    assert detail.name == "Person"
    assert detail.count == 2
    assert "WORKS_AT" in detail.connected_edge_types
    assert set(detail.sample_names) == {"Alice", "Bob"}


@pytest.mark.asyncio
async def test_get_type_detail_edge(mock_repo) -> None:
    nt = await mock_repo.get_or_create_node_type("agent", "Person", "A person")
    et = await mock_repo.get_or_create_edge_type("agent", "KNOWS", "Knows relation")
    alice = await mock_repo.upsert_node("agent", "Alice", nt.id)
    bob = await mock_repo.upsert_node("agent", "Bob", nt.id)
    await mock_repo.upsert_edge("agent", alice.id, bob.id, et.id)

    detail = await mock_repo.get_type_detail("agent", "KNOWS", "any_graph", "edge")
    assert detail is not None
    assert detail.name == "KNOWS"
    assert detail.count == 1
    assert "Person" in detail.connected_edge_types
    assert detail.sample_names == ["Alice→Bob"]


@pytest.mark.asyncio
async def test_get_type_detail_not_found(mock_repo) -> None:
    detail = await mock_repo.get_type_detail("agent", "NonExistent", "g", "node")
    assert detail is None


@pytest.mark.asyncio
async def test_get_stats_for_schema(mock_repo) -> None:
    await mock_repo.store_episode(agent_id="agent-a", content="test")
    stats = await mock_repo.get_stats_for_schema("agent-a", "any_schema")
    assert stats.total_episodes == 1
    assert stats.total_nodes == 0


# --- list_nodes_page tests ---


@pytest.mark.asyncio
async def test_list_nodes_page_returns_all_nodes(mock_repo) -> None:
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    await mock_repo.upsert_node("agent", "Alice", nt.id, content="Alice")
    await mock_repo.upsert_node("agent", "Bob", nt.id, content="Bob")

    nodes = await mock_repo.list_nodes_page("agent")
    assert len(nodes) == 2
    names = {n.name for n in nodes}
    assert names == {"Alice", "Bob"}


@pytest.mark.asyncio
async def test_list_nodes_page_filters_by_type(mock_repo) -> None:
    nt_person = await mock_repo.get_or_create_node_type("agent", "Person")
    nt_org = await mock_repo.get_or_create_node_type("agent", "Organization")
    await mock_repo.upsert_node("agent", "Alice", nt_person.id)
    await mock_repo.upsert_node("agent", "Acme", nt_org.id)

    nodes = await mock_repo.list_nodes_page("agent", type_id=nt_person.id)
    assert len(nodes) == 1
    assert nodes[0].name == "Alice"


@pytest.mark.asyncio
async def test_list_nodes_page_respects_limit(mock_repo) -> None:
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    for name in ["Alice", "Bob", "Charlie", "Diana", "Eve"]:
        await mock_repo.upsert_node("agent", name, nt.id)

    nodes = await mock_repo.list_nodes_page("agent", limit=3)
    assert len(nodes) == 3


@pytest.mark.asyncio
async def test_list_nodes_page_excludes_forgotten(mock_repo) -> None:
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    alice = await mock_repo.upsert_node("agent", "Alice", nt.id)
    await mock_repo.upsert_node("agent", "Bob", nt.id)
    await mock_repo.mark_forgotten("agent", [alice.id])

    nodes = await mock_repo.list_nodes_page("agent")
    assert len(nodes) == 1
    assert nodes[0].name == "Bob"


@pytest.mark.asyncio
async def test_list_nodes_page_sorts_by_importance(mock_repo) -> None:
    nt = await mock_repo.get_or_create_node_type("agent", "Person")
    await mock_repo.upsert_node("agent", "Alice", nt.id, importance=0.3)
    await mock_repo.upsert_node("agent", "Bob", nt.id, importance=0.9)
    await mock_repo.upsert_node("agent", "Charlie", nt.id, importance=0.6)

    nodes = await mock_repo.list_nodes_page("agent")
    assert nodes[0].name == "Bob"
    assert nodes[1].name == "Charlie"
    assert nodes[2].name == "Alice"
