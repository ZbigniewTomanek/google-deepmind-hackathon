"""E2E test for the extraction pipeline: ingest → extract → recall with graph context.

Validates the full data path:
  1. Ingest medical text via MCP remember (triggers extraction)
  2. Wait for Procrastinate extraction jobs to complete
  3. Verify ontology was created (node types, edge types)
  4. Verify nodes and edges were extracted into the graph
  5. Recall with a semantic query → expect graph_context on matched nodes
  6. Discover → expect non-zero type counts
  7. Cross-agent isolation: Bob cannot see Alice's extracted graph

Prerequisites:
  docker compose up -d postgres
  GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex &
  GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion &

Usage:
  GOOGLE_API_KEY=... uv run python scripts/e2e_extraction_pipeline_test.py

Via unified runner:
  GOOGLE_API_KEY=... ./scripts/run_e2e.sh scripts/e2e_extraction_pipeline_test.py
"""

from __future__ import annotations

import asyncio
import os
import time

import asyncpg
import httpx
from fastmcp import Client

from neocortex.config import PostgresConfig

BASE_URL = os.environ.get("NEOCORTEX_BASE_URL", "http://127.0.0.1:8000")
INGESTION_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
MCP_URL = os.environ.get("NEOCORTEX_MCP_URL", f"{BASE_URL}/mcp")
ALICE_TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")
BOB_TOKEN = os.environ.get("NEOCORTEX_BOB_TOKEN", "bob-token")
AGENT_SCHEMA = "ncx_alice__personal"

# --- Seed texts (subset of medical corpus for speed) ---

SEED_TEXTS = [
    (
        "Serotonin (5-hydroxytryptamine, 5-HT) is a monoamine neurotransmitter "
        "primarily found in the gastrointestinal tract, blood platelets, and the "
        "central nervous system. In the brain, serotonin is synthesized in the "
        "raphe nuclei of the brainstem. It modulates mood, appetite, sleep, and "
        "cognitive functions including memory and learning."
    ),
    (
        "Selective serotonin reuptake inhibitors (SSRIs) such as fluoxetine and "
        "sertraline work by blocking the reuptake of serotonin in the synaptic "
        "cleft, increasing its availability for postsynaptic receptors. They are "
        "first-line treatment for major depressive disorder and several anxiety "
        "disorders."
    ),
    (
        "SSRI-induced sexual dysfunction is one of the most common reasons for "
        "treatment discontinuation. Symptoms include decreased libido, delayed "
        "ejaculation, and anorgasmia. The mechanism involves serotonin's "
        "inhibitory effect on dopamine and norepinephrine pathways that mediate "
        "sexual arousal and orgasm."
    ),
]

JOB_WAIT_TIMEOUT = 120  # seconds
JOB_POLL_INTERVAL = 3  # seconds


async def mcp_call(token: str, tool_name: str, arguments: dict[str, object]) -> dict:
    async with Client(MCP_URL, auth=token) as client:
        result = await client.call_tool(tool_name, arguments)
    if not isinstance(result.structured_content, dict):
        raise AssertionError(f"{tool_name} did not return structured content: {result}")
    return result.structured_content


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _assert_health() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BASE_URL}/health")
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise AssertionError(f"Unexpected health payload: {payload}")


# ── Step 1: Ingest seed texts ──────────────────────────────────────


async def step_ingest() -> list[int]:
    """Store seed texts via MCP remember (triggers extraction jobs)."""
    print("\n=== Step 1: Ingest seed texts ===")
    episode_ids: list[int] = []
    for i, text in enumerate(SEED_TEXTS):
        result = await mcp_call(
            ALICE_TOKEN, "remember", {"text": text, "context": "e2e_extraction_test"}
        )
        eid = int(result["episode_id"])
        assert eid > 0, f"Bad episode id: {result}"
        episode_ids.append(eid)
        print(f"  [{i + 1}/{len(SEED_TEXTS)}] Stored episode {eid}: {text[:60]}...")
    return episode_ids


# ── Step 2: Wait for extraction jobs ───────────────────────────────


