"""E2E smoke test for the multi-graph NeoCortex server.

Prerequisites:
  docker compose up -d postgres
  NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex

Usage:
  uv run python scripts/e2e_mcp_test.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import httpx
from fastmcp import Client

from neocortex.config import PostgresConfig

BASE_URL = os.environ.get("NEOCORTEX_BASE_URL", "http://127.0.0.1:8000")
MCP_URL = os.environ.get("NEOCORTEX_MCP_URL", f"{BASE_URL}/mcp")
INGESTION_BASE_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
ADMIN_TOKEN = os.environ.get("NEOCORTEX_ADMIN_TOKEN", "admin-token-neocortex")
ALICE_TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")
BOB_TOKEN = os.environ.get("NEOCORTEX_BOB_TOKEN", "bob-token")


async def mcp_call(token: str, tool_name: str, arguments: dict[str, object]) -> dict:
    async with Client(MCP_URL, auth=token) as client:
        result = await client.call_tool(tool_name, arguments)
    if not isinstance(result.structured_content, dict):
        raise AssertionError(f"{tool_name} did not return structured content.")
    return result.structured_content


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _assert_health() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BASE_URL}/health")
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise AssertionError(f"Unexpected health payload: {payload}")


async def _assert_schema_state(
    conn: asyncpg.Connection,
    schema_name: str,
    expected_content: str,
    forbidden_content: str,
) -> None:
    schema_exists = await conn.fetchval(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1",
        schema_name,
    )
    if schema_exists != 1:
        raise AssertionError(f"Schema {schema_name} does not exist.")

    table_name = f"{_quote_identifier(schema_name)}.episode"
    rows = await conn.fetch(
        f"SELECT content FROM {table_name} WHERE content IN ($1, $2) ORDER BY content",
        expected_content,
        forbidden_content,
    )
    contents = [str(row["content"]) for row in rows]
    if expected_content not in contents:
        raise AssertionError(f"Expected content missing from {schema_name}: {expected_content}")
    if forbidden_content in contents:
        raise AssertionError(f"Forbidden content leaked into {schema_name}: {forbidden_content}")


async def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    alice_content = f"alicepizza stage10 {suffix}"
    bob_content = f"bobsushi stage10 {suffix}"
    alice_schema = "ncx_alice__personal"
    bob_schema = "ncx_bob__personal"
    shared_schema = "ncx_shared__knowledge"

    print("Checking server health...")
    await _assert_health()

    print("Storing Alice memory...")
    remember_alice = await mcp_call(
        ALICE_TOKEN,
        "remember",
        {"text": alice_content, "context": "stage10 smoke test"},
    )
    if int(remember_alice["episode_id"]) <= 0:
        raise AssertionError(f"Unexpected Alice episode id: {remember_alice}")

    print("Storing Bob memory...")
    remember_bob = await mcp_call(
        BOB_TOKEN,
        "remember",
        {"text": bob_content, "context": "stage10 smoke test"},
    )
    if int(remember_bob["episode_id"]) <= 0:
        raise AssertionError(f"Unexpected Bob episode id: {remember_bob}")

    print("Verifying Alice recall isolation...")
    alice_recall = await mcp_call(ALICE_TOKEN, "recall", {"query": "alicepizza"})
    alice_results = [str(item["content"]).lower() for item in alice_recall["results"]]
    if not any(alice_content in content for content in alice_results):
        raise AssertionError(f"Alice recall did not return her memory: {alice_recall}")
    if any(bob_content in content for content in alice_results):
        raise AssertionError(f"Alice recall leaked Bob memory: {alice_recall}")

    print("Verifying Bob recall isolation...")
    bob_recall = await mcp_call(BOB_TOKEN, "recall", {"query": "bobsushi"})
    bob_results = [str(item["content"]).lower() for item in bob_recall["results"]]
    if not any(bob_content in content for content in bob_results):
        raise AssertionError(f"Bob recall did not return his memory: {bob_recall}")
    if any(alice_content in content for content in bob_results):
        raise AssertionError(f"Bob recall leaked Alice memory: {bob_recall}")

    print("Granting read access to shared graph for discover test...")
    async with httpx.AsyncClient(base_url=INGESTION_BASE_URL, timeout=10.0) as client:
        for agent in ("alice", "bob"):
            resp = await client.post(
                "/admin/permissions",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                json={"agent_id": agent, "schema_name": shared_schema, "can_read": True},
            )
            if resp.status_code != 200:
                raise AssertionError(f"Failed to grant read to {agent}: {resp.status_code} {resp.text}")

    print("Verifying discover_graphs visibility...")
    alice_graphs_result = await mcp_call(ALICE_TOKEN, "discover_graphs", {})
    bob_graphs_result = await mcp_call(BOB_TOKEN, "discover_graphs", {})
    alice_graph_names = [g["schema_name"] for g in alice_graphs_result["graphs"]]
    bob_graph_names = [g["schema_name"] for g in bob_graphs_result["graphs"]]
    if alice_schema not in alice_graph_names or shared_schema not in alice_graph_names:
        raise AssertionError(f"Alice discover_graphs incomplete: {alice_graph_names}")
    if bob_schema not in bob_graph_names or shared_schema not in bob_graph_names:
        raise AssertionError(f"Bob discover_graphs incomplete: {bob_graph_names}")

    print("Verifying discover_ontology cognitive stats shape...")
    alice_ontology = await mcp_call(ALICE_TOKEN, "discover_ontology", {"graph_name": alice_schema})
    alice_stats = alice_ontology.get("stats", {})
    for key in (
        "total_nodes",
        "total_edges",
        "total_episodes",
        "forgotten_nodes",
        "consolidated_episodes",
        "avg_activation",
    ):
        if key not in alice_stats:
            raise AssertionError(f"Missing stat '{key}' in discover_ontology: {alice_stats}")
    print(f"  [PASS] Cognitive stats present: {alice_stats}")

    print("Verifying discover_domains returns seed domains...")
    domains_result = await mcp_call(ALICE_TOKEN, "discover_domains", {})
    domain_slugs = [d["slug"] for d in domains_result.get("domains", [])]
    if len(domain_slugs) > 0:
        print(f"  [PASS] discover_domains returned {len(domain_slugs)} domains: {domain_slugs}")
    else:
        msg = domains_result.get("message", "")
        print(f"  [INFO] No domains returned ({msg}) — domain routing may be disabled")

    print("Verifying PostgreSQL schemas and data isolation...")
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        for schema_name in (alice_schema, bob_schema, shared_schema):
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1",
                schema_name,
            )
            if exists != 1:
                raise AssertionError(f"Schema {schema_name} is missing.")

        await _assert_schema_state(conn, alice_schema, alice_content, bob_content)
        await _assert_schema_state(conn, bob_schema, bob_content, alice_content)
    finally:
        await conn.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
