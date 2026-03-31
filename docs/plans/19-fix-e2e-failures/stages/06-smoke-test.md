# Stage 6: Integration Smoke Test

**Goal**: Verify all 3 fixes work end-to-end by storing targeted episodes via MCP tools and checking graph state.
**Dependencies**: Stages 1-5 must be DONE. MCP server must be running with real DB.
**Status**: IN_PROGRESS -- blocked by 3 additional bugs found during smoke test (all fixed, needs re-run)

---

## Background

This stage is executed by Claude with MCP access, similar to Plan 18.5. It stores 3 specific episodes and validates that:
1. Domain routing populates shared graphs (M5 fix)
2. Correction episodes create SUPERSEDES/CORRECTS edges (M4 fix)
3. No corrupted type names appear (M6 fix)

---

## Bugs Found During Smoke Test (2026-03-31)

Three additional bugs were discovered and fixed during this stage before the
smoke test episodes could complete successfully:

### Bug A: `source_schema` sentinel mismatch (domain routing)

**Symptom**: Shared-graph extraction jobs logged `episode_not_found` despite
the episode existing in the personal graph.

**Root cause**: `DomainRouter._enqueue_extraction()` passes `source_schema=None`
meaning "read from personal graph". But `extract_episode` task code
(`tasks.py:61`) skips passing `source_schema` when it's `None` (can't
distinguish from "not provided"). The pipeline then defaults to reading from
`target_schema` (the shared schema), which has no episodes.

**Fix**: Use string sentinel `"__personal__"` in the router → task boundary.
- `router.py:245`: `source_schema="__personal__"` instead of `None`
- `tasks.py:61-65`: convert `"__personal__"` back to `None` before calling pipeline

**Files changed**: `src/neocortex/domains/router.py`, `src/neocortex/jobs/tasks.py`

### Bug B: Connection pool deadlock (shared-graph extraction)

**Symptom**: After fixing Bug A, shared-graph extraction started but hung
indefinitely. All 10 PG connections stuck in `idle in transaction` on
`SELECT is_shared FROM graph_registry`.

**Root cause**: `graph_scoped_connection()` acquires a connection, then calls
`ensure_pg_role(pool, ...)` which acquires **another** connection from the same
pool. The librarian agent runs tool calls concurrently (pydantic_ai). With 10
concurrent tool calls each holding a connection + needing another for
`ensure_pg_role`, the pool (max=10) deadlocks.

**Fix**: Changed `ensure_pg_role()` to accept either a Pool or Connection.
`graph_scoped_connection` now passes the already-acquired connection instead
of the pool, eliminating nested pool acquisition.

**Files changed**: `src/neocortex/db/roles.py`, `src/neocortex/db/scoped.py`

### Bug C: Missing `node_alias` table permissions (shared schemas)

**Symptom**: After fixing Bugs A+B, shared-graph extraction failed with
`InsufficientPrivilegeError: permission denied for table node_alias`.

**Root cause**: `SchemaManager._build_rls_block()` grants
SELECT/INSERT/UPDATE/DELETE on `node`, `edge`, `episode` but omits
`node_alias` (added in migration 009). The `neocortex_agent` role can't
read/write aliases in shared schemas.

**Fix**: Added `{schema_name}.node_alias` to the GRANT statement in
`_build_rls_block()`.

**Files changed**: `src/neocortex/schema_manager.py`

**Manual DB fix**: For already-provisioned shared schemas, run:
```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ncx_shared__technical_knowledge.node_alias TO neocortex_agent;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE ncx_shared__domain_knowledge.node_alias TO neocortex_agent;
-- Repeat for any other shared schemas (ncx_shared__user_profile, ncx_shared__work_context)
```

---

## Steps

### Pre-flight

1. Start the MCP server and ingestion service:
   ```bash
   ./scripts/launch.sh
   ```

2. Verify MCP tools are functional:
   - Call `discover_graphs` -- should list personal and shared graphs
   - Call `discover_domains` -- should list 4 seed domains

### Episode 1: Technical knowledge (domain routing test)

3. Store via `remember`:
   ```
   text: "The DataWalk entity resolution system uses a dual-projection Vertica architecture
   with blocking-based candidate generation. The system implements Fellegi-Sunter probabilistic
   matching with information content weighting. Key components: BlockingService (Python),
   MatchingEngine (SQL/Vertica), and a React dashboard for review workflows."
   importance: 0.7
   ```