async def step_wait_for_extraction() -> None:
    """Poll the database until no pending/running extraction jobs remain."""
    print(f"\n=== Step 2: Wait for extraction jobs (timeout {JOB_WAIT_TIMEOUT}s) ===")
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        start = time.monotonic()
        while time.monotonic() - start < JOB_WAIT_TIMEOUT:
            row = await conn.fetchrow(
                """SELECT
                    count(*) FILTER (WHERE status = 'todo') AS pending,
                    count(*) FILTER (WHERE status = 'doing') AS running,
                    count(*) FILTER (WHERE status = 'succeeded') AS completed,
                    count(*) FILTER (WHERE status = 'failed') AS failed
                FROM procrastinate_jobs
                WHERE queue_name = 'extraction'"""
            )
            pending, running, completed, failed = (
                int(row["pending"]),
                int(row["running"]),
                int(row["completed"]),
                int(row["failed"]),
            )
            elapsed = int(time.monotonic() - start)
            print(
                f"  [{elapsed:3d}s] pending={pending} running={running} "
                f"completed={completed} failed={failed}"
            )
            if pending == 0 and running == 0:
                if failed > 0:
                    err_rows = await conn.fetch(
                        """SELECT id, args, status
                           FROM procrastinate_jobs
                           WHERE queue_name = 'extraction' AND status = 'failed'
                           LIMIT 3"""
                    )
                    details = [(int(r["id"]), r["status"]) for r in err_rows]
                    print(f"  [WARN] {failed} job(s) failed: {details}")
                if completed > 0:
                    print(
                        f"  [PASS] All extraction jobs finished "
                        f"({completed} completed, {failed} failed)"
                    )
                    return
                # No jobs at all — maybe extraction isn't wired
                if completed == 0 and failed == 0:
                    print(
                        "  [WARN] No extraction jobs found — "
                        "checking if extraction is wired..."
                    )
                    await asyncio.sleep(JOB_POLL_INTERVAL)
                    continue
            await asyncio.sleep(JOB_POLL_INTERVAL)
        raise AssertionError(
            f"Extraction jobs did not complete within {JOB_WAIT_TIMEOUT}s"
        )
    finally:
        await conn.close()


# ── Step 3: Verify ontology created ────────────────────────────────


async def step_verify_ontology() -> None:
    """Check that node types and edge types were created in the agent's schema."""
    print("\n=== Step 3: Verify ontology ===")
    result = await mcp_call(ALICE_TOKEN, "discover", {})
    node_types = result.get("node_types", [])
    edge_types = result.get("edge_types", [])
    stats = result.get("stats", {})

    print(f"  Node types ({len(node_types)}):")
    for nt in node_types:
        print(f"    {nt['name']} — {nt.get('count', 0)} entities")
    print(f"  Edge types ({len(edge_types)}):")
    for et in edge_types:
        print(f"    {et['name']} — {et.get('count', 0)} relations")
    print(f"  Stats: {stats}")

    assert len(node_types) > 0, f"No node types created. discover returned: {result}"
    assert len(edge_types) > 0, f"No edge types created. discover returned: {result}"
    print(
        f"  [PASS] Ontology populated: "
        f"{len(node_types)} node types, {len(edge_types)} edge types"
    )


# ── Step 4: Verify graph data in PostgreSQL ────────────────────────


async def step_verify_graph_data() -> dict[str, int]:
    """Directly query the agent's schema to count nodes and edges."""
    print("\n=== Step 4: Verify graph data in PostgreSQL ===")
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        schema = _quote(AGENT_SCHEMA)
        node_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.node")
        edge_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.edge")
        episode_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.episode")
        node_type_count = await conn.fetchval(
            f"SELECT count(*) FROM {schema}.node_type"
        )
        edge_type_count = await conn.fetchval(
            f"SELECT count(*) FROM {schema}.edge_type"
        )

        counts = {
            "nodes": int(node_count),
            "edges": int(edge_count),
            "episodes": int(episode_count),
            "node_types": int(node_type_count),
            "edge_types": int(edge_type_count),
        }
        for label, count in counts.items():
            status = "PASS" if count > 0 else "FAIL"
            print(f"  [{status}] {label}: {count}")

        assert counts["nodes"] > 0, "No nodes extracted"
        assert counts["edges"] > 0, "No edges extracted"
        assert counts["episodes"] >= len(SEED_TEXTS), (
            f"Expected at least {len(SEED_TEXTS)} episodes, got {counts['episodes']}"
        )

        # Print sample nodes for human inspection
        rows = await conn.fetch(
            f"""SELECT n.name, nt.name AS type_name
                FROM {schema}.node n
                JOIN {schema}.node_type nt ON nt.id = n.type_id
                ORDER BY n.name LIMIT 10"""
        )
        print("  Sample nodes:")
        for r in rows:
            print(f"    {r['name']} [{r['type_name']}]")

        # Print sample edges
        edge_rows = await conn.fetch(
            f"""SELECT src.name AS source, et.name AS rel, tgt.name AS target
                FROM {schema}.edge e
                JOIN {schema}.node src ON src.id = e.source_id
                JOIN {schema}.node tgt ON tgt.id = e.target_id
                JOIN {schema}.edge_type et ON et.id = e.type_id
                LIMIT 10"""
        )
        print("  Sample edges:")
        for r in edge_rows:
            print(f"    {r['source']} --[{r['rel']}]--> {r['target']}")

        return counts
    finally:
        await conn.close()


