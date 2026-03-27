from fastmcp import Context

from neocortex.auth.dependencies import get_agent_id_from_context
from neocortex.schemas.memory import DiscoverResult, GraphStats


async def discover(ctx: Context | None = None) -> DiscoverResult:
    """Discover what types of knowledge are stored. Returns the ontology —
    entity types, relationship types, and statistics.
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for discover().")

    repo = ctx.lifespan_context["repo"]
    agent_id = get_agent_id_from_context(ctx)
    node_types = await repo.get_node_types(agent_id=agent_id)
    edge_types = await repo.get_edge_types(agent_id=agent_id)
    stats = await repo.get_stats(agent_id=agent_id)
    graphs = await repo.list_graphs(agent_id=agent_id)
    return DiscoverResult(
        node_types=node_types,
        edge_types=edge_types,
        stats=stats if isinstance(stats, GraphStats) else GraphStats.model_validate(stats),
        graphs=graphs,
    )
