# Stage 1: Remove RLS from Shared Graphs

**Goal**: Remove Row-Level Security policies from shared graph schemas so any permissioned agent can update any node/edge, while retaining `owner_role` for provenance.
**Dependencies**: None

---

## Steps

### 1. Replace `_build_rls_block` with `_build_shared_provenance_block`

- File: `src/neocortex/schema_manager.py`
- Lines: 190-270 (`_build_rls_block` static method)
- Details:
  - Rename `_build_rls_block` → `_build_shared_provenance_block`
  - **Keep** the following from the existing method:
    - `neocortex_agent` base role creation (lines 194-200)
    - `GRANT USAGE ON SCHEMA` (line 201)
    - `GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE` for node/edge/episode/node_alias (lines 202-205)
    - `GRANT SELECT, INSERT ON TABLE` for node_type/edge_type (line 206)
    - `GRANT USAGE, SELECT ON ALL SEQUENCES` (line 207)
    - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS owner_role` for all three tables (lines 208-210)
    - Owner role indexes (lines 211-213)
  - **Remove** everything from line 214 onward:
    - `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` (lines 214-216)
    - `ALTER TABLE ... FORCE ROW LEVEL SECURITY` (lines 217-219)
    - All `DROP POLICY IF EXISTS` statements (lines 220-223, 237-240, 254-256)
    - All `CREATE POLICY` statements (lines 224-236, 241-253, 257-268)
  - Update the caller at line 187: `self._build_rls_block(schema_name)` → `self._build_shared_provenance_block(schema_name)`

### 2. Simplify `graph_scoped_connection` for shared graphs

- File: `src/neocortex/db/scoped.py`
- Lines: 37-58 (`graph_scoped_connection`)
- Details:
  - For shared graphs: **stop calling** `SET LOCAL ROLE`. The role-switching was
    only needed for RLS enforcement. Without RLS, shared graphs run as the
    connection pool owner (same as personal graphs).
  - Keep the `is_shared` check and `agent_id` validation — we still need to know
    it's a shared graph for provenance.
  - New behavior for shared graphs:
    ```python
    if is_shared:
        if agent_id is None:
            raise ValueError("agent_id is required for shared graph access")
        # No SET LOCAL ROLE — shared graphs don't use RLS.
        # owner_role is set by the application layer for provenance.
    ```
  - In the `if is_shared:` branch (lines 49-55), **remove the four lines** that
    call `oauth_sub_to_pg_role`, `_validate_role_name`, `ensure_pg_role`, and
    `SET LOCAL ROLE`. These functions are imported from `neocortex.db.roles` —
    **keep the imports** at the top of the file because `role_scoped_connection`
    (lines 17-25) still uses them.
  - **Note**: `role_scoped_connection` (lines 17-25) is unrelated (used for
    non-graph operations) — leave it unchanged.

### 3. Set `owner_role` explicitly in INSERT statements

- File: `src/neocortex/db/adapter.py`
- Details:
  - Currently, `owner_role DEFAULT current_user` in the column definition handles
    provenance via the SET LOCAL ROLE mechanism.
  - Without SET LOCAL ROLE, `current_user` will be the connection pool owner
    (e.g., `neocortex`), not the agent.
  - **Design decision**: Use the raw `agent_id` string as the `owner_role` value
    (e.g., `"alice"`, `"bob"`). With RLS removed, pg-role-formatted names
    (`ncx_agent_alice`) are no longer needed — raw agent_id is simpler and
    more readable for provenance. No new imports needed in adapter.py.
  - **Fix**: In `upsert_node` (line 735-748 INSERT branch), add `owner_role`
    explicitly when `target_schema` is set:
    ```sql
    INSERT INTO node (type_id, name, content, properties, embedding, source, importance, owner_role)
    VALUES ($1, $2, $3, $4::jsonb, $5::vector, $6, $7, $8)
    ```
    Where `$8` is `agent_id` (the raw string). The method signature already
    receives both `agent_id` and `target_schema` — use `target_schema is not None`
    to decide when to include `owner_role`.
  - Apply same pattern to these INSERT paths:
    - `upsert_edge`: find the `INSERT INTO edge` statement (lines ~962-974,
      uses `ON CONFLICT DO UPDATE`). Add `owner_role` to the INSERT column list
      when `target_schema` is set.
    - `store_episode`: find the `INSERT INTO episode` statement. Add `owner_role`
      when `target_schema` is set.
  - For non-shared writes (`target_schema is None`), `owner_role` can be omitted
    (personal graphs have no `owner_role` column — it's only added by the
    shared provenance block).

---

## Verification

- [ ] `uv run pytest tests/ -v -k "test_rls or test_shared"` — existing RLS tests pass or are updated
- [ ] `uv run pytest tests/ -v` — full test suite passes (no regressions)
- [ ] Read `schema_manager.py` and confirm: no `ENABLE ROW LEVEL SECURITY`, no `CREATE POLICY` in the shared block
- [ ] Read `scoped.py` and confirm: no `SET LOCAL ROLE` for shared graphs
- [ ] Grep the codebase for remaining references to `_build_rls_block` — should be zero

---

## Commit

`refactor(shared-graphs): remove RLS from shared schemas, retain owner_role for provenance`
