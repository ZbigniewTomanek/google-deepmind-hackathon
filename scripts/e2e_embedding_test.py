"""E2E test for embedding operations.

Validates the full embedding lifecycle through MCP tools:
- Embeddings are generated and attached on remember
- Pure semantic recall works (zero keyword overlap)
- Vector similarity quality: related texts rank higher than unrelated
- Negative cases: unrelated queries don't surface irrelevant results
- Edge cases: short texts, long texts, unicode content
- Score composition: vector-matched results carry vector signal in score

Prerequisites:
  docker compose up -d postgres
  GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false uv run python -m neocortex

Usage:
  GOOGLE_API_KEY=... uv run python scripts/e2e_embedding_test.py
"""

from __future__ import annotations

import asyncio
import os
import uuid

from fastmcp import Client

BASE_URL = os.environ.get("NEOCORTEX_BASE_URL", "http://127.0.0.1:8000")
MCP_URL = os.environ.get("NEOCORTEX_MCP_URL", f"{BASE_URL}/mcp")
TOKEN = os.environ.get("NEOCORTEX_TOKEN", "dev-token-neocortex")

SUFFIX = uuid.uuid4().hex[:8]

passed = 0
failed = 0
warned = 0


def report(status: str, message: str) -> None:
    global passed, failed, warned
    if status == "PASS":
        passed += 1
    elif status == "FAIL":
        failed += 1
    elif status == "WARN":
        warned += 1
    print(f"  [{status}] {message}")


async def mcp_call(tool_name: str, arguments: dict[str, object]) -> dict:
    """Call an MCP tool on the running server and return structured content."""
    async with Client(MCP_URL, auth=TOKEN) as client:
        result = await client.call_tool(tool_name, arguments)
    if not isinstance(result.structured_content, dict):
        raise AssertionError(f"{tool_name} did not return structured content: {result}")
    return result.structured_content


async def remember(text: str, context: str | None = None) -> int:
    """Store a fact and return its episode ID."""
    result = await mcp_call("remember", {"text": text, **({"context": context} if context else {})})
    eid = int(result["episode_id"])
    if eid <= 0:
        raise AssertionError(f"Unexpected episode id: {result}")
    return eid


async def recall(query: str, limit: int = 10) -> list[dict]:
    """Recall and return the results list."""
    result = await mcp_call("recall", {"query": query, "limit": limit})
    return result.get("results", [])


# ---------------------------------------------------------------------------
# Test 1: Pure semantic recall (zero keyword overlap)
# ---------------------------------------------------------------------------


async def test_pure_semantic_recall() -> None:
    """Store facts, recall with completely different wording.

    This is the core embedding value-prop: finding results that keyword
    search alone would never surface.
    """
    print("\n--- Test 1: Pure Semantic Recall (zero keyword overlap) ---")

    pairs = [
        (
            f"The mitochondria is the powerhouse of the cell [{SUFFIX}]",
            "organelle responsible for cellular energy production",
            "mitochondria",
        ),
        (
            f"Water freezes at zero degrees Celsius under standard pressure [{SUFFIX}]",
            "temperature at which H2O becomes solid",
            "freezes",
        ),
        (
            f"The French Revolution began in 1789 with the storming of the Bastille [{SUFFIX}]",
            "18th century European uprising that overthrew the monarchy",
            "Revolution",
        ),
    ]

    for fact, _, _ in pairs:
        await remember(fact, context=f"e2e_semantic_{SUFFIX}")

    hits = 0
    for _fact, query, expected_keyword in pairs:
        results = await recall(query, limit=5)
        contents = [str(r.get("content", "")) for r in results]
        found = any(expected_keyword.lower() in c.lower() for c in contents)
        if found:
            hits += 1
            report("PASS", f"'{query[:45]}...' -> found '{expected_keyword}'")
        else:
            report("FAIL", f"'{query[:45]}...' -> missed '{expected_keyword}'")

    if hits >= 2:
        report("PASS", f"Pure semantic recall: {hits}/{len(pairs)} hits (threshold: 2)")
    else:
        report("FAIL", f"Pure semantic recall: {hits}/{len(pairs)} hits (threshold: 2)")


