from fastmcp import Context

from neocortex.auth.dependencies import get_agent_id_from_context
from neocortex.schemas.memory import RememberResult


async def remember(text: str, context: str | None = None, ctx: Context | None = None) -> RememberResult:
    """Store a memory. Describe what you want to remember in natural language.
    The system persists it as an episode and asynchronously extracts
    structured facts into the knowledge graph.

    Args:
        text: The content to remember, in natural language.
        context: Optional context about where/why this memory is being stored.
    """
    if ctx is None:
        raise RuntimeError("FastMCP context is required for remember().")

    repo = ctx.lifespan_context["repo"]
    agent_id = get_agent_id_from_context(ctx)
    episode_id = await repo.store_episode(agent_id=agent_id, content=text, context=context)
    return RememberResult(
        status="stored",
        episode_id=episode_id,
        message="Memory stored.",
    )
