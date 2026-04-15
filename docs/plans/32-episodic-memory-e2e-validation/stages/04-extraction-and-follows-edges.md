# Stage 4: Extraction Pipeline + FOLLOWS Edges

**Goal**: Wait for extraction jobs to complete, then verify that the extraction pipeline created knowledge graph nodes from the ingested episodes and FOLLOWS edges between consecutive session episodes.
**Dependencies**: Stage 1 must be DONE (episodes must be ingested and extraction jobs queued)

---

## Steps

### 1. Implement extraction wait helpers

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Add `_get_max_job_id()` and `_wait_for_extraction()` that poll the `procrastinate_jobs` table (public schema, Procrastinate library) for extraction job completion. Follow the established pattern from `e2e_cognitive_recall_test.py`.

  **Important**: Extraction jobs are tracked in `procrastinate_jobs` (public schema), NOT in a per-graph `extraction_job` table. Status values are `'todo'`/`'doing'`/`'succeeded'`, NOT `'pending'`/`'completed'`/`'failed'`.

  The baseline ID pattern ensures we only wait for jobs from THIS test run, not stale jobs from previous runs.

```python
async def _get_max_job_id() -> int:
    """Return the current max extraction job ID (baseline for wait)."""
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        val = await conn.fetchval(
            "SELECT coalesce(max(id), 0) FROM procrastinate_jobs "
            "WHERE queue_name = 'extraction'"
        )
        return int(val)
    finally:
        await conn.close()


async def _wait_for_extraction(baseline_job_id: int) -> None:
    """Poll until extraction jobs created after baseline are done."""
    conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
    try:
        start = time.monotonic()
        while time.monotonic() - start < JOB_WAIT_TIMEOUT:
            row = await conn.fetchrow(
                """SELECT
                    count(*) FILTER (WHERE status = 'todo') AS pending,
                    count(*) FILTER (WHERE status = 'doing') AS running,
                    count(*) FILTER (WHERE status = 'succeeded') AS completed
                FROM procrastinate_jobs
                WHERE queue_name = 'extraction' AND id > $1""",
                baseline_job_id,
            )
            pending = int(row["pending"])
            running = int(row["running"])
            completed = int(row["completed"])
            elapsed = int(time.monotonic() - start)
            print(
                f"  [{elapsed:3d}s] pending={pending} running={running} "
                f"completed={completed}"
            )
            if pending == 0 and running == 0 and completed > 0:
                print(f"  Extraction complete: {completed} jobs finished")
                return
            await asyncio.sleep(JOB_POLL_INTERVAL)

        raise AssertionError(
            f"Extraction jobs did not complete within {JOB_WAIT_TIMEOUT}s"
        )
    finally:
        await conn.close()
```

### 2. Implement FOLLOWS edge verification

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Add `verify_follows_edges()` that checks the DB for FOLLOWS edges between session episodes:

```python
async def verify_follows_edges(session_id: str) -> int:
    """Verify FOLLOWS edges exist between consecutive session episodes."""
    config = PostgresConfig()
    conn = await asyncpg.connect(dsn=config.dsn)
    try:
        # Find episodes in this session
        ep_table = f"{_quote_identifier(AGENT_SCHEMA)}.episode"
        episodes = await conn.fetch(
            f"SELECT id, session_sequence FROM {ep_table} "
            f"WHERE session_id = $1 ORDER BY session_sequence",
            session_id,
        )

        if len(episodes) < 2:
            print(f"  Only {len(episodes)} episodes — no FOLLOWS edges expected")
            return 0

        # Check for FOLLOWS edges in the edge table
        edge_table = f"{_quote_identifier(AGENT_SCHEMA)}.edge"
        edge_type_table = f"{_quote_identifier(AGENT_SCHEMA)}.edge_type"

        follows_count = await conn.fetchval(
            f"SELECT count(*) FROM {edge_table} e "
            f"JOIN {edge_type_table} et ON e.type_id = et.id "
            f"WHERE et.name = 'FOLLOWS'",
        )

        print(f"  FOLLOWS edges in graph: {follows_count}")
        return follows_count
    finally:
        await conn.close()
```

### 3. Implement extracted nodes verification

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Add `verify_extracted_nodes()` that uses MCP discover tools to check that extraction produced knowledge graph nodes:

```python
async def verify_extracted_nodes() -> int:
    """Verify extraction created nodes in the personal graph."""
    result = await mcp_call("discover_graphs", {})
    graphs = result.get("graphs", [])

    personal_graph = next(
        (g for g in graphs if g["schema_name"] == AGENT_SCHEMA), None
    )
    if personal_graph is None:
        raise AssertionError(f"Personal graph {AGENT_SCHEMA} not found in discover_graphs")

    stats = personal_graph.get("stats", {})
    node_count = stats.get("total_nodes", 0)
    edge_count = stats.get("total_edges", 0)
    episode_count = stats.get("total_episodes", 0)

    print(f"  Graph stats: {node_count} nodes, {edge_count} edges, {episode_count} episodes")

    if node_count == 0:
        raise AssertionError("No nodes extracted — extraction pipeline may have failed")

    return node_count
```

### 4. Implement Stage 4 test function

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Combine the above into `test_extraction_and_follows()`:

```python
async def test_extraction_and_follows(baseline_job_id: int) -> None:
    """Stage 4: Verify extraction pipeline and FOLLOWS edges."""
    print("\n=== Stage 4: Extraction Pipeline + FOLLOWS Edges ===")

    # Wait for extraction to process our episodes.
    # We captured baseline_job_id in main() before ingestion started (Stage 1).
    # This ensures we only wait for jobs from THIS test run.
    print("\nWaiting for extraction jobs to complete...")
    await _wait_for_extraction(baseline_job_id)

    # Verify extraction produced graph nodes
    print("\nChecking extracted knowledge graph nodes...")
    node_count = await verify_extracted_nodes()
    print(f"  Extraction produced {node_count} nodes")

    # Verify FOLLOWS edges for Session A (4 turns → should have >= 1 FOLLOWS)
    print(f"\nChecking FOLLOWS edges for Session A...")
    follows_a = await verify_follows_edges(SESSION_A)

    print(f"\nChecking FOLLOWS edges for Session B...")
    follows_b = await verify_follows_edges(SESSION_B)

    total_follows = follows_a + follows_b
    if total_follows == 0:
        raise AssertionError(
            "No FOLLOWS edges found in either session. "
            "The extraction pipeline should create FOLLOWS edges between "
            "consecutive personal episodes in the same session."
        )

    print(f"\n  Total FOLLOWS edges: {total_follows}")
    print("\n=== Stage 4 PASSED ===")
```

### 5. Wire into main

- File: `scripts/e2e_episodic_memory_test.py`
- Details: In `main()`, capture the baseline job ID **before Stage 1 ingestion** and pass it to Stage 4:

```python
    # Capture baseline BEFORE ingestion so we only wait for this run's jobs
    baseline_job_id = await _get_max_job_id()
    print(f"Baseline extraction job ID: {baseline_job_id}")

    # Stage 1: Session ingestion
    await test_session_ingestion()

    # ... Stages 2-3 ...

    # Stage 4: Extraction + FOLLOWS edges
    await test_extraction_and_follows(baseline_job_id)
```

---

## Verification

- [ ] Test passes with extraction completing within 120s timeout
- [ ] `discover_graphs` reports non-zero nodes and edges in personal graph
- [ ] At least 1 FOLLOWS edge exists (connecting consecutive session episodes)
- [ ] Output shows extraction job progress and final graph stats

---

## Commit

`test(e2e): add extraction pipeline and FOLLOWS edge validation`
