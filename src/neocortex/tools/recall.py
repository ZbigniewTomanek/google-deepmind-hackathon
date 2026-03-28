from fastmcp import Context
from loguru import logger

from neocortex.auth.dependencies import get_agent_id_from_context
from neocortex.schemas.memory import GraphContext, RecallItem, RecallResult


async def recall(query: str, limit: int = 10, ctx: Context | None = None) -> RecallResult:
    """Recall memories related to a query. Uses hybrid search combining
    semantic similarity, full-text search, and graph traversal.

    Args:
        query: What you want to know, in natural language.
        limit: Maximum number of results to return (1-100).
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for recall().")

    limit = max(1, min(limit, 100))
    repo = ctx.lifespan_context["repo"]
    settings = ctx.lifespan_context["settings"]
    agent_id = get_agent_id_from_context(ctx)

    embeddings = ctx.lifespan_context.get("embeddings")
    query_embedding = None
    if embeddings:
        query_embedding = await embeddings.embed(query)

    # Episode + existing node recall
    results = await repo.recall(query=query, agent_id=agent_id, limit=limit, query_embedding=query_embedding)

    # Node search with graph traversal
    matched_nodes = await repo.search_nodes(agent_id=agent_id, query=query, limit=5, query_embedding=query_embedding)

    traversal_depth = settings.recall_traversal_depth

    # Resolve type names (once, outside the loop)
    node_types = await repo.get_node_types(agent_id)
    edge_types = await repo.get_edge_types(agent_id)
    type_name_map = {t.id: t.name for t in node_types}
    edge_type_name_map = {t.id: t.name for t in edge_types}

    # Build node results with graph context
    existing_node_ids = {r.item_id for r in results if r.source_kind == "node"}
    node_results: list[RecallItem] = []

    for node in matched_nodes:
        neighborhood = await repo.get_node_neighborhood(agent_id=agent_id, node_id=node.id, depth=traversal_depth)

        node_type_name = type_name_map.get(node.type_id, "Unknown")

        graph_context = GraphContext(
            center_node={
                "id": node.id,
                "name": node.name,
                "type": node_type_name,
                "properties": node.properties,
            },
            edges=[
                {
                    "source": entry["edges"][0].source_id if entry["edges"] else None,
                    "target": entry["edges"][0].target_id if entry["edges"] else None,
                    "type": edge_type_name_map.get(entry["edges"][0].type_id, "Unknown") if entry["edges"] else None,
                    "weight": entry["edges"][0].weight if entry["edges"] else None,
                    "properties": entry["edges"][0].properties if entry["edges"] else {},
                }
                for entry in neighborhood
                if entry["edges"]
            ],
            neighbor_nodes=[
                {
                    "id": entry["node"].id,
                    "name": entry["node"].name,
                    "type": type_name_map.get(entry["node"].type_id, "Unknown"),
                }
                for entry in neighborhood
            ],
            depth=traversal_depth,
        )

        # If this node was already in recall results, enrich it with graph_context
        if node.id in existing_node_ids:
            for r in results:
                if r.source_kind == "node" and r.item_id == node.id:
                    r.graph_context = graph_context
                    break
        else:
            node_results.append(
                RecallItem(
                    item_id=node.id,
                    name=node.name,
                    content=node.content or "",
                    item_type=node_type_name,
                    score=0.5,  # default score for search_nodes matches
                    source=node.source,
                    source_kind="node",
                    graph_name=None,
                    graph_context=graph_context,
                )
            )

    # Merge and re-sort
    all_results = results + node_results
    all_results.sort(key=lambda item: item.score, reverse=True)

    # Record access for returned results (ACT-R activation tracking)
    final_results = all_results[:limit]
    recalled_node_ids = [r.item_id for r in final_results if r.source_kind == "node"]
    recalled_episode_ids = [r.item_id for r in final_results if r.source_kind == "episode"]
    if recalled_node_ids:
        await repo.record_node_access(agent_id, recalled_node_ids)
    if recalled_episode_ids:
        await repo.record_episode_access(agent_id, recalled_episode_ids)

    logger.bind(action_log=True).info(
        "recall_with_graph_traversal",
        agent_id=agent_id,
        query=query,
        total_results=len(all_results),
        node_results_with_context=sum(1 for r in all_results if r.graph_context is not None),
    )

    return RecallResult(
        results=final_results,
        total=len(final_results),
        query=query,
    )
