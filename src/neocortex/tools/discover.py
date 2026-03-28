from fastmcp import Context
from loguru import logger

from neocortex.auth.dependencies import ensure_provisioned, get_agent_id_from_context
from neocortex.schemas.memory import (
    DiscoverDetailsResult,
    DiscoverDomainsResult,
    DiscoverGraphsResult,
    DiscoverOntologyResult,
    DomainInfo,
    GraphSummary,
)


async def discover_domains(ctx: Context | None = None) -> DiscoverDomainsResult:
    """List semantic knowledge domains (upper ontology).
    Shows what broad categories of knowledge exist and which graphs store them.
    Call this first to understand the knowledge landscape.
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for discover_domains().")

    agent_id = get_agent_id_from_context(ctx)
    domain_router = ctx.lifespan_context.get("domain_router")

    if domain_router is None:
        logger.bind(action_log=True).info("tool_call", tool="discover_domains", agent_id=agent_id, domains=0)
        return DiscoverDomainsResult(domains=[], message="Domain routing is not enabled")

    domains = await domain_router.list_domains()
    domain_infos = [
        DomainInfo(
            slug=d.slug,
            name=d.name,
            description=d.description,
            schema_name=d.schema_name,
        )
        for d in domains
    ]

    logger.bind(action_log=True).info(
        "tool_call",
        tool="discover_domains",
        agent_id=agent_id,
        domains=len(domain_infos),
    )
    return DiscoverDomainsResult(domains=domain_infos)


async def discover_graphs(ctx: Context | None = None) -> DiscoverGraphsResult:
    """List all knowledge graphs accessible to you, with per-graph statistics.
    Each graph has node/edge/episode counts.
    Use graph names with discover_ontology to drill into a specific graph.
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for discover_graphs().")

    repo = ctx.lifespan_context["repo"]
    agent_id = get_agent_id_from_context(ctx)
    await ensure_provisioned(ctx, agent_id)

    schema_names = await repo.list_graphs(agent_id=agent_id)

    # Build a lookup of schema_name -> (purpose, is_shared) from schema_mgr if available
    schema_info: dict[str, tuple[str, bool]] = {}
    schema_mgr = ctx.lifespan_context.get("schema_mgr")
    if schema_mgr is not None:
        all_graphs = await schema_mgr.list_graphs()
        for g in all_graphs:
            schema_info[g.schema_name] = (g.purpose, g.is_shared)

    graphs: list[GraphSummary] = []
    for name in schema_names:
        stats = await repo.get_stats_for_schema(agent_id=agent_id, schema_name=name)
        if name in schema_info:
            purpose, is_shared = schema_info[name]
        else:
            # Parse purpose from schema name: strip ncx_{agent}__ prefix
            parts = name.split("__", 1)
            purpose = parts[1] if len(parts) > 1 else name
            is_shared = False
        graphs.append(
            GraphSummary(
                schema_name=name,
                is_shared=is_shared,
                purpose=purpose,
                stats=stats,
            )
        )

    logger.bind(action_log=True).info(
        "tool_call",
        tool="discover_graphs",
        agent_id=agent_id,
        graph_count=len(graphs),
    )
    return DiscoverGraphsResult(graphs=graphs)


async def discover_ontology(graph_name: str, ctx: Context | None = None) -> DiscoverOntologyResult:
    """Show the entity types and relationship types in a specific graph.
    Returns node types and edge types with counts. Use discover_details
    to drill into a specific type.
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for discover_ontology().")

    repo = ctx.lifespan_context["repo"]
    agent_id = get_agent_id_from_context(ctx)

    node_types = await repo.get_node_types(agent_id=agent_id, target_schema=graph_name)
    edge_types = await repo.get_edge_types(agent_id=agent_id, target_schema=graph_name)
    stats = await repo.get_stats_for_schema(agent_id=agent_id, schema_name=graph_name)

    logger.bind(action_log=True).info(
        "tool_call",
        tool="discover_ontology",
        agent_id=agent_id,
        graph_name=graph_name,
        node_types=len(node_types),
        edge_types=len(edge_types),
    )
    return DiscoverOntologyResult(
        graph_name=graph_name,
        node_types=node_types,
        edge_types=edge_types,
        stats=stats,
    )


async def discover_details(
    type_name: str,
    graph_name: str,
    kind: str = "node",
    ctx: Context | None = None,
) -> DiscoverDetailsResult:
    """Get detailed information about a specific type in a graph.
    Returns the type's description, connected types, and sample entity names.

    Args:
        type_name: The name of the type to inspect.
        graph_name: The schema name of the graph containing the type.
        kind: 'node' for entity types, 'edge' for relationship types.
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for discover_details().")

    repo = ctx.lifespan_context["repo"]
    agent_id = get_agent_id_from_context(ctx)

    detail = await repo.get_type_detail(agent_id=agent_id, type_name=type_name, graph_name=graph_name, kind=kind)

    if detail is None:
        from neocortex.schemas.memory import TypeDetail

        detail = TypeDetail(id=0, name=type_name, description=f"Type '{type_name}' not found in {graph_name}")

    logger.bind(action_log=True).info(
        "tool_call",
        tool="discover_details",
        agent_id=agent_id,
        graph_name=graph_name,
        type_name=type_name,
        kind=kind,
    )
    return DiscoverDetailsResult(graph_name=graph_name, type_detail=detail)