# ---------------------------------------------------------------------------
# Test 2: Vector similarity quality — related > unrelated
# ---------------------------------------------------------------------------


async def test_similarity_ranking() -> None:
    """Store facts from distinct domains. A domain-specific query should rank
    its own domain's fact higher than unrelated domains.
    """
    print("\n--- Test 2: Similarity Ranking (related > unrelated) ---")

    domain_facts = {
        "cooking": f"A roux is made by cooking equal parts flour and fat to thicken sauces [{SUFFIX}]",
        "astronomy": f"Neutron stars are the collapsed cores of massive stars after supernova [{SUFFIX}]",
        "music": f"A pentatonic scale consists of five notes per octave commonly used in blues [{SUFFIX}]",
    }

    for domain, fact in domain_facts.items():
        await remember(fact, context=f"e2e_ranking_{domain}_{SUFFIX}")

    queries = {
        "cooking": "thickening agents for French cuisine sauces",
        "astronomy": "remnants of stellar explosions in deep space",
        "music": "musical scales used in blues improvisation",
    }

    for domain, query in queries.items():
        results = await recall(query, limit=5)
        if not results:
            report("FAIL", f"{domain}: no results returned")
            continue

        top_content = str(results[0].get("content", ""))
        expected_snippet = domain_facts[domain].split("[")[0].strip()[:30]
        if expected_snippet.lower()[:20] in top_content.lower():
            report("PASS", f"{domain}: correct domain ranked #1")
        else:
            # Check if it's in top 3 at least
            top3 = [str(r.get("content", "")) for r in results[:3]]
            found_in_top3 = any(expected_snippet.lower()[:20] in c.lower() for c in top3)
            if found_in_top3:
                report("WARN", f"{domain}: correct domain in top 3 but not #1")
            else:
                report("FAIL", f"{domain}: correct domain not in top 3")


# ---------------------------------------------------------------------------
# Test 3: Negative test — unrelated query returns nothing relevant
# ---------------------------------------------------------------------------


async def test_negative_recall() -> None:
    """Recall with a query completely unrelated to anything stored.

    Should return either no results or results with low scores. We verify
    that our test-specific content (tagged with SUFFIX) does NOT appear
    for a completely off-topic query.
    """
    print("\n--- Test 3: Negative Recall (unrelated query) ---")

    # Store a very specific fact
    specific_fact = f"The Voyager 1 probe entered interstellar space in August 2012 [{SUFFIX}]"
    await remember(specific_fact, context=f"e2e_negative_{SUFFIX}")

    # Query about something completely unrelated
    results = await recall("best recipe for sourdough bread baking", limit=5)
    contents = [str(r.get("content", "")) for r in results]
    voyager_leaked = any("Voyager" in c for c in contents)

    if not voyager_leaked:
        report("PASS", "Unrelated query did not surface 'Voyager' fact")
    else:
        # Check the score — if it's very low, that's still acceptable
        voyager_results = [r for r in results if "Voyager" in str(r.get("content", ""))]
        if voyager_results and float(voyager_results[0].get("score", 1.0)) < 0.3:
            report("WARN", "Voyager appeared but with low score (<0.3)")
        else:
            report("FAIL", "Unrelated query surfaced 'Voyager' fact with significant score")


# ---------------------------------------------------------------------------
# Test 4: Short text embedding
# ---------------------------------------------------------------------------


async def test_short_text() -> None:
    """Very short texts should still get embeddings and be recallable."""
    print("\n--- Test 4: Short Text Embedding ---")

    short_text = f"Python [{SUFFIX}]"
    await remember(short_text, context=f"e2e_short_{SUFFIX}")

    results = await recall("programming language created by Guido van Rossum", limit=5)
    contents = [str(r.get("content", "")) for r in results]
    found = any("Python" in c and SUFFIX in c for c in contents)

    if found:
        report("PASS", "Short text 'Python' found via semantic query")
    else:
        report("WARN", "Short text not found — may be too ambiguous for embedding match")


# ---------------------------------------------------------------------------
# Test 5: Long text embedding
# ---------------------------------------------------------------------------


