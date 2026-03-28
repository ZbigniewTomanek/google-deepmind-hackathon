import random

from fastmcp import Context
from loguru import logger

from neocortex.auth.dependencies import get_agent_id_from_context
from neocortex.schemas.memory import GraphContext, RecallItem, RecallResult
from neocortex.scoring import compute_spreading_activation, neighborhood_to_adjacency


async def _maybe_forget_sweep(repo, agent_id: str, settings, *, force: bool = False) -> None:
    """Probabilistically identify and soft-forget low-activation, low-importance nodes."""
    if not force and random.random() >= 0.05:
        return
    forgettable = await repo.identify_forgettable_nodes(
        agent_id, settings.forget_activation_threshold, settings.forget_importance_floor
    )
    if forgettable:
        count = await repo.mark_forgotten(agent_id, forgettable)
        if count:
            logger.bind(action_log=True).info("forget_sweep", agent_id=agent_id, forgotten_count=count)


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
    matched_node_tuples = await repo.search_nodes(
        agent_id=agent_id, query=query, limit=5, query_embedding=query_embedding
    )

    traversal_depth = settings.recall_traversal_depth

    # Resolve type names (once, outside the loop)
    node_types = await repo.get_node_types(agent_id)
    edge_types = await repo.get_edge_types(agent_id)
    type_name_map = {t.id: t.name for t in node_types}
    edge_type_name_map = {t.id: t.name for t in edge_types}

    # Build node results with graph context + collect adjacency for spreading activation
    existing_node_ids = {r.item_id for r in results if r.source_kind == "node"}
    node_results: list[RecallItem] = []
    merged_adjacency: dict[int, list[tuple[int, float]]] = {}
    traversed_edge_ids: set[int] = set()

    # Collect all seeds: Phase 1 node results + Phase 2 search results
    seed_nodes: list[tuple[int, float]] = []
    for r in results:
        if r.source_kind == "node":
            seed_nodes.append((r.item_id, r.score))

    for node, relevance_score in matched_node_tuples:
        neighborhood = await repo.get_node_neighborhood(agent_id=agent_id, node_id=node.id, depth=traversal_depth)

        # Collect edge IDs for reinforcement
        for entry in neighborhood:
            for edge in entry["edges"]:
                traversed_edge_ids.add(edge.id)

        # Build adjacency map for spreading activation
        adjacency = neighborhood_to_adjacency(neighborhood, node.id)
        for nid, neighbors in adjacency.items():
            if nid not in merged_adjacency:
                merged_adjacency[nid] = []
            merged_adjacency[nid].extend(neighbors)

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
            # Add Phase 2 seed with relevance score
            seed_nodes.append((node.id, relevance_score))
            node_results.append(
                RecallItem(
                    item_id=node.id,
                    name=node.name,
                    content=node.content or "",
                    item_type=node_type_name,
                    score=relevance_score,
                    source=node.source,
                    source_kind="node",
                    graph_name=None,
                    graph_context=graph_context,
                )
            )

    # Merge and apply spreading activation
    all_results = results + node_results

    if seed_nodes and merged_adjacency:
        bonus_map = compute_spreading_activation(
            seed_nodes=seed_nodes,
            neighborhood=merged_adjacency,
            decay=settings.spreading_activation_decay,
            max_depth=settings.spreading_activation_max_depth,
        )

        # Apply bonus to node results
        for r in all_results:
            if r.source_kind == "node" and r.item_id in bonus_map:
                bonus = bonus_map[r.item_id]
                r.spreading_bonus = bonus
                r.score += bonus * 0.1  # Moderate contribution to avoid dominating

    # Re-sort by updated score
    all_results.sort(key=lambda item: item.score, reverse=True)

    # Record access for returned results (ACT-R activation tracking)
    final_results = all_results[:limit]
    recalled_node_ids = [r.item_id for r in final_results if r.source_kind == "node"]
    recalled_episode_ids = [r.item_id for r in final_results if r.source_kind == "episode"]
    if recalled_node_ids:
        await repo.record_node_access(agent_id, recalled_node_ids)
    if recalled_episode_ids:
        await repo.record_episode_access(agent_id, recalled_episode_ids)

    # Edge reinforcement — strengthen traversed edges (Hebbian learning)
    if traversed_edge_ids:
        await repo.reinforce_edges(
            agent_id,
            list(traversed_edge_ids),
            delta=settings.edge_reinforcement_delta,
            ceiling=settings.edge_weight_ceiling,
        )

    # Lazy edge decay — 1 in 10 recall calls
    if random.random() < 0.1:
        await repo.decay_stale_edges(
            agent_id,
            older_than_hours=168.0,
            decay_factor=0.95,
            floor=settings.edge_weight_floor,
        )

    # Lazy forget sweep — 1 in 20 recall calls
    await _maybe_forget_sweep(repo, agent_id, settings)

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
