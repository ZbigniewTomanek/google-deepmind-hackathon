# Stage 7: Report & Verdict

**Goal**: Compile all metrics from Stages 4-6, compare to targets, produce final verdict.
**Dependencies**: Stages 4, 5, 6 DONE

---

## Steps

### 7.1 Final Graph State Snapshot

```bash
# Total counts
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT
    (SELECT count(*) FROM ncx_shared__project_titan.node WHERE forgotten = false) AS nodes,
    (SELECT count(*) FROM ncx_shared__project_titan.edge) AS edges,
    (SELECT count(*) FROM ncx_shared__project_titan.episode) AS episodes,
    (SELECT count(DISTINCT type) FROM ncx_shared__project_titan.node WHERE forgotten = false) AS node_types,
    (SELECT count(DISTINCT type) FROM ncx_shared__project_titan.edge) AS edge_types;"

# Per-agent episode breakdown
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT agent_id, count(*) AS episodes
   FROM ncx_shared__project_titan.episode
   GROUP BY agent_id ORDER BY agent_id;"

# Full ontology
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT type, count(*) AS cnt
   FROM ncx_shared__project_titan.node WHERE forgotten = false
   GROUP BY type ORDER BY cnt DESC;"

docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT type, count(*) AS cnt
   FROM ncx_shared__project_titan.edge
   GROUP BY type ORDER BY cnt DESC;"
```

### 7.2 Compile Metrics

Fill in the results table:

| # | Metric | Target | Measured | Verdict |
|---|--------|--------|----------|---------|
| M1 | Entity dedup rate ≥ 70% | ≥ 4/5 | 4/5 (80%) | **PASS** |
| M2 | Cross-agent recall ≥ 80% | ≥ 8/10 | 8/10 (80%) | **PASS** |
| M3 | Complementary fact merge ≥ 60% | ≥ 3/5 | 0/5 (0%) | **FAIL** |
| M4 | Conflict handling ≥ 66% | ≥ 2/3 | 0/3 (0%) | **FAIL** |
| M5 | Permission enforcement 100% | 0 unauthorized | 0 | **PASS** |
| M6 | No corrupted types | 0 | 0 | **PASS** |
| M7 | Max activation ≤ 0.80 | ≤ 0.80 | 0.816 | **FAIL** |

### 7.3 Graph Growth Analysis

| Metric | Post-Alice (Stage 2) | Post-Bob (Stage 3) | Final (Stage 7) | Growth Factor |
|--------|---------------------|---------------------|-----------------|---------------|
| Nodes | 41 | 51 | 57 | 1.39x |
| Edges | 18 | 18 | 26 | 1.44x |
| Episodes | 5 | 10 | 14 | 2.8x |
| Node Types | 12 | 12 | 14 | |
| Edge Types | 10 | 10 | 15 | |

**Key insight**: POST_BOB_NODES (51) = 1.24 × POST_ALICE_NODES (41) → **dedup IS working** (< 1.5x threshold).
Despite 14 episodes from 2 agents, only 57 unique nodes were created. Shared entities
like Project Titan, Sarah Chen, Marcus Rivera, and PostgreSQL appear exactly once.

### 7.4 Overall Verdict

**Gate**: ≥ 5/7 metrics PASS = OVERALL PASS

**Result: 4/7 PASS → OVERALL FAIL**

The multi-agent shared knowledge graph passes on entity deduplication (M1), cross-agent
recall accessibility (M2), permission enforcement (M5), and ontology quality (M6).
It fails on knowledge merging (M3), conflict resolution (M4), and score bounds (M7).

The system works as a **shared knowledge store with correct access control and deduplication**,
but does NOT yet work as a **knowledge consolidation system** that merges, updates, and
resolves conflicts across agents.

### 7.5 Issues Found

**Issue 1: RLS Blocks Cross-Agent Node Updates in Shared Graphs (PRIMARY ROOT CAUSE for M3, M4)**

This is the most critical finding from the post-mortem code investigation. The shared graph
uses Row-Level Security policies (`schema_manager.py:233-234`):

```sql
CREATE POLICY node_update_policy ON node FOR UPDATE
  USING (owner_role = current_user) WITH CHECK (owner_role = current_user);
```

When Alice creates a node, it gets `owner_role = 'neocortex_agent_alice'`. When Bob's
extraction later tries to update that same node (to merge content or apply a correction),
the UPDATE silently matches 0 rows because RLS hides nodes owned by other agents. This
causes `upsert_node` at `adapter.py:728-729` to raise `RuntimeError("Failed to update node")`,
which crashes the **entire librarian agent run** — not just the single node operation.

The failure sequence:
1. Bob's librarian calls `find_similar_nodes` → finds Alice's existing node
2. Calls `create_or_update_node` (to update with correction or merge content)
3. `upsert_node` finds Alice's node by name (Phase 1 exact match)
4. Executes `UPDATE ... WHERE id = $4 RETURNING ...`
5. RLS blocks the update → `updated_row = None`
6. `RuntimeError("Failed to update node")` → **crashes entire librarian run**
7. Job fails, procrastinate retries (up to 3 attempts)
8. `cleanup_partial_curation` deletes any Bob nodes created before the crash
9. Same crash on every retry → job dead, zero nodes persisted

