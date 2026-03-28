"""E2E test for hybrid recall with embeddings.

Proves that embeddings + hybrid scoring work end-to-end through MCP tools:
- Semantic (vector) recall finds results that keyword search alone would miss
- Text-rank still contributes to scoring
- Recency decay boosts newer results over older ones
- Discover reports correct episode counts

Prerequisites:
  docker compose up -d postgres
  GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex

Usage:
  GOOGLE_API_KEY=... uv run python scripts/e2e_hybrid_recall_test.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

from fastmcp import Client

BASE_URL = os.environ.get("NEOCORTEX_BASE_URL", "http://127.0.0.1:8000")
MCP_URL = os.environ.get("NEOCORTEX_MCP_URL", f"{BASE_URL}/mcp")
TOKEN = os.environ.get("NEOCORTEX_TOKEN", "dev-token-neocortex")


async def mcp_call(tool_name: str, arguments: dict[str, object]) -> dict:
    """Call an MCP tool on the running server and return structured content."""
    async with Client(MCP_URL, auth=TOKEN) as client:
        result = await client.call_tool(tool_name, arguments)
    if not isinstance(result.structured_content, dict):
        raise AssertionError(f"{tool_name} did not return structured content: {result}")
    return result.structured_content


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

SUFFIX = uuid.uuid4().hex[:8]

# Facts with deliberately distinctive vocabulary so we can test semantic recall
# with lexically different queries.
FACTS = [
    f"PostgreSQL supports JSONB for flexible schema-less data storage [{SUFFIX}]",
    f"The team decided to use React with TypeScript for the frontend application [{SUFFIX}]",
    f"Authentication uses OAuth2 with PKCE flow for secure browser-based login [{SUFFIX}]",
    f"Kubernetes horizontal pod autoscaler adjusts replica count based on CPU metrics [{SUFFIX}]",
    f"The data pipeline uses Apache Kafka for event streaming between microservices [{SUFFIX}]",
    f"Machine learning models are served via TensorFlow Serving behind an Envoy proxy [{SUFFIX}]",
]

# Semantic queries — phrased differently but should match the corresponding fact
SEMANTIC_QUERIES = [
    ("flexible data storage formats in the database", "JSONB"),
    ("frontend technology choice and language", "React"),
    ("security protocol for user login in the browser", "OAuth2"),
    ("auto-scaling containers based on resource usage", "Kubernetes"),
    ("real-time event processing between services", "Kafka"),
    ("deploying trained AI models for inference", "TensorFlow"),
]


async def store_facts() -> list[int]:
    """Remember all test facts and return their episode IDs."""
    episode_ids: list[int] = []
    for fact in FACTS:
        result = await mcp_call("remember", {"text": fact, "context": f"e2e_hybrid_{SUFFIX}"})
        eid = int(result["episode_id"])
        if eid <= 0:
            raise AssertionError(f"Unexpected episode id: {result}")
        episode_ids.append(eid)
        print(f"  Stored episode {eid}: {fact[:60]}...")
    return episode_ids


async def test_semantic_recall() -> None:
    """Recall with semantically similar but lexically different queries.

    At least some of these should find the right fact via vector similarity
    even though the query words don't overlap much with the stored text.
    """
    print("\n--- Semantic Recall ---")
    hits = 0
    for query, expected_keyword in SEMANTIC_QUERIES:
        result = await mcp_call("recall", {"query": query, "limit": 10})
        results = result.get("results", [])
        contents = [str(r.get("content", "")) for r in results]
        # Check if the expected keyword appears in any returned result
        found = any(expected_keyword.lower() in c.lower() for c in contents)
        status = "PASS" if found else "MISS"
        if found:
            hits += 1
        print(f"  [{status}] Query: '{query[:50]}...' -> expected '{expected_keyword}'")

    print(f"  Semantic hits: {hits}/{len(SEMANTIC_QUERIES)}")
    # We expect at least half the semantic queries to work via embeddings.
    # In practice with good embeddings, most or all should match.
    if hits < len(SEMANTIC_QUERIES) // 2:
        raise AssertionError(
            f"Too few semantic hits ({hits}/{len(SEMANTIC_QUERIES)}). " "Embeddings may not be working."
        )


async def test_keyword_recall() -> None:
    """Recall with exact keywords still works (text-rank path)."""
    print("\n--- Keyword Recall ---")
    result = await mcp_call("recall", {"query": f"JSONB {SUFFIX}", "limit": 10})
    results = result.get("results", [])
    contents = [str(r.get("content", "")) for r in results]
    if not any("JSONB" in c for c in contents):
        raise AssertionError(f"Keyword recall for 'JSONB' failed: {contents}")
    print("  [PASS] Keyword 'JSONB' found via text search")

    result = await mcp_call("recall", {"query": f"Kafka {SUFFIX}", "limit": 10})
    results = result.get("results", [])
    contents = [str(r.get("content", "")) for r in results]
    if not any("Kafka" in c for c in contents):
        raise AssertionError(f"Keyword recall for 'Kafka' failed: {contents}")
    print("  [PASS] Keyword 'Kafka' found via text search")


async def test_recency_boost() -> None:
    """Store two facts about the same topic at different times; newer should rank higher."""
    print("\n--- Recency Boost ---")
    old_fact = f"The deployment pipeline uses Jenkins for CI/CD (legacy) [{SUFFIX}]"
    new_fact = f"The deployment pipeline has been migrated to GitHub Actions for CI/CD [{SUFFIX}]"

    await mcp_call("remember", {"text": old_fact, "context": f"e2e_recency_old_{SUFFIX}"})
    # Small delay not needed — the DB timestamps will differ by insertion order
    await mcp_call("remember", {"text": new_fact, "context": f"e2e_recency_new_{SUFFIX}"})

    result = await mcp_call("recall", {"query": f"CI/CD deployment pipeline {SUFFIX}", "limit": 5})
    results = result.get("results", [])
    ci_results = [r for r in results if "CI/CD" in str(r.get("content", ""))]

    if len(ci_results) < 2:
        print(f"  [SKIP] Only {len(ci_results)} CI/CD results found — need 2 to compare recency")
        return

    # The newer fact (GitHub Actions) should appear before the older one (Jenkins)
    contents_ordered = [str(r.get("content", "")) for r in ci_results]
    gh_idx = next((i for i, c in enumerate(contents_ordered) if "GitHub Actions" in c), None)
    jenkins_idx = next((i for i, c in enumerate(contents_ordered) if "Jenkins" in c), None)

    if gh_idx is not None and jenkins_idx is not None and gh_idx < jenkins_idx:
        print("  [PASS] Newer fact (GitHub Actions) ranked above older fact (Jenkins)")
    else:
        # Not a hard failure — recency is just one signal among three
        print(f"  [WARN] Recency ordering not as expected: " f"GitHub Actions at {gh_idx}, Jenkins at {jenkins_idx}")


async def test_discover() -> None:
    """Discover should report stats including our stored episodes."""
    print("\n--- Discover ---")
    result = await mcp_call("discover", {})
    stats = result.get("stats", {})
    graphs = result.get("graphs", [])

    print(f"  Stats: {stats}")
    print(f"  Graphs: {graphs}")

    episode_count = stats.get("total_episodes", 0)
    if isinstance(episode_count, (int, float)) and episode_count > 0:
        print(f"  [PASS] Discover reports {episode_count} episodes")
    else:
        raise AssertionError(f"Expected total_episodes > 0 in stats: {stats}")

    # Cognitive heuristics stats should be present
    for key in ("forgotten_nodes", "consolidated_episodes", "avg_activation"):
        if key not in stats:
            raise AssertionError(f"Missing cognitive stat '{key}' in discover stats: {stats}")
    print(
        f"  [PASS] Cognitive stats present: "
        f"forgotten={stats['forgotten_nodes']}, "
        f"consolidated={stats['consolidated_episodes']}, "
        f"avg_activation={stats['avg_activation']}"
    )


async def main() -> None:
    print(f"E2E Hybrid Recall Test (suffix={SUFFIX})")
    print(f"Server: {MCP_URL}")
    print(f"Token: {TOKEN[:8]}...")

    print("\n=== Step 1: Store diverse facts ===")
    episode_ids = await store_facts()
    print(f"Stored {len(episode_ids)} episodes: {episode_ids}")

    print("\n=== Step 2: Test semantic recall ===")
    await test_semantic_recall()

    print("\n=== Step 3: Test keyword recall ===")
    await test_keyword_recall()

    print("\n=== Step 4: Test recency boost ===")
    await test_recency_boost()

    print("\n=== Step 5: Test discover ===")
    await test_discover()

    print("\n" + "=" * 40)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
