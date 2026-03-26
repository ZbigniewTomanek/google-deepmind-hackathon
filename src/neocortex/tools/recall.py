async def recall(query: str, limit: int = 10) -> dict:
    """Recall memories related to a query. Uses hybrid search combining
    semantic similarity, full-text search, and graph traversal.

    Args:
        query: What you want to know, in natural language.
        limit: Maximum number of results to return (1-100).
    """
    return {
        "results": [],
        "total": 0,
        "query": query,
        "message": "No memories found (mock mode — no database connected).",
    }