This explains why:
- M3 (content merge) = 0/5: Bob's librarian cannot UPDATE Alice's nodes to merge facts
- M4 (conflict handling) = 0/3: Bob's corrections crash before creating new nodes or edges
- 4/10 original extraction jobs failed (all Bob's): same RLS wall

The extraction agent prompts are actually **correct** — the librarian is instructed to create
new versioned nodes for corrections and SUPERSEDES edges. But even when the LLM follows
these instructions, it often first tries to update an existing node for a related entity
in the same episode (not just the corrected one), and that UPDATE hits the RLS wall,
killing the entire run before it reaches the correction-handling logic.

Key code locations:
- RLS policies: `src/neocortex/schema_manager.py:233-234`
- RuntimeError on failed UPDATE: `src/neocortex/db/adapter.py:728-729`
- cleanup_partial_curation wiping retry progress: `src/neocortex/extraction/pipeline.py:154-163`
- Librarian correction instructions (correct but unreachable): `src/neocortex/extraction/agents.py:330-345`

**Issue 2: Extraction Tool Call Limit Too Low (4/14 jobs failed)**
- PydanticAI agents hit `tool_calls_limit=50` (`pipeline.py:182`) on complex episodes
- Correction episodes are especially expensive: the librarian must call `find_similar_nodes`,
  `inspect_node_neighborhood`, and `get_edges_between` before deciding to create/update,
  easily consuming 50+ tool calls on a single episode
- Episodes with many interconnected entities (observability stack, project context) also
  trigger too many tool calls even without corrections
- Severity: HIGH — 29% extraction failure rate directly impacts all downstream metrics
- Impact: Reduced test coverage (only 10/14 episodes fully extracted)

**Issue 3: cleanup_partial_curation Guarantees No Progress Survives Retries**
- Before each retry (`pipeline.py:154-163`), `cleanup_partial_curation` deletes ALL nodes
  and edges Bob created from the previous attempt (matched by `properties->>'_source_episode'`)
- Even if Bob successfully created "Apache Pulsar" as a new node before the RLS crash on
  a different node, that progress is wiped before the retry — which will also fail
- On shared graphs where RLS is the root cause, this creates a guaranteed-failure loop:
  partial progress → cleanup → retry → same crash → cleanup → retry → same crash → dead

**Issue 4: Recall Score Exceeds Bound (M7=0.816)**
- A newly created Milestone node (Backend Feature-Complete Deadline) scored 0.816 in recall,
  exceeding the 0.80 target
- This happened with a very specific query ("Project Titan deployment date") that closely
  matched the node's semantic content
- Original 10 generic queries all stayed below 0.80 (max 0.789)

**Issue 5: Recall Type Resolution Bug**
- Many nodes show `item_type: "Unknown"` in recall results despite having valid type_id
  in the database
- The recall tool is not resolving type_id → type name in its response formatting

### 7.6 Recommendations

**1. Fix `upsert_node` to handle RLS-blocked updates gracefully** (Fixes Issues 1, 3; unblocks M3, M4)
- When `updated_row is None` after UPDATE on a shared graph, fall back to INSERT with a
  modified name instead of raising RuntimeError. This is the **minimum viable fix**.
- Location: `src/neocortex/db/adapter.py:728-729`
- Alternative: catch RuntimeError in the librarian tool handler and retry as INSERT

**2. Revise RLS update policy for shared graphs** (Fixes Issue 1 at the root)
- Option A: Allow any agent with write permission to UPDATE any node in the shared graph
  (simplest — change `owner_role = current_user` to a role-membership check)
- Option B: Introduce a co-ownership model where shared-graph nodes are owned by a
  shared role that all permissioned agents can assume
- Option C: Use a "last writer wins" policy with an audit trail for the update history
- Location: `src/neocortex/schema_manager.py:233-234`

**3. Increase extraction tool call limit** (Fixes Issue 2)
- Raise `tool_calls_limit` from 50 to at least 100 in `pipeline.py:182`
- Correction episodes require significantly more tool calls: find existing nodes,
  inspect neighborhoods, create new versioned nodes, create temporal edges
- Even non-correction episodes with densely interconnected entities (e.g., observability
  stack listing 8+ technologies) regularly exceed 50 calls
- Without this, ~29% of extraction jobs fail, undermining all quality metrics

**4. Skip cleanup_partial_curation on shared graphs or on RLS errors** (Fixes Issue 3)
- On shared graphs where the failure is systemic (RLS), cleanup guarantees that no
  progress from partial runs survives. Disable cleanup when the error is RLS-related,
  or skip cleanup for shared-graph retries entirely.
- Location: `src/neocortex/extraction/pipeline.py:154-163`

**5. Fix recall type resolution** (Fixes Issue 5)
- Join node_type table in recall query to return human-readable type names

**6. Add automated multi-agent E2E test**
- Codify the successful parts of this validation (M1, M2, M5, M6) as automated tests
- These passing metrics represent genuine capability worth regression-testing

---

## Verification

- [x] All 7 metrics computed and recorded
- [x] Graph growth analysis complete
- [x] Overall verdict determined: **FAIL** (4/7 pass, gate ≥ 5/7)
- [x] Issues documented (5 issues)
- [x] Recommendations listed (5 recommendations)

---

## Commit

After all stages are complete, update the index.md with final results and commit:
`test(e2e): complete multi-agent shared graph validation plan 22`
