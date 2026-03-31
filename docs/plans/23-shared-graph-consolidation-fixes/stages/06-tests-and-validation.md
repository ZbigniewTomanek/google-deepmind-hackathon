# Stage 6: Tests & Validation

**Goal**: Add unit tests covering all changes from Stages 1-5 and document E2E re-validation.
**Dependencies**: Stages 1-5

---

## Steps

### 1. Update existing RLS tests

- File: `tests/mcp/test_rls.py`
- Details:
  - This file tests RLS policy enforcement on shared graphs.
  - After Stage 1, RLS is removed from shared graphs. Update tests to verify:
    - **Shared graphs**: No RLS enforcement. Agent B CAN update Agent A's nodes.
    - **Provenance**: `owner_role` column still populated correctly for audit.
  - Remove or update assertions that expect UPDATE to fail across agents.
  - Add a positive test: Agent A creates a node, Agent B updates it — succeeds.

### 2. Add cross-agent upsert test

- File: `tests/unit/test_shared_graph_consolidation.py` (new)
- Details:
  - Test using `InMemoryRepository` (no Docker needed).
  - Follow existing test patterns: `@pytest.mark.asyncio`, `InMemoryRepository`
    from `neocortex.db.mock`, `MCPSettings` from `neocortex.mcp_settings`,
    `AsyncMock`/`MagicMock` from `unittest.mock`.
  - Scenarios:
    - **Test cross_agent_upsert**: Agent A upserts node "Python" with content
      "A programming language". Agent B upserts same node "Python" with content
      "A versatile programming language used in ML". Verify: single node exists,
      content reflects B's update (the librarian is expected to merge).
    - **Test update_zero_rows_fallback**: Mock the UPDATE to return None.
      Verify: fallback INSERT creates a new node, no RuntimeError raised.
  - **Note**: `owner_role` provenance cannot be tested with `InMemoryRepository`
    because the `Node` model has no `owner_role` field and the mock doesn't
    track it. Owner role provenance is verified via the RLS integration tests
    in Step 1 (which require PostgreSQL).

### 3. Add tool_calls_limit configuration test

- File: `tests/unit/test_shared_graph_consolidation.py` (same file — no dedicated
  `test_settings.py` exists; settings are tested inline across test files)
- Details:
  - Verify `extraction_tool_calls_limit` defaults to 150:
    ```python
    def test_extraction_tool_calls_limit_default():
        settings = MCPSettings(mock_db=True)
        assert settings.extraction_tool_calls_limit == 150
    ```
  - Verify it can be overridden via environment variable
    `NEOCORTEX_EXTRACTION_TOOL_CALLS_LIMIT=200`.

### 4. Add recall type resolution test

- File: `tests/unit/test_shared_graph_consolidation.py` (same file)
- Details:
  - Create a node with a known type. Recall the node. Verify `item_type` is the
    type name, not "Unknown".
  - Edge case: If possible with InMemoryRepository, create a node whose type_id
    doesn't match any type entry. Verify recall returns gracefully.

### 5. Update existing extraction tests if needed

- File: `tests/unit/test_extraction_target_schema.py`
- Details:
  - If any tests assert RLS behavior during extraction, update them.
  - Verify that extraction to shared graphs (via `target_schema`) works
    without role switching.

### 6. Document E2E re-validation procedure

- File: `docs/plans/23-shared-graph-consolidation-fixes/resources/e2e-revalidation.md`
- Details:
  - Write a short guide for re-running Plan 22 metrics:
    1. Start fresh: `./scripts/manage.sh start --fresh`
    2. Create shared graph + permissions (link to Plan 22 Stage 1)
    3. Ingest Alice's episodes (link to Plan 22 Stage 2)
    4. Ingest Bob's episodes (link to Plan 22 Stage 3)
    5. Check M3: Query shared nodes for cross-agent content
    6. Check M4: Ingest correction episodes, verify supersession
    7. Check M7: Recall and verify no "Unknown" types
  - Expected outcomes after fixes:
    - M3 ≥ 3/5 — content merging works (RLS no longer blocks)
    - M4 ≥ 2/3 — corrections propagate
    - M7 = 0 "Unknown" types

---

## Verification

- [ ] `uv run pytest tests/ -v` — full suite passes with 0 failures
- [ ] `uv run pytest tests/mcp/test_rls.py -v` — RLS tests updated and passing
- [ ] `uv run pytest tests/unit/test_shared_graph_consolidation.py -v` — new tests pass
- [ ] New test file exists and covers: cross-agent upsert, fallback, provenance, type resolution
- [ ] `resources/e2e-revalidation.md` exists

---

## Commit

`test(shared-graphs): add cross-agent consolidation tests, update RLS tests, document E2E revalidation`
