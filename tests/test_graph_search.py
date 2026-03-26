import pytest


@pytest.mark.asyncio
async def test_vector_search(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    emb_a = [1.0] + [0.0] * 767  # Unit vector in first dimension
    emb_b = [0.0, 1.0] + [0.0] * 766  # Unit vector in second dimension
    await graph_service.create_node(type_id=concept.id, name="VecA", embedding=emb_a, source="test_search")
    await graph_service.create_node(type_id=concept.id, name="VecB", embedding=emb_b, source="test_search")

    # Search near emb_a — should find VecA first
    results = await graph_service.search_by_vector([0.9, 0.1] + [0.0] * 766, limit=2)
    assert len(results) >= 1
    assert results[0]["name"] == "VecA"


@pytest.mark.asyncio
async def test_text_search(graph_service):
    concept = await graph_service.get_node_type_by_name("Concept")
    await graph_service.create_node(
        type_id=concept.id,
        name="PostgreSQL",
        content="Open source relational database management system",
        source="test_search",
    )
    await graph_service.create_node(
        type_id=concept.id,
        name="Redis",
        content="In-memory key-value data store",
        source="test_search",
    )

    results = await graph_service.search_by_text("relational database", limit=5)
    assert len(results) >= 1
    assert results[0]["name"] == "PostgreSQL"


@pytest.mark.asyncio
async def test_ontology_stats(graph_service):
    stats = await graph_service.get_ontology_stats()
    assert "total_nodes" in stats
    assert "total_edges" in stats
    assert "total_episodes" in stats
    assert "node_types" in stats
    assert "edge_types" in stats
    assert len(stats["node_types"]) >= 6  # seed types
