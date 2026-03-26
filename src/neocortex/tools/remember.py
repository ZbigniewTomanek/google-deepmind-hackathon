async def remember(text: str, context: str | None = None) -> dict:
    """Store a memory. Describe what you want to remember in natural language.
    The system persists it as an episode and asynchronously extracts
    structured facts into the knowledge graph.

    Args:
        text: The content to remember, in natural language.
        context: Optional context about where/why this memory is being stored.
    """
    return {
        "status": "stored",
        "episode_id": -1,
        "message": "Memory stored (mock mode — no database connected).",
    }