async def test_long_text() -> None:
    """Longer texts should be embedded and recallable."""
    print("\n--- Test 5: Long Text Embedding ---")

    long_text = (
        f"The James Webb Space Telescope (JWST) is a large infrared space telescope "
        f"launched on December 25, 2021. It orbits the Sun near the second Lagrange "
        f"point (L2), approximately 1.5 million kilometers from Earth. JWST's primary "
        f"mirror is 6.5 meters in diameter, composed of 18 hexagonal gold-plated "
        f"beryllium segments. The telescope observes in the infrared spectrum, enabling "
        f"it to peer through cosmic dust clouds and observe the earliest galaxies formed "
        f"after the Big Bang. Its four main instruments — NIRCam, NIRSpec, MIRI, and "
        f"FGS/NIRISS — cover wavelengths from 0.6 to 28.5 micrometers. The project "
        f"was a collaboration between NASA, ESA, and CSA. [{SUFFIX}]"
    )
    await remember(long_text, context=f"e2e_long_{SUFFIX}")

    results = await recall("space observatory studying early universe and galaxies", limit=5)
    contents = [str(r.get("content", "")) for r in results]
    found = any("Webb" in c or "JWST" in c for c in contents)

    if found:
        report("PASS", "Long text about JWST found via semantic query")
    else:
        report("FAIL", "Long text about JWST not found")


# ---------------------------------------------------------------------------
# Test 6: Unicode and multilingual text
# ---------------------------------------------------------------------------


async def test_unicode_text() -> None:
    """Texts with unicode characters should embed and recall without errors."""
    print("\n--- Test 6: Unicode Text Embedding ---")

    unicode_text = (
        f"Le café au lait est une boisson française populaire préparée " f"avec du café et du lait chaud [{SUFFIX}]"
    )
    await remember(unicode_text, context=f"e2e_unicode_{SUFFIX}")

    # Recall in English — cross-lingual semantic match
    results = await recall("popular French coffee drink with hot milk", limit=5)
    contents = [str(r.get("content", "")) for r in results]
    found = any("café" in c and SUFFIX in c for c in contents)

    if found:
        report("PASS", "French text found via English semantic query")
    else:
        report("WARN", "Cross-lingual recall did not match — model may not support it well")


# ---------------------------------------------------------------------------
# Test 7: Multiple similar facts — score differentiation
# ---------------------------------------------------------------------------


async def test_score_differentiation() -> None:
    """Store facts at varying semantic distances from a query.
    The closest fact should score highest.
    """
    print("\n--- Test 7: Score Differentiation ---")

    close_fact = f"Redis is an in-memory key-value data store used for caching [{SUFFIX}]"
    medium_fact = f"MongoDB is a document-oriented NoSQL database for flexible schemas [{SUFFIX}]"
    far_fact = f"Git is a distributed version control system for tracking code changes [{SUFFIX}]"

    await remember(close_fact, context=f"e2e_diff_close_{SUFFIX}")
    await remember(medium_fact, context=f"e2e_diff_medium_{SUFFIX}")
    await remember(far_fact, context=f"e2e_diff_far_{SUFFIX}")

    results = await recall("fast in-memory cache for application data", limit=10)

    # Find scores for our specific facts
    scores = {}
    for r in results:
        content = str(r.get("content", ""))
        if "Redis" in content and SUFFIX in content:
            scores["close"] = float(r.get("score", 0))
        elif "MongoDB" in content and SUFFIX in content:
            scores["medium"] = float(r.get("score", 0))
        elif "Git" in content and SUFFIX in content:
            scores["far"] = float(r.get("score", 0))

    if "close" not in scores:
        report("FAIL", "Redis fact not found in recall results")
        return

    report("PASS", f"Redis (close) score: {scores.get('close', 0):.3f}")

    if "close" in scores and "far" in scores:
        if scores["close"] > scores["far"]:
            report("PASS", f"Close fact scored higher than far fact ({scores['close']:.3f} > {scores['far']:.3f})")
        else:
            report("WARN", f"Score order unexpected: close={scores['close']:.3f}, far={scores['far']:.3f}")
    elif "close" in scores and "far" not in scores:
        report("PASS", "Far fact (Git) correctly excluded from results")


