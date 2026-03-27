from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import uuid4

import pytest
from fastmcp import Context

from neocortex.db.adapter import GraphServiceAdapter
from neocortex.db.scoped import graph_scoped_connection, schema_scoped_connection
from neocortex.graph_router import GraphRouter
from neocortex.graph_service import GraphService
from neocortex.mcp_settings import MCPSettings
from neocortex.schema_manager import SchemaManager
from neocortex.tools.discover import discover


@dataclass
class _FakeContext:
    lifespan_context: dict[str, object]


async def _insert_concept_node(
    pg_service,
    schema_name: str,
    name: str,
    content: str,
    source: str,
    *,
    agent_id: str | None = None,
    shared: bool = False,
) -> None:
    context_manager = (
        graph_scoped_connection(pg_service.pool, schema_name, agent_id=agent_id)
        if agent_id is not None
        else schema_scoped_connection(pg_service.pool, schema_name)
    )
    async with context_manager as conn:
        type_id = await conn.fetchval("SELECT id FROM node_type WHERE name = 'Concept'")
        assert type_id is not None
        if shared:
            await conn.execute(
                """
                INSERT INTO node (type_id, name, content, source, owner_role)
                VALUES ($1, $2, $3, $4, NULL)
                """,
                int(type_id),
                name,
                content,
                source,
            )
            return

        await conn.execute(
            """
            INSERT INTO node (type_id, name, content, source)
            VALUES ($1, $2, $3, $4)
            """,
            int(type_id),
            name,
            content,
            source,
        )


@pytest.mark.asyncio
async def test_recall_merges_results_across_agent_and_shared_graphs(pg_service) -> None:
    manager = SchemaManager(pg_service)
    router = GraphRouter(manager, pg_service.pool)
    adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"adapter-{suffix}"

    shared_schema = await manager.create_graph(agent_id="shared", purpose=f"knowledge_{suffix}", is_shared=True)
    personal_schema = await manager.ensure_default_graphs(agent_id)

    try:
        await adapter.store_episode(agent_id=agent_id, content=f"Alice likes pizza {suffix}", source_type="mcp")
        await _insert_concept_node(
            pg_service,
            shared_schema,
            name=f"Pizza Fact {suffix}",
            content=f"Pizza research note {suffix}",
            source=f"test_multi_graph_{suffix}",
            agent_id=agent_id,
            shared=True,
        )

        results = await adapter.recall(query="pizza", agent_id=agent_id, limit=10)

        assert len(results) >= 2
        assert {item.graph_name for item in results} >= {personal_schema, shared_schema}
        assert {item.source_kind for item in results} >= {"episode", "node"}
        assert any(item.content == f"Alice likes pizza {suffix}" for item in results)
        assert any(item.content == f"Pizza research note {suffix}" for item in results)
    finally:
        await manager.drop_graph(personal_schema)
        await manager.drop_graph(shared_schema)


@pytest.mark.asyncio
async def test_recall_results_include_graph_name_and_source_kind(pg_service) -> None:
    manager = SchemaManager(pg_service)
    router = GraphRouter(manager, pg_service.pool)
    adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"provenance-{suffix}"

    personal_schema = await manager.ensure_default_graphs(agent_id)
    try:
        await adapter.store_episode(agent_id=agent_id, content=f"Episode provenance {suffix}", source_type="mcp")
        await _insert_concept_node(
            pg_service,
            personal_schema,
            name=f"Node Provenance {suffix}",
            content=f"Node provenance {suffix}",
            source=f"test_multi_graph_{suffix}",
        )

        results = await adapter.recall(query="provenance", agent_id=agent_id, limit=10)

        assert {item.source_kind for item in results} == {"episode", "node"}
        assert all(item.graph_name == personal_schema for item in results)
        assert {item.item_type for item in results} >= {"Episode", "Concept"}
    finally:
        await manager.drop_graph(personal_schema)


@pytest.mark.asyncio
async def test_discover_aggregates_stats_and_lists_accessible_graphs(pg_service) -> None:
    manager = SchemaManager(pg_service)
    router = GraphRouter(manager, pg_service.pool)
    adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"discover-{suffix}"
    settings = MCPSettings(auth_mode="dev_token", dev_user_id=agent_id, mock_db=False)

    shared_schema = await manager.create_graph(agent_id="shared", purpose=f"discover_{suffix}", is_shared=True)
    personal_schema = await manager.ensure_default_graphs(agent_id)

    try:
        await adapter.store_episode(agent_id=agent_id, content=f"Discover episode {suffix}", source_type="mcp")
        await _insert_concept_node(
            pg_service,
            personal_schema,
            name=f"Personal concept {suffix}",
            content=f"Personal note {suffix}",
            source=f"test_multi_graph_{suffix}",
        )
        await _insert_concept_node(
            pg_service,
            shared_schema,
            name=f"Shared concept {suffix}",
            content=f"Shared note {suffix}",
            source=f"test_multi_graph_{suffix}",
            agent_id=agent_id,
            shared=True,
        )

        result = await discover(
            cast(
                Context,
                _FakeContext(
                    lifespan_context={
                        "repo": adapter,
                        "settings": settings,
                    }
                ),
            )
        )

        assert result.stats.total_nodes == 2
        assert result.stats.total_edges == 0
        assert result.stats.total_episodes == 1
        assert result.graphs == [personal_schema, shared_schema]
        concept = next(item for item in result.node_types if item.name == "Concept")
        assert concept.count == 2
    finally:
        await manager.drop_graph(personal_schema)
        await manager.drop_graph(shared_schema)
