from __future__ import annotations

import asyncpg

from neocortex.schema_manager import SchemaManager
from neocortex.schemas.graph import GraphInfo


class GraphRouter:
    """Routes memory operations to graph schemas using simple MVP heuristics."""

    def __init__(self, schema_mgr: SchemaManager, pool: asyncpg.Pool):
        self._schema_mgr = schema_mgr
        self._pool = pool

    async def route_store(self, agent_id: str) -> str:
        """Store new memories in the agent's personal graph, creating it if needed."""
        graph = await self._schema_mgr.get_graph(agent_id=agent_id, purpose="personal")
        if graph is not None:
            return graph.schema_name
        return await self._schema_mgr.create_graph(agent_id=agent_id, purpose="personal")

    async def route_recall(self, agent_id: str) -> list[str]:
        """Recall from all accessible graphs with personal graphs ranked ahead of shared ones."""
        agent_graphs = await self._schema_mgr.list_graphs(agent_id=agent_id)
        shared_graphs = await self._schema_mgr.list_graphs(agent_id="shared")
        ordered_agent_graphs = sorted(agent_graphs, key=_graph_priority)
        ordered_shared_graphs = sorted(shared_graphs, key=_graph_priority)
        return [graph.schema_name for graph in ordered_agent_graphs + ordered_shared_graphs]

    async def route_discover(self, agent_id: str) -> list[str]:
        """Use the same accessible graph set for ontology discovery as recall."""
        return await self.route_recall(agent_id)


def _graph_priority(graph: GraphInfo) -> tuple[int, str, str]:
    return (0 if graph.purpose == "personal" else 1, graph.purpose, graph.schema_name)
