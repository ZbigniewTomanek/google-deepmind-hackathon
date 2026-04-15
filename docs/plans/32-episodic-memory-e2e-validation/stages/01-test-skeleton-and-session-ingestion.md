# Stage 1: Test Skeleton + Session Ingestion

**Goal**: Create the E2E test script with shared infrastructure and ingest a realistic multi-turn conversation as session-tagged episodes via the HTTP ingestion API.
**Dependencies**: None

---

## Steps

### 1. Create test script skeleton

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Create a new E2E test script following the patterns in `scripts/e2e_cognitive_recall_test.py` and `scripts/e2e_hybrid_recall_test.py`.

Include these shared components:
  - Module docstring with prerequisites and usage (same format as existing E2E tests)
  - Imports: `asyncio`, `os`, `uuid`, `json`, `time`, `asyncpg`, `httpx`, `fastmcp.Client`, `neocortex.config.PostgresConfig`
  - URL constants: `BASE_URL`, `INGESTION_URL`, `MCP_URL` from env with defaults `127.0.0.1:8000/8001`
  - Token constants: `ALICE_TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")`
  - `AGENT_SCHEMA = "ncx_alice__personal"`
  - `SUFFIX = uuid.uuid4().hex[:8]` for test isolation
  - `JOB_WAIT_TIMEOUT = 120`, `JOB_POLL_INTERVAL = 3`
  - `mcp_call(tool_name, arguments)` helper (same as `e2e_cognitive_recall_test.py`)
  - `_headers(token)` and `_post(path, token, **kwargs)` helpers for HTTP calls to ingestion API.
    **Important**: `_post` must use `INGESTION_URL` (port 8001) as `base_url`, NOT `BASE_URL` (port 8000):
    ```python
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def _post(path: str, token: str, **kwargs) -> dict:
        async with httpx.AsyncClient(base_url=INGESTION_URL, timeout=10.0) as client:
            resp = await client.post(path, headers=_headers(token), **kwargs)
        resp.raise_for_status()
        return resp.json()
    ```
  - `_quote_identifier(identifier)` helper for SQL identifiers
  - Session constants:
    ```python
    SESSION_A = f"morning-standup-{SUFFIX}"
    SESSION_B = f"afternoon-debug-{SUFFIX}"
    ```

### 2. Define realistic conversation data

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Define two conversation sessions (Session A: 4 turns, Session B: 3 turns) with realistic content that an AI agent would store. Content should be thematically connected within each session but distinct between sessions, and include enough semantic overlap to test cross-session recall.

```python
# Session A: morning standup discussion about database migration (4 turns)
SESSION_A_TURNS = [
    f"We discussed the PostgreSQL 16 upgrade timeline in standup today. The DBA team wants to do it during the maintenance window on May 3rd. [{SUFFIX}]",
    f"The main risk with the PG16 upgrade is the breaking change in jsonb_path_query behavior. We need to audit all JSONB queries in the analytics pipeline first. [{SUFFIX}]",
    f"Alice volunteered to run the JSONB query audit. She'll check all stored procedures and the three most active Grafana dashboards. [{SUFFIX}]",
    f"The team agreed to freeze schema migrations one week before the PG16 upgrade. No DDL changes after April 26th. [{SUFFIX}]",
]

# Session B: afternoon debugging session about API latency (3 turns)
SESSION_B_TURNS = [
    f"Investigating p99 latency spike in the /api/search endpoint. Response times jumped from 120ms to 800ms after yesterday's deploy. [{SUFFIX}]",
    f"Root cause found: the new full-text search query is doing a sequential scan on the documents table instead of using the GIN index. The query planner chose wrong because ANALYZE hasn't run since the bulk import. [{SUFFIX}]",
    f"Fix deployed: ran ANALYZE on documents table and added a query hint to force GIN index usage. p99 back to 130ms. Will add ANALYZE to the post-import automation. [{SUFFIX}]",
]
```

### 3. Implement session ingestion function

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Write `ingest_session_episodes()` that sends each turn as a `POST /ingest/text` request with the same `session_id`. Returns the list of created episode IDs.

```python
async def ingest_session_episodes(
    session_id: str, turns: list[str], token: str = ALICE_TOKEN
) -> None:
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
```

### 4. Implement DB verification function

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Write `verify_session_in_db()` that connects to PostgreSQL directly and asserts:
  - All episodes exist in `ncx_alice__personal.episode`
  - Episodes have the correct `session_id`
  - `session_sequence` values are sequential (0, 1, 2, ...)
  - Episodes are ordered by `session_sequence` within the session

```python
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
            raise AssertionError(
                f"Expected {expected_count} episodes for session {session_id}, "
                f"got {len(rows)}"
            )
        for i, row in enumerate(rows):
            if row["session_sequence"] != i:
                raise AssertionError(
                    f"Episode {row['id']} has session_sequence={row['session_sequence']}, "
                    f"expected {i}"
                )
        print(f"  DB check passed: {expected_count} episodes with correct sequences")
    finally:
        await conn.close()
```

### 5. Implement test_session_ingestion entry point

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Write `test_session_ingestion()` that calls the ingestion and verification functions:

```python
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
```

### 6. Add main entry point

- File: `scripts/e2e_episodic_memory_test.py`
- Details: Add a `main()` function that runs all test stages sequentially, with later stages added in subsequent plan stages:

```python
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

    print("\n=== ALL TESTS PASSED ===")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Verification

- [ ] Script runs without syntax errors: `uv run python -c "import ast; ast.parse(open('scripts/e2e_episodic_memory_test.py').read())"`
- [ ] With server running (`./scripts/run_e2e.sh`), the test completes: `uv run python scripts/e2e_episodic_memory_test.py`
- [ ] Output shows 7 episodes stored (4 for session A, 3 for session B)
- [ ] DB verification passes: both sessions have correct `session_sequence` values (0,1,2,3 and 0,1,2)

---

## Commit

`test(e2e): add episodic memory test skeleton with session ingestion`
