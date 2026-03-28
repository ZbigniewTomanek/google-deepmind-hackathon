from __future__ import annotations

from uuid import uuid4

import pytest

from neocortex.db.adapter import GraphServiceAdapter
from neocortex.graph_router import GraphRouter
from neocortex.mcp_settings import MCPSettings
from neocortex.schema_manager import SchemaManager
from neocortex.server import create_server


@pytest.mark.asyncio
async def test_server_lifespan_provisions_shared_graph_and_agent_personal_graph(pg_service) -> None:
    suffix = uuid4().hex[:8]
    agent_id = f"server-stage-{suffix}"
    shared_schema = SchemaManager.make_schema_name("shared", "knowledge")
    personal_schema = SchemaManager.make_schema_name(agent_id, "personal")
    cleanup_manager = SchemaManager(pg_service)

    for schema_name in (personal_schema, shared_schema):
        await cleanup_manager.drop_graph(schema_name)

    settings = MCPSettings(auth_mode="none", mock_db=False, domain_routing_enabled=False)
    server = create_server(settings)

    try:
        async with server._lifespan_manager():
            context = server._lifespan_result
            assert context is not None

            repo = context["repo"]
            schema_mgr = context["schema_mgr"]
            router = context["router"]

            assert isinstance(repo, GraphServiceAdapter)
            assert isinstance(schema_mgr, SchemaManager)
            assert isinstance(router, GraphRouter)

            shared_graph = await schema_mgr.get_graph(agent_id="shared", purpose="knowledge")
            assert shared_graph is not None
            assert shared_graph.schema_name == shared_schema
            assert shared_graph.is_shared is True

            episode_id = await repo.store_episode(agent_id=agent_id, content="stage 7 auto-provision check")
            assert episode_id > 0

            personal_graph = await schema_mgr.get_graph(agent_id=agent_id, purpose="personal")
            assert personal_graph is not None
            assert personal_graph.schema_name == personal_schema
    finally:
        await cleanup_manager.drop_graph(personal_schema)
        await cleanup_manager.drop_graph(shared_schema)
