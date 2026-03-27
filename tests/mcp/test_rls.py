import os
from uuid import uuid4

import pytest

from neocortex.db.adapter import GraphServiceAdapter
from neocortex.db.scoped import scoped_connection
from neocortex.graph_service import GraphService

pytestmark = pytest.mark.skipif(
    os.getenv("NEOCORTEX_RUN_RLS_TESTS") != "1",
    reason="Set NEOCORTEX_RUN_RLS_TESTS=1 with PostgreSQL running to enable RLS tests.",
)


async def _assert_rls_ready(pg_service) -> None:
    owner_role_exists = await pg_service.fetchval("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'episode' AND column_name = 'owner_role'
        """)
    policy_exists = await pg_service.fetchval("SELECT 1 FROM pg_policy WHERE polname = 'episode_select_policy'")
    if not owner_role_exists or not policy_exists:
        pytest.skip("RLS migration has not been applied to the current database.")


async def _get_concept_type_id(pg_service) -> int:
    type_id = await pg_service.fetchval("SELECT id FROM node_type WHERE name = 'Concept'")
    if type_id is None:
        raise AssertionError("Seed ontology is missing the Concept node type.")
    return int(type_id)


@pytest.mark.asyncio
async def test_agent_sees_only_own_episodes(pg_service) -> None:
    await _assert_rls_ready(pg_service)
    adapter = GraphServiceAdapter(GraphService(pg_service), pool=pg_service.pool)
    suffix = uuid4().hex[:8]
    agent_a = f"test-agent-a-{suffix}"
    agent_b = f"test-agent-b-{suffix}"

    await adapter.store_episode(agent_a, f"A episode {suffix}")
    await adapter.store_episode(agent_b, f"B episode {suffix}")

    async with scoped_connection(pg_service.pool, agent_a) as conn_a:
        rows_a = await conn_a.fetch("SELECT content FROM episode ORDER BY id")
    async with scoped_connection(pg_service.pool, agent_b) as conn_b:
        rows_b = await conn_b.fetch("SELECT content FROM episode ORDER BY id")

    assert [row["content"] for row in rows_a] == [f"A episode {suffix}"]
    assert [row["content"] for row in rows_b] == [f"B episode {suffix}"]


@pytest.mark.asyncio
async def test_agent_sees_shared_nodes(pg_service) -> None:
    await _assert_rls_ready(pg_service)
    suffix = uuid4().hex[:8]
    concept_type_id = await _get_concept_type_id(pg_service)
    node_name = f"Shared Node {suffix}"

    row = await pg_service.fetchrow(
        """
        INSERT INTO node (type_id, name, content, source, owner_role)
        VALUES ($1, $2, $3, $4, NULL)
        RETURNING id
        """,
        concept_type_id,
        node_name,
        f"Visible to all agents {suffix}",
        f"test_shared_{suffix}",
    )
    assert row is not None

    async with scoped_connection(pg_service.pool, f"shared-a-{suffix}") as conn_a:
        count_a = await conn_a.fetchval("SELECT count(*) FROM node WHERE name = $1", node_name)
    async with scoped_connection(pg_service.pool, f"shared-b-{suffix}") as conn_b:
        count_b = await conn_b.fetchval("SELECT count(*) FROM node WHERE name = $1", node_name)

    assert int(count_a) == 1
    assert int(count_b) == 1


@pytest.mark.asyncio
async def test_agent_cannot_modify_other_agent_nodes(pg_service) -> None:
    await _assert_rls_ready(pg_service)
    suffix = uuid4().hex[:8]
    concept_type_id = await _get_concept_type_id(pg_service)
    agent_a = f"node-owner-{suffix}"
    agent_b = f"node-other-{suffix}"

    async with scoped_connection(pg_service.pool, agent_a) as conn_a:
        row = await conn_a.fetchrow(
            """
            INSERT INTO node (type_id, name, content, source)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            concept_type_id,
            f"Private Node {suffix}",
            "agent a only",
            f"test_private_{suffix}",
        )
    assert row is not None
    node_id = int(row["id"])

    async with scoped_connection(pg_service.pool, agent_b) as conn_b:
        update_status = await conn_b.execute("UPDATE node SET content = $1 WHERE id = $2", "hijacked", node_id)
        delete_status = await conn_b.execute("DELETE FROM node WHERE id = $1", node_id)

    assert update_status == "UPDATE 0"
    assert delete_status == "DELETE 0"


@pytest.mark.asyncio
async def test_ontology_tables_are_shared(pg_service) -> None:
    await _assert_rls_ready(pg_service)
    suffix = uuid4().hex[:8]
    type_name = f"Test_SharedOntology_{suffix}"

    async with scoped_connection(pg_service.pool, f"ontology-writer-{suffix}") as conn_a:
        await conn_a.execute(
            "INSERT INTO node_type (name, description) VALUES ($1, $2)",
            type_name,
            "shared ontology test",
        )

    async with scoped_connection(pg_service.pool, f"ontology-reader-{suffix}") as conn_b:
        exists = await conn_b.fetchval("SELECT 1 FROM node_type WHERE name = $1", type_name)

    assert exists == 1
