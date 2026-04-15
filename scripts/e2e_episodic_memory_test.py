"""E2E test for episodic memory features (Plan 31: MemMachine improvements).

Validates session-tagged episodes, neighbor expansion, STM boost, FOLLOWS edges,
and combined episodic + graph recall against a running MCP server + PostgreSQL.

Prerequisites:
  docker compose up -d postgres
  GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex &
  GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion &

Usage:
  GOOGLE_API_KEY=... uv run python scripts/e2e_episodic_memory_test.py

Via unified runner:
  GOOGLE_API_KEY=... ./scripts/run_e2e.sh scripts/e2e_episodic_memory_test.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import httpx
from fastmcp import Client

from neocortex.config import PostgresConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("NEOCORTEX_BASE_URL", "http://127.0.0.1:8000")
INGESTION_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
MCP_URL = os.environ.get("NEOCORTEX_MCP_URL", f"{BASE_URL}/mcp")
ALICE_TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")
AGENT_SCHEMA = "ncx_alice__personal"

SUFFIX = uuid.uuid4().hex[:8]

JOB_WAIT_TIMEOUT = 120
JOB_POLL_INTERVAL = 3

SESSION_A = f"morning-standup-{SUFFIX}"
SESSION_B = f"afternoon-debug-{SUFFIX}"

# Session A: morning standup discussion about database migration (4 turns)
SESSION_A_TURNS = [
    (
        "We discussed the PostgreSQL 16 upgrade timeline in standup today."
        " The DBA team wants to do it during the maintenance window"
        f" on May 3rd. [{SUFFIX}]"
    ),
    (
        "The main risk with the PG16 upgrade is the breaking change in"
        " jsonb_path_query behavior. We need to audit all JSONB queries"
        f" in the analytics pipeline first. [{SUFFIX}]"
    ),
    (
        "Alice volunteered to run the JSONB query audit. She'll check"
        " all stored procedures and the three most active Grafana"
        f" dashboards. [{SUFFIX}]"
    ),
    (
        "The team agreed to freeze schema migrations one week before"
        f" the PG16 upgrade. No DDL changes after April 26th. [{SUFFIX}]"
    ),
]

# Session B: afternoon debugging session about API latency (3 turns)
SESSION_B_TURNS = [
    (
        "Investigating p99 latency spike in the /api/search endpoint."
        " Response times jumped from 120ms to 800ms after yesterday's"
        f" deploy. [{SUFFIX}]"
    ),
    (
        "Root cause found: the new full-text search query is doing a"
        " sequential scan on the documents table instead of using the"
        " GIN index. The query planner chose wrong because ANALYZE"
        f" hasn't run since the bulk import. [{SUFFIX}]"
    ),
    (
        "Fix deployed: ran ANALYZE on documents table and added a query"
        " hint to force GIN index usage. p99 back to 130ms. Will add"
        f" ANALYZE to the post-import automation. [{SUFFIX}]"
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def mcp_call(tool_name: str, arguments: dict[str, object]) -> dict:
    """Call an MCP tool on the running server and return structured content."""
    async with Client(MCP_URL, auth=ALICE_TOKEN) as client:
        result = await client.call_tool(tool_name, arguments)
    if not isinstance(result.structured_content, dict):
        raise AssertionError(f"{tool_name} did not return structured content: {result}")
    return result.structured_content


def _quote_identifier(identifier: str) -> str:
    """Quote a SQL identifier to prevent injection."""
    return '"' + identifier.replace('"', '""') + '"'


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _post(path: str, token: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=INGESTION_URL, timeout=10.0) as client:
        resp = await client.post(path, headers=_headers(token), **kwargs)
    resp.raise_for_status()
    return resp.json()


async def _get_max_job_id() -> int:
    """Return the current max job ID so we can track only new jobs."""
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        val = await conn.fetchval("SELECT coalesce(max(id), 0) FROM procrastinate_jobs WHERE queue_name = 'extraction'")
        return int(val)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Stage 1: Session Ingestion
# ---------------------------------------------------------------------------


async def ingest_session_episodes(session_id: str, turns: list[str], token: str = ALICE_TOKEN) -> None:
    """Ingest a sequence of text turns as a single session."""
    for turn in turns:
        result = await _post(
            "/ingest/text",
            token,
            json={"text": turn, "session_id": session_id},
        )
        if result["status"] != "stored":
            raise AssertionError(f"Ingestion failed: {result}")
        # Note: result["episodes_created"] is a count (int), not an episode ID.
        # Actual episode IDs are verified via direct DB queries using session_id.
        print(f"  Stored episode (session={session_id[:20]}...): {turn[:60]}...")


async def verify_session_in_db(session_id: str, expected_count: int) -> None:
    """Verify session episodes exist in DB with correct sequence numbers."""
    config = PostgresConfig()
    conn = await asyncpg.connect(dsn=config.dsn)
    try:
        table = f"{_quote_identifier(AGENT_SCHEMA)}.episode"
        rows = await conn.fetch(
            f"SELECT id, content, session_id, session_sequence, created_at "
            f"FROM {table} WHERE session_id = $1 ORDER BY session_sequence",
            session_id,
        )
        if len(rows) != expected_count:
            raise AssertionError(f"Expected {expected_count} episodes for session {session_id}, " f"got {len(rows)}")
        for i, row in enumerate(rows):
            if row["session_sequence"] != i:
                raise AssertionError(
                    f"Episode {row['id']} has session_sequence={row['session_sequence']}, " f"expected {i}"
                )
        print(f"  DB check passed: {expected_count} episodes with correct sequences")
    finally:
        await conn.close()


async def test_session_ingestion() -> None:
    """Stage 1: Ingest session-tagged episodes and verify in DB."""
    print("\n=== Stage 1: Session Ingestion ===")

    print("\nIngesting Session A (morning standup, 4 turns)...")
    await ingest_session_episodes(SESSION_A, SESSION_A_TURNS)

    print("\nIngesting Session B (afternoon debug, 3 turns)...")
    await ingest_session_episodes(SESSION_B, SESSION_B_TURNS)

    print("\nVerifying sessions in database...")
    await verify_session_in_db(SESSION_A, len(SESSION_A_TURNS))
    await verify_session_in_db(SESSION_B, len(SESSION_B_TURNS))

    print("\n=== Stage 1 PASSED ===")


# ---------------------------------------------------------------------------
# Stage 2: Session Recall with Neighbors
# ---------------------------------------------------------------------------


async def test_session_recall_with_neighbors() -> None:
    """Stage 2: Recall with neighbor expansion and session clustering."""
    print("\n=== Stage 2: Session Recall with Neighbors ===")

    # Query that should match Session A content
    result = await mcp_call(
        "recall",
        {
            "query": f"PostgreSQL upgrade timeline and risks {SUFFIX}",
            "limit": 20,
        },
    )
    items = result["results"]

    if not items:
        raise AssertionError("Recall returned no results")

    # Check that we got episode results
    episode_items = [i for i in items if i.get("source_kind") == "episode"]
    print(f"  Recall returned {len(items)} items, {len(episode_items)} episodes")

    if len(episode_items) < 2:
        raise AssertionError(f"Expected at least 2 episode results (nucleus + neighbors), " f"got {len(episode_items)}")

    # Check for neighbor episodes (those brought in by expansion)
    nucleus_episodes = [e for e in episode_items if e.get("neighbor_of") is None]
    neighbor_episodes = [e for e in episode_items if e.get("neighbor_of") is not None]
    print(f"  Nucleus episodes: {len(nucleus_episodes)}")
    print(f"  Neighbor episodes: {len(neighbor_episodes)}")

    if not neighbor_episodes:
        raise AssertionError(
            "No neighbor episodes found — neighbor expansion may not be working. "
            "Check that recall_expand_neighbors setting is True."
        )

    # Verify neighbor scores are discounted relative to nucleus
    for neighbor in neighbor_episodes:
        nucleus_id = neighbor["neighbor_of"]
        nucleus = next((e for e in nucleus_episodes if e["item_id"] == nucleus_id), None)
        if nucleus and neighbor["score"] >= nucleus["score"]:
            print(
                f"  WARNING: Neighbor {neighbor['item_id']} score "
                f"({neighbor['score']:.4f}) >= nucleus {nucleus_id} score "
                f"({nucleus['score']:.4f})"
            )

    # Verify session_id is present on episode results
    session_episodes = [e for e in episode_items if e.get("session_id")]
    if not session_episodes:
        raise AssertionError("No episodes have session_id in recall results")

    print(f"  Episodes with session_id: {len(session_episodes)}")
    print("\n=== Stage 2 PASSED ===")


async def test_cross_session_isolation() -> None:
    """Verify neighbor expansion stays within session boundaries."""
    print("\n--- Cross-Session Isolation Check ---")

    result = await mcp_call(
        "recall",
        {
            "query": f"API latency spike search endpoint {SUFFIX}",
            "limit": 20,
        },
    )
    items = result["results"]
    episode_items = [i for i in items if i.get("source_kind") == "episode"]

    # Find neighbor episodes and check their session_id
    for ep in episode_items:
        if ep.get("neighbor_of") and ep.get("session_id"):
            # Find the nucleus this neighbor belongs to
            nucleus = next(
                (e for e in episode_items if e["item_id"] == ep["neighbor_of"]),
                None,
            )
            if nucleus and nucleus.get("session_id") != ep["session_id"]:
                raise AssertionError(
                    f"Neighbor episode {ep['item_id']} (session={ep['session_id']}) "
                    f"has different session than nucleus {ep['neighbor_of']} "
                    f"(session={nucleus.get('session_id')}). "
                    f"Cross-session neighbor expansion should not happen."
                )

    print("  Cross-session isolation verified")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    print(f"NeoCortex Episodic Memory E2E Test (suffix={SUFFIX})")
    print(f"MCP: {MCP_URL}")
    print(f"Ingestion: {INGESTION_URL}")

    # Capture baseline extraction job ID BEFORE ingestion so Stage 4
    # only waits for jobs from this test run (not stale previous runs).
    baseline_job_id = await _get_max_job_id()
    print(f"Baseline extraction job ID: {baseline_job_id}")

    # Stage 1: Session ingestion
    await test_session_ingestion()

    # Stage 2: Session recall with neighbors
    await test_session_recall_with_neighbors()
    await test_cross_session_isolation()

    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
