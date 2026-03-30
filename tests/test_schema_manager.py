from uuid import uuid4

import pytest

from neocortex.schema_manager import SchemaManager


def test_make_schema_name() -> None:
    assert SchemaManager.make_schema_name("alice", "personal") == "ncx_alice__personal"


@pytest.mark.asyncio
async def test_create_graph(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"schema-test-{suffix}"
    purpose = "personal"

    schema_name = await manager.create_graph(agent_id=agent_id, purpose=purpose)

    try:
        assert schema_name == f"ncx_schematest{suffix}__personal"
        exists = await pg_service.fetchval(
            """
            SELECT 1
            FROM information_schema.schemata
            WHERE schema_name = $1
            """,
            schema_name,
        )
        assert exists == 1

        tables = await pg_service.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
            ORDER BY table_name
            """,
            schema_name,
        )
        assert [row["table_name"] for row in tables] == [
            "_migration",
            "edge",
            "edge_type",
            "episode",
            "node",
            "node_alias",
            "node_type",
        ]
    finally:
        await manager.drop_graph(schema_name)


@pytest.mark.asyncio
async def test_create_duplicate_graph(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"duplicate-{suffix}"
    purpose = "research"

    first_schema = await manager.create_graph(agent_id=agent_id, purpose=purpose)
    try:
        second_schema = await manager.create_graph(agent_id=agent_id, purpose=purpose)
        graphs = await manager.list_graphs(agent_id=agent_id)

        assert second_schema == first_schema
        assert len(graphs) == 1
    finally:
        await manager.drop_graph(first_schema)


@pytest.mark.asyncio
async def test_drop_graph(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    schema_name = await manager.create_graph(agent_id=f"drop-{suffix}", purpose="personal")

    dropped = await manager.drop_graph(schema_name)

    assert dropped is True
    exists = await pg_service.fetchval(
        """
        SELECT 1
        FROM information_schema.schemata
        WHERE schema_name = $1
        """,
        schema_name,
    )
    assert exists is None
    registry_entry = await pg_service.fetchval("SELECT 1 FROM graph_registry WHERE schema_name = $1", schema_name)
    assert registry_entry is None


@pytest.mark.asyncio
async def test_list_graphs(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    alice_personal = await manager.create_graph(agent_id=f"alice-{suffix}", purpose="personal")
    alice_research = await manager.create_graph(agent_id=f"alice-{suffix}", purpose="research")
    bob_personal = await manager.create_graph(agent_id=f"bob-{suffix}", purpose="personal")

    try:
        alice_graphs = await manager.list_graphs(agent_id=f"alice-{suffix}")
        assert [graph.purpose for graph in alice_graphs] == ["personal", "research"]

        all_graphs = await manager.list_graphs()
        schema_names = {graph.schema_name for graph in all_graphs}
        assert alice_personal in schema_names
        assert alice_research in schema_names
        assert bob_personal in schema_names
    finally:
        await manager.drop_graph(alice_personal)
        await manager.drop_graph(alice_research)
        await manager.drop_graph(bob_personal)


@pytest.mark.asyncio
async def test_ensure_default_graphs(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    agent_id = f"default-{suffix}"

    first_schema = await manager.ensure_default_graphs(agent_id)
    second_schema = await manager.ensure_default_graphs(agent_id)

    try:
        assert first_schema == second_schema
        graph = await manager.get_graph(agent_id=agent_id, purpose="personal")
        assert graph is not None
        assert graph.schema_name == first_schema
    finally:
        await manager.drop_graph(first_schema)