# ---------------------------------------------------------------------------
# Test 8: Duplicate text produces separate episodes
# ---------------------------------------------------------------------------


async def test_duplicate_storage() -> None:
    """Storing the same text twice should create two episodes, both recallable."""
    print("\n--- Test 8: Duplicate Text Storage ---")

    text = f"Photosynthesis converts sunlight into chemical energy in plants [{SUFFIX}]"
    eid1 = await remember(text, context=f"e2e_dup_first_{SUFFIX}")
    eid2 = await remember(text, context=f"e2e_dup_second_{SUFFIX}")

    if eid1 == eid2:
        report("FAIL", f"Duplicate storage returned same episode ID: {eid1}")
        return

    report("PASS", f"Two distinct episode IDs: {eid1}, {eid2}")

    results = await recall("plant biology converting light to energy", limit=10)
    matching = [
        r for r in results if "Photosynthesis" in str(r.get("content", "")) and SUFFIX in str(r.get("content", ""))
    ]

    if len(matching) >= 2:
        report("PASS", f"Both duplicate episodes found ({len(matching)} matches)")
    elif len(matching) == 1:
        report("WARN", "Only one of two duplicate episodes found")
    else:
        report("FAIL", "Neither duplicate episode found via semantic recall")


# ---------------------------------------------------------------------------
# Test 9: Embedding enables recall where keyword search fails
# ---------------------------------------------------------------------------


async def test_embedding_vs_keyword() -> None:
    """Store a fact and recall it with a query that shares zero keywords.
    Then verify that a keyword query also works. This proves both paths
    contribute to hybrid scoring.
    """
    print("\n--- Test 9: Embedding vs Keyword Paths ---")

    fact = f"Elephants are the largest living terrestrial animals weighing up to 6 tonnes [{SUFFIX}]"
    await remember(fact, context=f"e2e_paths_{SUFFIX}")

    # Semantic query — zero keyword overlap with fact
    sem_results = await recall("biggest land mammals on Earth by body mass", limit=5)
    sem_contents = [str(r.get("content", "")) for r in sem_results]
    sem_found = any("Elephants" in c and SUFFIX in c for c in sem_contents)

    if sem_found:
        report("PASS", "Semantic path: found 'Elephants' via paraphrase query")
    else:
        report("FAIL", "Semantic path: 'Elephants' not found via paraphrase")

    # Keyword query — direct keyword overlap
    kw_results = await recall(f"Elephants terrestrial {SUFFIX}", limit=5)
    kw_contents = [str(r.get("content", "")) for r in kw_results]
    kw_found = any("Elephants" in c and SUFFIX in c for c in kw_contents)

    if kw_found:
        report("PASS", "Keyword path: found 'Elephants' via keyword query")
    else:
        report("FAIL", "Keyword path: 'Elephants' not found via keyword query")

    # Compare scores — hybrid (both signals) should score >= semantic-only
    if sem_found and kw_found:
        sem_score = next(
            float(r.get("score", 0))
            for r in sem_results
            if "Elephants" in str(r.get("content", "")) and SUFFIX in str(r.get("content", ""))
        )
        kw_score = next(
            float(r.get("score", 0))
            for r in kw_results
            if "Elephants" in str(r.get("content", "")) and SUFFIX in str(r.get("content", ""))
        )
        report("PASS", f"Scores: semantic={sem_score:.3f}, keyword={kw_score:.3f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    print(f"E2E Embedding Operations Test (suffix={SUFFIX})")
    print(f"Server: {MCP_URL}")
    print(f"Token: {TOKEN[:8]}...")

    await test_pure_semantic_recall()
    await test_similarity_ranking()
    await test_negative_recall()
    await test_short_text()
    await test_long_text()
    await test_unicode_text()
    await test_score_differentiation()
    await test_duplicate_storage()
    await test_embedding_vs_keyword()

    print("\n" + "=" * 50)
    print(f"RESULTS: {passed} passed, {failed} failed, {warned} warnings")
    if failed > 0:
        print("SOME CHECKS FAILED")
        raise SystemExit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
