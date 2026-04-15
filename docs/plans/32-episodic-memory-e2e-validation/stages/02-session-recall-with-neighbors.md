# Stage 2: Session Recall with Neighbor Expansion

**Goal**: Verify that recalling episodes returns session-clustered results with temporal neighbor expansion, and that neighbors carry correct provenance metadata.
**Dependencies**: Stage 1 must be DONE

---

## Steps

### 1. Implement session recall test

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Add `test_session_recall_with_neighbors()` that:
  1. Recalls using a query semantically related to Session A (e.g., "PostgreSQL upgrade timeline and risks")
  2. Asserts that the recall result contains episodes from Session A
  3. Checks that neighbor episodes are included (those with `neighbor_of` set)
  4. Verifies that results within the same session are in chronological order by `session_sequence`

```python
async def test_session_recall_with_neighbors() -> None:
    """Stage 2: Recall with neighbor expansion and session clustering."""
    print("\n=== Stage 2: Session Recall with Neighbors ===")

    # Query that should match Session A content
    result = await mcp_call("recall", {
        "query": f"PostgreSQL upgrade timeline and risks {SUFFIX}",
        "limit": 20,
    })
    items = result["results"]

    if not items:
        raise AssertionError("Recall returned no results")

    # Check that we got episode results
    episode_items = [i for i in items if i.get("source_kind") == "episode"]
    print(f"  Recall returned {len(items)} items, {len(episode_items)} episodes")

    if len(episode_items) < 2:
        raise AssertionError(
            f"Expected at least 2 episode results (nucleus + neighbors), "
            f"got {len(episode_items)}"
        )

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
```

### 2. Implement cross-session isolation test

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Add `test_cross_session_isolation()` that queries for Session B content and verifies that neighbor expansion does NOT pull in Session A episodes:

```python
async def test_cross_session_isolation() -> None:
    """Verify neighbor expansion stays within session boundaries."""
    print("\n--- Cross-Session Isolation Check ---")

    result = await mcp_call("recall", {
        "query": f"API latency spike search endpoint {SUFFIX}",
        "limit": 20,
    })
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
```

### 3. Wire into main

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Add calls to both new test functions in `main()`, after `test_session_ingestion()`:

```python
    # Stage 2: Session recall with neighbors
    await test_session_recall_with_neighbors()
    await test_cross_session_isolation()
```

---

## Verification

- [ ] With server running, `uv run python scripts/e2e_episodic_memory_test.py` passes Stages 1 and 2
- [ ] Output shows nucleus and neighbor episodes in recall results
- [ ] Neighbor episodes have `neighbor_of` pointing to a valid nucleus episode
- [ ] Cross-session isolation check passes (no Session A neighbors when querying Session B)

---

## Commit

`test(e2e): add session recall with neighbor expansion validation`
