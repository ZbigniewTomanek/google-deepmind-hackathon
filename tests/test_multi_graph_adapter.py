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
from neocortex.permissions.memory_service import InMemoryPermissionService
from neocortex.schema_manager import SchemaManager
from neocortex.tools.discover import discover_graphs, discover_ontology


async def _make_admin_permissions() -> InMemoryPermissionService:
    svc = InMemoryPermissionService(bootstrap_admin_id="admin")
    await svc.ensure_admin("admin")
    return svc


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
async def test_store_episode_writes_to_agent_personal_schema(pg_service) -> None:
    manager = SchemaManager(pg_service)
    router = GraphRouter(manager, pg_service.pool, permissions=await _make_admin_permissions())
    adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"store-{suffix}"

    personal_schema = await manager.ensure_default_graphs(agent_id)
    try:
        episode_id = await adapter.store_episode(
            agent_id=agent_id,
            content=f"Stored in personal graph {suffix}",
            source_type="mcp",
        )

        async with schema_scoped_connection(pg_service.pool, personal_schema) as conn:
            row = await conn.fetchrow(
                "SELECT id, agent_id, content FROM episode WHERE id = $1",
                episode_id,
            )

        assert row is not None
        assert int(row["id"]) == episode_id
        assert str(row["agent_id"]) == agent_id
        assert str(row["content"]) == f"Stored in personal graph {suffix}"
    finally:
        await manager.drop_graph(personal_schema)


@pytest.mark.asyncio
async def test_recall_merges_results_across_agent_and_shared_graphs(pg_service) -> None:
    manager = SchemaManager(pg_service)
    router = GraphRouter(manager, pg_service.pool, permissions=await _make_admin_permissions())
    adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"adapter-{suffix}"

    shared_schema = await manager.create_graph(agent_id="shared", purpose=f"knowledge_{suffix}", is_shared=True)
    personal_schema = await manager.ensure_default_graphs(agent_id)

    try:
        permissions = await _make_admin_permissions()
        await permissions.grant(agent_id, shared_schema, can_read=True, can_write=False, granted_by="admin")
        router = GraphRouter(manager, pg_service.pool, permissions=permissions)
        adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)

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
    router = GraphRouter(manager, pg_service.pool, permissions=await _make_admin_permissions())
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
async def test_discover_graphs_lists_accessible_graphs(pg_service) -> None:
    manager = SchemaManager(pg_service)
    router = GraphRouter(manager, pg_service.pool, permissions=await _make_admin_permissions())
    adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"discover-{suffix}"
    settings = MCPSettings(auth_mode="dev_token", dev_user_id=agent_id, mock_db=False)

    shared_schema = await manager.create_graph(agent_id="shared", purpose=f"discover_{suffix}", is_shared=True)
    personal_schema = await manager.ensure_default_graphs(agent_id)

    try:
        permissions = await _make_admin_permissions()
        await permissions.grant(agent_id, shared_schema, can_read=True, can_write=False, granted_by="admin")
        router = GraphRouter(manager, pg_service.pool, permissions=permissions)
        adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)

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

        graphs_result = await discover_graphs(
            cast(
                Context,
                _FakeContext(
                    lifespan_context={
                        "repo": adapter,
                        "settings": settings,
                        "schema_mgr": manager,
                    }
                ),
            )
        )

        graph_names = [g.schema_name for g in graphs_result.graphs]
        assert personal_schema in graph_names
        assert shared_schema in graph_names

        # Test discover_ontology for the personal graph
        ontology_result = await discover_ontology(
            graph_name=personal_schema,
            ctx=cast(
                Context,
                _FakeContext(
                    lifespan_context={
                        "repo": adapter,
                        "settings": settings,
                    }
                ),
            ),
        )

        assert ontology_result.graph_name == personal_schema
        assert ontology_result.stats.total_nodes >= 1
        concept = next(item for item in ontology_result.node_types if item.name == "Concept")
        assert concept.count >= 1
    finally:
        await manager.drop_graph(personal_schema)
        await manager.drop_graph(shared_schema)


@pytest.mark.asyncio
async def test_schema_isolation_keeps_agent_data_separate(pg_service) -> None:
    manager = SchemaManager(pg_service)
    router = GraphRouter(manager, pg_service.pool, permissions=await _make_admin_permissions())
    adapter = GraphServiceAdapter(GraphService(pg_service), router=router, pool=pg_service.pool, pg=pg_service)
    suffix = uuid4().hex[:8]
    agent_a = f"isolation-a-{suffix}"
    agent_b = f"isolation-b-{suffix}"

    schema_a = await manager.ensure_default_graphs(agent_a)
    schema_b = await manager.ensure_default_graphs(agent_b)
    try:
        await adapter.store_episode(agent_id=agent_a, content=f"Alpha memory {suffix}", source_type="mcp")
        await adapter.store_episode(agent_id=agent_b, content=f"Beta memory {suffix}", source_type="mcp")

        results_a = await adapter.recall(query="Alpha", agent_id=agent_a, limit=10)
        results_b = await adapter.recall(query="Beta", agent_id=agent_b, limit=10)

        assert any(item.content == f"Alpha memory {suffix}" and item.graph_name == schema_a for item in results_a)
        assert all(item.content != f"Beta memory {suffix}" for item in results_a)
        assert any(item.content == f"Beta memory {suffix}" and item.graph_name == schema_b for item in results_b)
        assert all(item.content != f"Alpha memory {suffix}" for item in results_b)
    finally:
        await manager.drop_graph(schema_a)
        await manager.drop_graph(schema_b)
