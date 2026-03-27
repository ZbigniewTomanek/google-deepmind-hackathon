from fastmcp import Context

from neocortex.schemas.memory import DiscoverResult, GraphStats


async def discover(query: str | None = None, ctx: Context | None = None) -> DiscoverResult:
    """Discover what types of knowledge are stored. Returns the ontology —
    entity types, relationship types, and statistics. Optionally filtered.

    Args:
        query: Optional filter to narrow the ontology exploration.
    """
    del query
    if ctx is None:
        raise RuntimeError("FastMCP context is required for discover().")

    repo = ctx.lifespan_context["repo"]
    node_types = await repo.get_node_types()
    edge_types = await repo.get_edge_types()
    stats = await repo.get_stats()
    return DiscoverResult(
        node_types=node_types,
        edge_types=edge_types,
        stats=stats if isinstance(stats, GraphStats) else GraphStats.model_validate(stats),
    )
