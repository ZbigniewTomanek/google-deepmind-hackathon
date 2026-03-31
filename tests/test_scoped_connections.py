from uuid import uuid4

import pytest

from neocortex.db.scoped import _validate_schema_name, graph_scoped_connection, schema_scoped_connection
from neocortex.schema_manager import SchemaManager


def test_validate_schema_name_accepts_valid_graph_schema() -> None:
    _validate_schema_name("ncx_alice__personal")


@pytest.mark.parametrize("schema_name", ["ncx___", "ncx_", "public", "ncx_a"])
def test_validate_schema_name_rejects_invalid_values(schema_name: str) -> None:
    with pytest.raises(ValueError, match="Invalid graph schema name"):
        _validate_schema_name(schema_name)


@pytest.mark.asyncio
async def test_schema_scoped_connection_uses_requested_schema(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    schema_name = await manager.create_graph(agent_id=f"scope-{suffix}", purpose="personal")

    try:
        async with schema_scoped_connection(pg_service.pool, schema_name) as conn:
            current_schema = await conn.fetchval("SELECT current_schema()")
            await conn.execute(
                """
                INSERT INTO episode (agent_id, content, source_type, metadata)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                f"test_scope_{suffix}",
                f"schema scoped {suffix}",
                "test",
                "{}",
            )

        assert current_schema == schema_name
        count = await pg_service.fetchval(
            f"SELECT count(*) FROM {schema_name}.episode WHERE agent_id = $1", f"test_scope_{suffix}"
        )
        assert int(count) == 1
    finally:
        await manager.drop_graph(schema_name)


@pytest.mark.asyncio
async def test_graph_scoped_connection_in_shared_schema_keeps_base_role(pg_service) -> None:
    """Shared graphs no longer use RLS, so the connection keeps the pool owner role."""
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    schema_name = await manager.create_graph(agent_id="shared", purpose=f"knowledge_{suffix}", is_shared=True)
    agent_id = f"shared-reader-{suffix}"

    try:
        async with pg_service.pool.acquire() as conn:
            baseline_role = await conn.fetchval("SELECT current_role")

        async with graph_scoped_connection(pg_service.pool, schema_name, agent_id=agent_id) as conn:
            search_path = await conn.fetchval("SHOW search_path")
            current_role = await conn.fetchval("SELECT current_role")

        assert search_path == f"{schema_name}, public"
        # No SET LOCAL ROLE — shared graphs keep the pool owner role
        assert current_role == baseline_role
    finally:
        await manager.drop_graph(schema_name)


@pytest.mark.asyncio
async def test_graph_scoped_connection_in_private_schema_keeps_base_role(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    schema_name = await manager.create_graph(agent_id=f"private-{suffix}", purpose="personal")

    try:
        async with pg_service.pool.acquire() as conn:
            baseline_role = await conn.fetchval("SELECT current_role")

        async with graph_scoped_connection(pg_service.pool, schema_name, agent_id=f"reader-{suffix}") as conn:
            current_schema = await conn.fetchval("SELECT current_schema()")
            current_role = await conn.fetchval("SELECT current_role")

        assert current_schema == schema_name
        assert current_role == baseline_role
    finally:
        await manager.drop_graph(schema_name)


@pytest.mark.asyncio
async def test_execute_in_schema_runs_against_requested_graph_schema(pg_service) -> None:
    manager = SchemaManager(pg_service)
    suffix = uuid4().hex[:8]
    schema_name = await manager.create_graph(agent_id=f"execute-{suffix}", purpose="personal")

    try:
        status = await pg_service.execute_in_schema(
            schema_name,
            """
            INSERT INTO episode (agent_id, content, source_type, metadata)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            f"test_execute_{suffix}",
            f"execute in schema {suffix}",
            "test",
            "{}",
        )

        assert status == "INSERT 0 1"
        count = await pg_service.fetchval(
            f"SELECT count(*) FROM {schema_name}.episode WHERE agent_id = $1",
            f"test_execute_{suffix}",
        )
        assert int(count) == 1
    finally:
        await manager.drop_graph(schema_name)
