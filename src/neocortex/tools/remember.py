from fastmcp import Context
from loguru import logger

from neocortex.auth.dependencies import get_agent_id_from_context
from neocortex.schemas.memory import RememberResult


async def remember(
    text: str,
    context: str | None = None,
    target_graph: str | None = None,
    ctx: Context | None = None,
) -> RememberResult:
    """Store a memory. Describe what you want to remember in natural language.
    The system persists it as an episode and asynchronously extracts
    structured facts into the knowledge graph.

    Args:
        text: The content to remember, in natural language.
        context: Optional context about where/why this memory is being stored.
        target_graph: Optional shared graph to write to (requires write permission).
                      If omitted, stores to the agent's personal graph.
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for remember().")

    repo = ctx.lifespan_context["repo"]
    agent_id = get_agent_id_from_context(ctx)

    if target_graph is not None:
        router = ctx.lifespan_context["router"]
        await router.route_store_to(agent_id, target_graph)
        episode_id = await repo.store_episode_to(
            agent_id=agent_id, target_schema=target_graph, content=text, context=context
        )
    else:
        episode_id = await repo.store_episode(agent_id=agent_id, content=text, context=context)

    embeddings = ctx.lifespan_context.get("embeddings")
    if embeddings:
        vector = await embeddings.embed(text)
        if vector:
            await repo.update_episode_embedding(episode_id, vector, agent_id)

    # Enqueue extraction job if enabled
    extraction_job_id: int | None = None
    settings = ctx.lifespan_context["settings"]
    job_app = ctx.lifespan_context.get("job_app")
    if job_app and settings.extraction_enabled:
        extraction_job_id = await job_app.configure_task("extract_episode").defer_async(
            agent_id=agent_id, episode_ids=[episode_id], target_schema=target_graph
        )
        logger.bind(action_log=True).info(
            "extraction_enqueued",
            job_id=extraction_job_id,
            episode_id=episode_id,
            agent_id=agent_id,
            target_graph=target_graph,
        )

    return RememberResult(
        status="stored",
        episode_id=episode_id,
        message="Memory stored.",
        extraction_job_id=extraction_job_id,
    )