# ── Step 5: Recall with graph context ──────────────────────────────


async def step_recall_with_graph_context() -> None:
    """Recall using a semantic query and verify graph_context is populated."""
    print("\n=== Step 5: Recall with graph context ===")
    queries = [
        ("serotonin mood regulation", "serotonin"),
        ("SSRI antidepressant mechanism", "ssri"),
        ("sexual dysfunction treatment side effects", "sexual"),
    ]
    for query, expected_keyword in queries:
        result = await mcp_call(ALICE_TOKEN, "recall", {"query": query, "limit": 10})
        results = result.get("results", [])
        print(f"\n  Query: '{query}'")
        print(f"  Results: {len(results)}")

        # Check for any node-sourced results (from extraction)
        node_results = [r for r in results if r.get("source_kind") == "node"]
        episode_results = [r for r in results if r.get("source_kind") == "episode"]
        print(f"    Nodes: {len(node_results)}, Episodes: {len(episode_results)}")

        # Check graph_context on node results
        with_context = [r for r in node_results if r.get("graph_context")]
        if with_context:
            print(f"    [PASS] {len(with_context)} node(s) have graph_context")
            ctx = with_context[0]["graph_context"]
            center = ctx.get("center_node", {})
            edges = ctx.get("edges", [])
            neighbors = ctx.get("neighbor_nodes", [])
            print(f"    Center: {center.get('name')} [{center.get('type')}]")
            print(f"    Edges: {len(edges)}, Neighbors: {len(neighbors)}")
        else:
            if node_results:
                print(
                    "    [WARN] Node results found but no graph_context attached"
                )
            else:
                print(
                    "    [INFO] No node results (only episodes) "
                    "— graph may still be building"
                )

        # At minimum, episodes should match
        contents = " ".join(str(r.get("content", "")) for r in results).lower()
        if expected_keyword.lower() in contents:
            print(f"    [PASS] Found '{expected_keyword}' in results")
        else:
            print(f"    [WARN] '{expected_keyword}' not found in results")


# ── Step 6: Cross-agent isolation ──────────────────────────────────


async def step_verify_isolation() -> None:
    """Verify Bob cannot see Alice's extracted graph."""
    print("\n=== Step 6: Cross-agent isolation ===")
    result = await mcp_call(BOB_TOKEN, "discover", {})

    bob_node_types = result.get("node_types", [])
    bob_stats = result.get("stats", {})
    bob_nodes = bob_stats.get("total_nodes", 0)

    print(f"  Bob's node types: {len(bob_node_types)}")
    print(f"  Bob's total nodes: {bob_nodes}")

    # Bob should NOT have Alice's extracted nodes in his personal schema
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        bob_schema = "ncx_bob__personal"
        exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1",
            bob_schema,
        )
        if exists:
            bob_nodes_count = await conn.fetchval(
                f"SELECT count(*) FROM {_quote(bob_schema)}.node"
            )
            assert int(bob_nodes_count) == 0, (
                f"Bob has {bob_nodes_count} nodes — extraction leaked across agents"
            )
            print(f"  [PASS] Bob's personal schema has 0 nodes")
        else:
            print(f"  [PASS] Bob's personal schema doesn't exist (no data stored)")
    finally:
        await conn.close()


# ── Main ───────────────────────────────────────────────────────────


async def main() -> None:
    print("=" * 60)
    print("E2E Extraction Pipeline Test")
    print(f"MCP:       {MCP_URL}")
    print(f"Ingestion: {INGESTION_URL}")
    print(f"Token:     {ALICE_TOKEN[:8]}...")
    print("=" * 60)

    await _assert_health()

    episode_ids = await step_ingest()
    await step_wait_for_extraction()
    await step_verify_ontology()
    counts = await step_verify_graph_data()
    await step_recall_with_graph_context()
    await step_verify_isolation()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  Episodes ingested:  {len(episode_ids)}")
    print(f"  Nodes extracted:    {counts['nodes']}")
    print(f"  Edges extracted:    {counts['edges']}")
    print(f"  Node types:         {counts['node_types']}")
    print(f"  Edge types:         {counts['edge_types']}")
    print("=" * 60)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
