from neocortex.schemas.memory import DiscoverResult, GraphStats


async def discover(query: str | None = None) -> DiscoverResult:
    """Discover what types of knowledge are stored. Returns the ontology —
    entity types, relationship types, and statistics. Optionally filtered.

    Args:
        query: Optional filter to narrow the ontology exploration.
    """
    return DiscoverResult(
        node_types=[],
        edge_types=[],
        stats=GraphStats(total_nodes=0, total_edges=0, total_episodes=0),
    )
