import pytest


@pytest.mark.asyncio
async def test_create_and_get_node(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    node = await graph_service.create_node(
        type_id=concept.id, name="TestNode", content="Test content", source="test_data"
    )
    assert node.name == "TestNode"
    fetched = await graph_service.get_node(node.id)
    assert fetched is not None
    assert fetched.content == "Test content"


@pytest.mark.asyncio
async def test_create_node_with_embedding(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    emb = [0.1] * 768
    node = await graph_service.create_node(type_id=concept.id, name="EmbeddedNode", embedding=emb, source="test_data")
    assert node.id > 0


@pytest.mark.asyncio
async def test_create_and_traverse_edge(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    relates = await graph_service.get_edge_type_by_name("RELATES_TO")
    n1 = await graph_service.create_node(type_id=concept.id, name="Node_A", source="test_data")
    n2 = await graph_service.create_node(type_id=concept.id, name="Node_B", source="test_data")
    edge = await graph_service.create_edge(source_id=n1.id, target_id=n2.id, type_id=relates.id)
    assert edge.source_id == n1.id
    assert edge.target_id == n2.id

    outgoing = await graph_service.get_edges_from(n1.id)
    assert len(outgoing) == 1
    assert outgoing[0].target_id == n2.id

    incoming = await graph_service.get_edges_to(n2.id)
    assert len(incoming) == 1
    assert incoming[0].source_id == n1.id


@pytest.mark.asyncio
async def test_get_neighbors(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    relates = await graph_service.get_edge_type_by_name("RELATES_TO")
    center = await graph_service.create_node(type_id=concept.id, name="Center", source="test_data")
    leaf = await graph_service.create_node(type_id=concept.id, name="Leaf", source="test_data")
    await graph_service.create_edge(source_id=center.id, target_id=leaf.id, type_id=relates.id)

    neighbors = await graph_service.get_neighbors(center.id)
    assert len(neighbors) >= 1
    assert any(n["name"] == "Leaf" for n in neighbors)


@pytest.mark.asyncio
async def test_create_and_list_episodes(graph_service):
    ep = await graph_service.create_episode(agent_id="test_agent", content="Test episode content", source_type="test")
    assert ep.agent_id == "test_agent"
    episodes = await graph_service.list_episodes(agent_id="test_agent")
    assert len(episodes) >= 1
