from neocortex.schemas.memory import (
    DiscoverResult,
    GraphStats,
    RecallItem,
    RecallResult,
    RememberResult,
    TypeInfo,
)


def test_schema_models_can_be_instantiated() -> None:
    remember = RememberResult(status="stored", episode_id=1, message="Memory stored.")
    item = RecallItem(
        item_id=1,
        name="Episode #1",
        content="Alice likes tea",
        item_type="Episode",
        score=0.9,
        source="mcp",
        source_kind="episode",
        graph_name="ncx_alice__personal",
    )
    recall = RecallResult(results=[item], total=1, query="tea")
    node_type = TypeInfo(id=1, name="Episode", description="Stored memories", count=1)
    stats = GraphStats(total_nodes=1, total_edges=0, total_episodes=1)
    discover = DiscoverResult(node_types=[node_type], edge_types=[], stats=stats, graphs=["ncx_alice__personal"])

    assert remember.status == "stored"
    assert recall.total == 1
    assert discover.stats.total_episodes == 1
    assert discover.graphs == ["ncx_alice__personal"]


def test_schema_serialization_round_trip() -> None:
    original = DiscoverResult(
        node_types=[TypeInfo(id=1, name="Episode", description="Stored memories", count=2)],
        edge_types=[TypeInfo(id=2, name="RELATED_TO", description="Graph edge", count=1)],
        stats=GraphStats(total_nodes=2, total_edges=1, total_episodes=2),
        graphs=["ncx_alice__personal", "ncx_shared__knowledge"],
    )

    payload = original.model_dump()
    restored = DiscoverResult.model_validate(payload)

    assert restored == original
