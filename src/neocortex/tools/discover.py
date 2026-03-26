async def discover(query: str | None = None) -> dict:
    """Discover what types of knowledge are stored. Returns the ontology —
    entity types, relationship types, and statistics. Optionally filtered.

    Args:
        query: Optional filter to narrow the ontology exploration.
    """
    return {
        "node_types": [],
        "edge_types": [],
        "stats": {"total_nodes": 0, "total_edges": 0, "total_episodes": 0},
        "message": "Empty knowledge graph (mock mode — no database connected).",
    }