4. Wait for extraction to complete. Poll by calling `discover_ontology` on the target
   graph every 30 seconds until new node types appear (or 5 minutes elapse). Then verify:
   - `discover_graphs` -- shared graphs should have non-zero node counts
   - Check `ncx_shared__technical_knowledge` specifically via `discover_ontology`
   - **Pass criteria**: At least 1 shared graph has nodes from this episode

### Episode 2: Correction (temporal edge test)

5. Store a base fact via `remember`:
   ```
   text: "The Metaphone3 phonetic encoding uses a 4-character code length for all languages.
   This was decided in sprint 12 based on benchmark results showing 87% accuracy on the
   English test corpus."
   importance: 0.6
   ```

6. Wait for extraction to complete (poll `discover_ontology` for new types, up to 5 min).

7. Store a correction via `remember`:
   ```
   text: "CORRECTION: The Metaphone3 strategy has been updated. Instead of using 4-char
   codes for all languages, the team switched to a hybrid approach: 8-character codes
   for Latin-script languages and 4-character codes for non-Latin scripts. This replaced
   the previous uniform 4-char strategy after discovering precision issues with longer names."
   importance: 0.8
   ```

8. Wait for extraction to complete (poll `discover_ontology` for new edge instances, up to 5 min). Then verify:
   - `discover_ontology` -- check for SUPERSEDES or CORRECTS edge types with instances
   - `inspect_node` on "Metaphone3" or similar -- check for temporal edges in neighborhood
   - **Pass criteria**: At least 1 SUPERSEDES or CORRECTS edge exists connecting the correction to the original

### Episode 3: Clean type names (type corruption test)

9. Store via `remember`:
   ```
   text: "The normalization pipeline preprocesses input records through multiple stages:
   phone number parsing (ParsePhoneNumber UDX), human name parsing (ParseHumanName UDX),
   address standardization, and Unicode normalization. Each stage produces a normalized
   field that feeds into the composite fingerprint computation."
   importance: 0.5
   ```

10. Wait for extraction to complete (poll `discover_ontology` for new types, up to 5 min). Then verify:
    - `discover_ontology` -- scan ALL node type names
    - Check every type against: starts with uppercase, <= 60 chars, no embedded IDs
    - **Pass criteria**: Zero corrupted type names

### Cleanup

11. Record all results in this stage file.
12. Stop services: `./scripts/launch.sh --stop`

---

## Re-run Instructions (for next agent)

All 3 bugs (A, B, C) are fixed in the source code. To re-run the smoke test:

1. **Reset DB** (recommended): `docker compose down -v && docker compose up -d postgres`
   then `./scripts/launch.sh`. This ensures clean shared schemas with correct grants.
   Alternatively, apply the manual GRANT statements above to all 4 shared schemas.

2. **Reconnect MCP**: `/mcp` to reconnect to the restarted server.

3. **Run Episodes 1-3** as described above. Each episode's extraction takes
   ~60-90 seconds (personal graph) + ~60-120 seconds (shared graph via domain routing).
   The shared graph extraction involves 3 LLM calls (ontology/extractor/librarian)
   per routed domain, so allow up to 3 minutes per episode.

4. **Key things to watch**:
   - `tail -f log/mcp.log` for `curation_complete` and `extract_episode_completed`
   - No `episode_not_found` warnings (Bug A fixed)
   - No `idle in transaction` connection pileup (Bug B fixed)
   - No `InsufficientPrivilegeError` (Bug C fixed)

---

## Verification

| Check | Pass Criteria | Status |
|-------|--------------|--------|
| Domain routing | >= 1 shared graph has nodes after Episode 1 | PENDING |
| Temporal edges | >= 1 SUPERSEDES or CORRECTS edge after Episode 2 (correction) | PENDING |
| Type names | 0 corrupted types across all extractions | PENDING |
| Server stability | No crashes, no unhandled exceptions in logs | PENDING |

---

## Commit

```
docs(plan-19): record integration smoke test results

Stage 6: MCP-driven smoke test verified domain routing, temporal
correction edges, and type name integrity end-to-end.
```
