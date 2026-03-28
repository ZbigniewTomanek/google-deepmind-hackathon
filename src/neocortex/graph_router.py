from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg

from neocortex.schema_manager import SchemaManager
from neocortex.schemas.graph import GraphInfo

if TYPE_CHECKING:
    from neocortex.permissions.protocol import PermissionChecker


class GraphRouter:
    """Routes memory operations to graph schemas using simple MVP heuristics."""

    def __init__(
        self,
        schema_mgr: SchemaManager,
        pool: asyncpg.Pool,
        permissions: PermissionChecker,
    ):
        self._schema_mgr = schema_mgr
        self._pool = pool
        self._permissions = permissions

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

        # Filter shared graphs by read permission (single query, admins short-circuit)
        shared_names = [g.schema_name for g in shared_graphs]
        readable = await self._permissions.readable_schemas(agent_id, shared_names)
        accessible_shared = [g for g in shared_graphs if g.schema_name in readable]

        ordered_agent = sorted(agent_graphs, key=_graph_priority)
        ordered_shared = sorted(accessible_shared, key=_graph_priority)
        return [g.schema_name for g in ordered_agent + ordered_shared]

    async def route_discover(self, agent_id: str) -> list[str]:
        """Use the same accessible graph set for ontology discovery as recall."""
        return await self.route_recall(agent_id)

    async def route_store_to(self, agent_id: str, target_schema: str) -> str:
        """Validate write permission and return the target schema for a directed store."""
        graphs = await self._schema_mgr.list_graphs(agent_id="shared")
        schema_names = {g.schema_name for g in graphs}
        if target_schema not in schema_names:
            raise PermissionError(f"Schema '{target_schema}' is not a shared graph")

        if not await self._permissions.can_write_schema(agent_id, target_schema):
            raise PermissionError(f"Agent '{agent_id}' does not have write access to '{target_schema}'")
        return target_schema


def _graph_priority(graph: GraphInfo) -> tuple[int, str, str]:
    return (0 if graph.purpose == "personal" else 1, graph.purpose, graph.schema_name)
