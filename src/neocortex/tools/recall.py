from fastmcp import Context

from neocortex.auth.dependencies import get_agent_id_from_context
from neocortex.schemas.memory import RecallResult


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
    agent_id = get_agent_id_from_context(ctx)

    embeddings = ctx.lifespan_context.get("embeddings")
    query_embedding = None
    if embeddings:
        query_embedding = await embeddings.embed(query)

    results = await repo.recall(query=query, agent_id=agent_id, limit=limit, query_embedding=query_embedding)
    return RecallResult(
        results=results,
        total=len(results),
        query=query,
    )
