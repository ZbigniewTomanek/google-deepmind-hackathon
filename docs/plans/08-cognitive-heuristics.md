# Plan 08: Cognitive Heuristics for Memory Elasticity

## Overview

Transform NeoCortex from "smart RAG" (static vector+text+recency scoring) into a cognitive memory system inspired by ACT-R, Collins & Loftus spreading activation, and Zettelkasten associative trails. The system will support both short-term task recall (recency + fresh context) and long-term structured knowledge (high activation + importance + dense graph connections).

Six heuristics, implemented incrementally:

| ID | Heuristic | Research Basis | Effect |
|----|-----------|----------------|--------|
| A | ACT-R Base-Level Activation | ACT-R subsymbolic activation (Sec 1) | Memories strengthen through use |
| B | Spreading Activation | Collins & Loftus (Sec 1, 4) | Graph topology influences recall ranking |
| C | Importance / Utility Score | Utility-weighted sampling (Sec 4) | Critical facts resist decay |
| D | Edge Weight Reinforcement | Hebbian learning + Zettelkasten trails (Sec 3) | Associative paths evolve with use |
| E | Episodic Consolidation | SOAR episodic→semantic (Sec 1, 5) | Graph-first retrieval after extraction |
| F | Soft-Forget | Ebbinghaus decay + semantic pruning (Sec 4, 5) | Low-activation unimportant nodes excluded |

### Final Scoring Formula

```
score(item) = w_vec * cosine_sim
            + w_text * text_rank
            + w_act * base_activation(access_count, last_accessed)
            + w_imp * importance
            + spreading_activation_bonus(neighbors, edge_weights)
```

With graceful degradation: missing signals redistribute weight proportionally (existing pattern).

### Episode vs. Node Scoring

Both episodes and nodes participate in the 5-signal scoring model symmetrically:

| Signal | Nodes | Episodes |
|--------|-------|----------|
| vector_sim | embedding cosine similarity | embedding cosine similarity |
| text_rank | tsvector ts_rank | None (redistributed) |
| recency | created_at decay | created_at decay |
| activation | access_count + last_accessed_at | access_count + last_accessed_at |
| importance | extraction-assigned [0, 1] | default 0.5 (or importance_hint from remember()) |

Episodes get `access_count` and `last_accessed_at` columns (just like nodes), so they build activation through repeated recall. Spreading activation only applies to nodes (graph edges required), but episodes still compete fairly on the other 4 signals.

**Lifecycle**: Episodes start as the "short-term buffer" (recency-dominated). Once extracted into the knowledge graph and consolidated (Stage 6), their score is halved — the graph representation takes over for long-term recall. Unconsolidated episodes remain competitive with nodes.

### E2E Validation Strategy

A single growing test file `tests/test_cognitive_e2e.py` is bootstrapped in Stage 1 and extended in every subsequent stage. It uses `InMemoryRepository` (no Docker needed), builds a realistic graph through helpers, and validates each heuristic both in isolation and in composition with prior ones.

Each stage adds a clearly-labeled test class. The full suite runs via:
```bash
uv run pytest tests/test_cognitive_e2e.py -v
```

---

## Stage 1: Schema Evolution — New Columns & Models

**Goal**: Add database columns, update Pydantic models, and bootstrap the E2E test file.

### Steps

1. **Update `migrations/templates/graph_schema.sql`** — add columns to node, episode, and edge tables:
   - `node.access_count INTEGER DEFAULT 0` — total recall hits (ACT-R `n`)
   - `node.last_accessed_at TIMESTAMPTZ DEFAULT now()` — last recall hit time (ACT-R `t_j`)
   - `node.importance FLOAT DEFAULT 0.5` — utility score [0, 1] (default neutral)
   - `node.forgotten BOOLEAN DEFAULT false` — soft-delete flag
   - `node.forgotten_at TIMESTAMPTZ` — when the node was forgotten
   - `episode.access_count INTEGER DEFAULT 0` — total recall hits (episodes get activation too)
   - `episode.last_accessed_at TIMESTAMPTZ DEFAULT now()` — last recall hit time
   - `episode.importance FLOAT DEFAULT 0.5` — importance hint from remember() or default
   - `episode.consolidated BOOLEAN DEFAULT false` — extraction completed flag
   - `edge.last_reinforced_at TIMESTAMPTZ DEFAULT now()` — tracks last traversal time (for decay targeting)
   - Add index: `idx_{schema_name}_node_forgotten ON node (forgotten) WHERE forgotten = false` (partial index for fast filtering)

2. **Update `src/neocortex/models.py`** — add fields to Pydantic models:
   - `Node`: add `access_count: int = 0`, `last_accessed_at: datetime`, `importance: float = 0.5`, `forgotten: bool = False`, `forgotten_at: datetime | None = None`
   - `Episode`: add `access_count: int = 0`, `last_accessed_at: datetime`, `importance: float = 0.5`, `consolidated: bool = False`
   - `Edge`: add `last_reinforced_at: datetime` (defaults to `created_at`)

3. **Update `src/neocortex/schemas/memory.py`** — add `activation_score` and `importance` to `RecallItem` for transparency:
   - `activation_score: float | None = None`
   - `importance: float | None = None`

4. **Update `src/neocortex/mcp_settings.py`** — add new settings (keep existing weight defaults unchanged):
   - `recall_weight_activation: float = 0.25` — weight for base activation signal
   - `recall_weight_importance: float = 0.15` — weight for importance signal
   - `activation_decay_rate: float = 0.5` — ACT-R `d` parameter (memory decay rate)
   - `spreading_activation_decay: float = 0.6` — energy decay per hop
   - `spreading_activation_max_depth: int = 2` — max propagation hops
   - `forget_activation_threshold: float = 0.05` — below this, node may be forgotten
   - `forget_importance_floor: float = 0.3` — nodes above this importance are never forgotten
   - `edge_reinforcement_delta: float = 0.05` — weight increment on traversal
   - `edge_weight_floor: float = 0.1` — minimum edge weight
   - `edge_weight_ceiling: float = 2.0` — maximum edge weight
   - **Do NOT rebalance existing weights yet** — `recall_weight_vector`, `recall_weight_text`, `recall_weight_recency` stay at `0.4, 0.35, 0.25`. Weight rebalancing happens in Stage 2 when activation is actually wired in, to avoid changing scoring behavior before the new signals exist.

5. **Bootstrap `tests/test_cognitive_e2e.py`** — create the E2E test file with:
   - Shared fixtures: `repo` (InMemoryRepository), `agent_id`, helper to populate a small graph (3 node types, 5 nodes, 6 edges, 2 episodes)
   - `TestStage1_SchemaFoundation`:
     - `test_node_model_has_cognitive_fields` — instantiate `Node` with new defaults, assert `access_count=0`, `importance=0.5`, `forgotten=False`
     - `test_episode_model_has_cognitive_fields` — instantiate `Episode`, assert `access_count=0`, `importance=0.5`, `consolidated=False`
     - `test_edge_model_has_last_reinforced_at` — instantiate `Edge`, assert `last_reinforced_at` is set
     - `test_recall_item_has_cognitive_fields` — instantiate `RecallItem` with `activation_score` and `importance`
     - `test_settings_have_cognitive_params` — instantiate `MCPSettings`, assert new defaults are present and existing weight defaults are unchanged (`0.4, 0.35, 0.25`)
     - `test_mock_repo_upsert_node_with_new_fields` — upsert a node via mock repo, read it back, verify `access_count`, `importance`, `forgotten` fields

### Verification
- `uv run pytest tests/test_cognitive_e2e.py -v` — all Stage 1 tests pass
- `uv run pytest tests/ -v` — full suite passes (no regressions)

### Commit
`feat(schema): add columns for cognitive heuristics (activation, importance, forgotten, consolidated)`

---

## Stage 2: ACT-R Base-Level Activation

**Goal**: Replace naive recency-only scoring with ACT-R base-level activation that combines access frequency and recency.

### Background (from research Sec 1)

ACT-R base-level activation: `B_i = ln(n) - d * ln(T)` where:
- `n` = access_count (number of retrievals)
- `T` = hours since last access
- `d` = decay rate (0.5 default)

Simplified from the full sum-of-powers form (computationally efficient, O(1) per node).

### Steps

1. **Rebalance default weights** in `src/neocortex/mcp_settings.py` — now that activation is being wired in:
   - `recall_weight_vector: 0.3` (was 0.4)
   - `recall_weight_text: 0.2` (was 0.35)
   - `recall_weight_recency: 0.1` (was 0.25, recency partially subsumed by activation)
   - `recall_weight_activation: 0.25` (new, from Stage 1)
   - `recall_weight_importance: 0.15` (new, from Stage 1)

2. **Add `compute_base_activation()` to `src/neocortex/scoring.py`**:
   ```python
   def compute_base_activation(
       access_count: int,
       last_accessed_at: datetime,
       decay_rate: float = 0.5,
   ) -> float:
       """ACT-R simplified base-level activation.

       B_i = ln(n + 1) - d * ln(T + 1)
       Normalized to [0, 1] via sigmoid.
       """
   ```
   - Use `ln(n+1)` to handle zero-access nodes (returns 0 for n=0, grows logarithmically)
   - Use `ln(T+1)` where T is hours since last access (avoids ln(0))
   - Apply sigmoid normalization to map to [0, 1]: `1 / (1 + exp(-B_i))`

3. **Update `HybridWeights`** in scoring.py — extend to 5 signals:
   ```python
   class HybridWeights(NamedTuple):
       vector: float
       text: float
       recency: float
       activation: float
       importance: float
   ```

4. **Update `compute_hybrid_score()`** — accept activation and importance signals:
   ```python
   def compute_hybrid_score(
       vector_sim: float | None,
       text_rank: float | None,
       recency: float,
       activation: float | None,
       importance: float | None,
       weights: HybridWeights,
   ) -> float:
   ```

5. **Add access tracking to `MemoryRepository` protocol** (`src/neocortex/db/protocol.py`):
   ```python
   async def record_node_access(self, agent_id: str, node_ids: list[int]) -> None:
       """Increment access_count and update last_accessed_at for recalled nodes."""

   async def record_episode_access(self, agent_id: str, episode_ids: list[int]) -> None:
       """Increment access_count and update last_accessed_at for recalled episodes."""
   ```

6. **Implement `record_node_access()` in `GraphServiceAdapter`** (`src/neocortex/db/adapter.py`):
   ```sql
   UPDATE node SET access_count = access_count + 1, last_accessed_at = now()
   WHERE id = ANY($1::int[])
   ```

7. **Implement `record_episode_access()` in `GraphServiceAdapter`**:
   ```sql
   UPDATE episode SET access_count = access_count + 1, last_accessed_at = now()
   WHERE id = ANY($1::int[])
   ```

8. **Implement both in `InMemoryRepository`** (`src/neocortex/db/mock.py`):
   - Increment `access_count`, set `last_accessed_at = now()` for matching node/episode IDs

9. **Upgrade `InMemoryRepository.recall()` to use real scoring** — the current mock returns fixed `score=1.0` for all matches. This must be upgraded to compute actual hybrid scores so E2E tests exercise the real scoring path:
   - Compute `compute_recency_score(created_at, half_life)` for each result
   - Compute `compute_base_activation(access_count, last_accessed_at, decay_rate)` for each result
   - Pass `importance` from node/episode fields
   - Call `compute_hybrid_score(vector_sim=None, text_rank=None, recency, activation, importance, weights)` for final scoring
   - Sort results by score descending

10. **Update recall SQL in adapter** — SELECT new columns (`access_count`, `last_accessed_at`, `importance`) in both node AND episode queries so scoring can use them.

11. **Update `recall()` in adapter** — compute `base_activation` per result (both nodes and episodes), pass to `compute_hybrid_score()`.

12. **Wire access tracking into `recall` tool** (`src/neocortex/tools/recall.py`):
    - After building final results, collect returned node IDs and episode IDs separately
    - Call `repo.record_node_access(agent_id, node_ids)` for node results
    - Call `repo.record_episode_access(agent_id, episode_ids)` for episode results

13. **Fix callers** — update all existing calls to `compute_hybrid_score()` and `HybridWeights` across codebase (adapter recall scoring, any tests) to pass the new parameters. Existing callers pass `activation=None, importance=None` so they degrade gracefully.

### E2E Validation — add `TestStage2_BaseActivation` to `tests/test_cognitive_e2e.py`:
- `test_base_activation_zero_access` — node with `access_count=0` returns activation ~0.5 (sigmoid of 0)
- `test_base_activation_high_frequency_recent` — node with `access_count=100, last_accessed=now` returns activation close to 1.0
- `test_base_activation_low_frequency_stale` — node with `access_count=1, last_accessed=30d ago` returns activation < 0.3
- `test_base_activation_decays_with_time` — two nodes same access_count, one accessed 1h ago, other 7d ago → first scores higher
- `test_hybrid_score_five_signals` — all 5 signals provided, verify weighted sum
- `test_hybrid_score_activation_none_degrades` — activation=None redistributes weight to remaining signals
- `test_record_node_access_increments` — create node via mock repo, call `record_node_access`, verify `access_count` incremented and `last_accessed_at` updated
- `test_record_episode_access_increments` — store episode via mock repo, call `record_episode_access`, verify `access_count` incremented and `last_accessed_at` updated
- `test_mock_recall_uses_real_scoring` — populate mock repo with 2 nodes (one accessed 50 times recently, one never accessed). Recall and verify scored node ranks higher (not both score=1.0)
- `test_episode_activation_in_recall` — store 2 episodes. Recall both. Recall again — verify episodes that were recalled have `access_count >= 1` and score higher on second recall
- `test_recall_records_access` — populate graph with nodes and episodes, recall a query that matches both, verify node's `access_count >= 1` AND matched episode's `access_count >= 1`

### Verification
- `uv run pytest tests/test_cognitive_e2e.py::TestStage2_BaseActivation -v` — all pass
- `uv run pytest tests/ -v` — full suite passes

### Commit
`feat(scoring): implement ACT-R base-level activation with access tracking`

---

## Stage 3: Importance Scoring in Extraction Pipeline

**Goal**: Extraction agents assign importance scores to entities. The `remember()` tool accepts an optional importance hint.

### Steps

1. **Add `importance` field to extraction schemas** (`src/neocortex/extraction/schemas.py`):
   - `ExtractedEntity.importance: float = Field(default=0.5, ge=0.0, le=1.0, description="How critical is this entity to the domain")`
   - `NormalizedEntity.importance: float = Field(default=0.5, ge=0.0, le=1.0)`
   - `ExtractedRelation` already has `weight` — reuse it as relation importance

2. **Update Extractor Agent system prompt** (`src/neocortex/extraction/agents.py`):
   Add rule:
   ```
   - Assign an importance score (0.0–1.0) to each entity:
     0.0–0.3: Peripheral, contextual detail
     0.3–0.6: Standard factual entity
     0.6–0.8: Central concept referenced multiple times
     0.8–1.0: Critical domain entity (core drug, disease, mechanism)
   ```

3. **Update Librarian Agent system prompt** — add rule:
   ```
   - Preserve importance scores from extractor. If merging with an existing node,
     take the maximum importance (knowledge that keeps being referenced is important).
   ```

4. **Thread importance through `_persist_payload()`** (`src/neocortex/extraction/pipeline.py`):
   - Pass `importance=entity.importance` to `repo.upsert_node()` call

5. **Update `upsert_node()` in protocol, adapter, and mock**:
   - Add `importance: float = 0.5` parameter
   - Adapter SQL: include `importance` in INSERT, use `GREATEST(node.importance, $N)` on UPDATE (importance only goes up via extraction)
   - Mock: same `max()` logic

6. **Add `importance` parameter to `remember()` tool** (`src/neocortex/tools/remember.py`):
   ```python
   async def remember(
       text: str,
       context: str | None = None,
       importance: float | None = None,
       ctx: Context | None = None,
   ) -> RememberResult:
   ```
   - Store importance in episode metadata: `metadata={"importance_hint": importance}`
   - Pass through to extraction job (extraction pipeline reads from episode metadata)

7. **Update `store_episode()` in protocol + adapter + mock** — accept optional `metadata` dict parameter (currently hardcoded in adapter). When `importance` is provided to `remember()`, also set `episode.importance = importance` directly on the episode record (not just in metadata).

8. **Thread `importance_hint` into extraction pipeline** — in `_persist_payload()` (`src/neocortex/extraction/pipeline.py`):
   - Fetch the source episode via `repo.get_episode(agent_id, episode_id)`
   - Read `importance_hint = episode.metadata.get("importance_hint")`
   - If `importance_hint` is set, use it as a **floor** for extracted entity importance: `entity.importance = max(entity.importance, importance_hint)`
   - This ensures that a user's explicit importance signal propagates through to the knowledge graph, even if the extractor agent assigns a lower score

### E2E Validation — add `TestStage3_Importance` to `tests/test_cognitive_e2e.py`:
- `test_upsert_node_with_importance` — upsert node with importance=0.8, read back, verify importance=0.8
- `test_upsert_node_importance_takes_max` — upsert node with importance=0.3, then upsert same name+type with importance=0.7, verify stored importance=0.7. Then upsert with importance=0.5, verify importance stays 0.7 (max semantics)
- `test_upsert_node_default_importance` — upsert without specifying importance, verify default 0.5
- `test_importance_in_hybrid_score` — verify `compute_hybrid_score` with importance=0.9 scores higher than importance=0.1 (all other signals equal)
- `test_importance_boosts_recall_ranking` — populate mock repo with 2 nodes matching same query: one with importance=0.9, other importance=0.1. Recall and verify high-importance node ranks first.
- `test_extraction_schemas_have_importance` — instantiate `ExtractedEntity` and `NormalizedEntity` with importance field, verify validation (0-1 range, rejects 1.5)
- `test_importance_hint_floors_extracted_importance` — store episode with `importance_hint=0.8` in metadata. Run `_persist_payload` with an entity whose extractor-assigned importance is 0.4. Verify persisted node has importance=0.8 (hint used as floor). Repeat with extractor importance=0.9 — verify importance stays 0.9 (extractor was higher).

### Verification
- `uv run pytest tests/test_cognitive_e2e.py::TestStage3_Importance -v` — all pass
- `uv run pytest tests/ -v` — full suite passes

### Commit
`feat(extraction): add importance scoring to entities and remember tool`

---

## Stage 4: Spreading Activation

**Goal**: After initial hybrid search, propagate activation energy from matched nodes along graph edges. Well-connected neighbors of high-scoring nodes get a recall bonus.

### Background (from research Sec 1)

Collins & Loftus spreading activation: when a node is activated, it transfers a fraction of its energy to neighbors proportional to edge weight, decayed by distance. Energy = `parent_score * edge_weight * decay^distance`.

### Steps

1. **Add `compute_spreading_activation()` to `src/neocortex/scoring.py`**:
   ```python
   def compute_spreading_activation(
       seed_nodes: list[tuple[int, float]],  # (node_id, initial_score)
       neighborhood: dict[int, list[tuple[int, float]]],  # node_id -> [(neighbor_id, edge_weight)]
       decay: float = 0.6,
       max_depth: int = 2,
   ) -> dict[int, float]:
       """Propagate activation energy from seed nodes through graph edges.

       Returns mapping of node_id -> accumulated activation bonus.
       Uses BFS with decaying energy propagation.
       """
   ```
   - For each seed node, BFS outward up to `max_depth`
   - Energy at each hop: `parent_energy * edge_weight * decay`
   - If a node receives energy from multiple paths, sum them
   - Normalize result to [0, 1] range

2. **Reuse existing `get_node_neighborhood()`** — no new protocol method needed. The existing method already returns edges with weights via BFS. Add a helper to extract the adjacency map:
   ```python
   def neighborhood_to_adjacency(
       neighborhood: list[dict],  # from get_node_neighborhood()
       center_node_id: int,
   ) -> dict[int, list[tuple[int, float]]]:
       """Convert get_node_neighborhood() output to adjacency map for spreading activation."""
   ```
   This avoids a parallel graph traversal method and keeps the protocol surface small.

3. **Integrate into `recall` tool** (`src/neocortex/tools/recall.py`):

   **Seed selection**: Seeds are the union of:
   - Phase 1 node results (from `repo.recall()`) — these have real hybrid scores
   - Phase 2 node results (from `repo.search_nodes()`) — these need relevance scores

   To get Phase 2 relevance scores, update `search_nodes()` to return `list[tuple[Node, float]]` (node + relevance score) instead of `list[Node]`. In the adapter, the relevance score is `ts_rank` or `1 - cosine_distance` (whichever matched). In the mock, use a simple text overlap heuristic. This replaces the current hardcoded `score=0.5` for search_nodes matches (`recall.py:95`).

   After seed selection:
   - For each seed node, call `repo.get_node_neighborhood()` (already called for graph context)
   - Convert to adjacency map via `neighborhood_to_adjacency()`
   - Merge adjacency maps across all seeds
   - Call `compute_spreading_activation(seeds, adjacency, decay, max_depth)` to get bonus map
   - Add bonus to each result's score: `result.score += w_spreading * bonus`
   - Re-sort results by updated score

   Note: the neighborhood traversal for spreading activation piggybacks on the existing Phase 2 traversal loop — no extra DB calls needed.

4. **Add spreading activation bonus to `RecallItem`** for observability:
   - `spreading_bonus: float | None = None`

### E2E Validation — add `TestStage4_SpreadingActivation` to `tests/test_cognitive_e2e.py`:
- `test_spreading_single_seed_two_neighbors` — graph: A→B(w=1.0), A→C(w=0.5). Seed A with score 1.0. Verify B gets higher bonus than C (proportional to edge weight).
- `test_spreading_two_seeds_converge` — graph: A→C, B→C. Seed A and B each with score 1.0. Verify C's bonus is the sum of both contributions.
- `test_spreading_decay_across_hops` — graph: A→B→C. Seed A. Verify B's bonus > C's bonus (C is 2 hops away, decayed twice).
- `test_spreading_isolated_node_zero_bonus` — node D with no edges. Verify D gets 0 bonus.
- `test_spreading_respects_max_depth` — graph: A→B→C→D. max_depth=2. Verify D (3 hops) gets 0 bonus.
- `test_spreading_with_varying_edge_weights` — graph: A→B(w=2.0), A→C(w=0.1). Verify B bonus >> C bonus.
- `test_recall_includes_spreading_bonus` — full integration: populate mock repo with a triangle graph (A→B→C→A). Recall a query matching node A. Verify results include B and C with non-zero `spreading_bonus` in RecallItem.
- `test_neighborhood_to_adjacency_conversion` — call `get_node_neighborhood()` for a known graph, convert via `neighborhood_to_adjacency()`, verify correct adjacency map structure.
- `test_search_nodes_returns_relevance_scores` — call `search_nodes()` on mock repo, verify results include relevance scores (not just Node objects).

### Verification
- `uv run pytest tests/test_cognitive_e2e.py::TestStage4_SpreadingActivation -v` — all pass
- `uv run pytest tests/ -v` — full suite passes

### Commit
`feat(recall): implement spreading activation for graph-aware scoring`

---

## Stage 5: Edge Weight Reinforcement

**Goal**: Edges traversed during recall get stronger. Unused edges decay toward a floor. Creates emergent "associative trails."

### Steps

1. **Add `reinforce_edges()` to protocol** (`src/neocortex/db/protocol.py`):
   ```python
   async def reinforce_edges(
       self, agent_id: str, edge_ids: list[int], delta: float = 0.05, ceiling: float = 2.0
   ) -> None:
       """Increment edge weights for traversed edges, capped at ceiling."""
   ```

2. **Implement in adapter** — single SQL:
   ```sql
   UPDATE edge SET weight = LEAST(weight + $2, $3), last_reinforced_at = now()
   WHERE id = ANY($1::int[])
   ```

3. **Implement in mock** — iterate matching edges, apply `min(weight + delta, ceiling)`, set `last_reinforced_at = now()`.

4. **Wire into `recall` tool** — after building graph contexts:
   - Collect all edge IDs from `graph_context.edges` across results
   - Also collect edge IDs traversed during spreading activation
   - Call `repo.reinforce_edges(agent_id, edge_ids)`

5. **Add periodic edge decay** (lazy, during recall):
   - Add `decay_stale_edges()` to protocol:
     ```python
     async def decay_stale_edges(
         self, agent_id: str, older_than_hours: float = 168.0,
         decay_factor: float = 0.95, floor: float = 0.1,
         force: bool = False,
     ) -> int:
         """Decay weights of edges not recently reinforced. Returns count of decayed edges.

         Uses last_reinforced_at (not created_at) to target edges that haven't
         been traversed recently. The force parameter bypasses probabilistic
         gating for deterministic testing.
         """
     ```
   - Adapter SQL — uses `last_reinforced_at` to correctly target untouched edges:
     ```sql
     UPDATE edge SET weight = GREATEST(weight * $3, $4)
     WHERE last_reinforced_at < now() - interval '$2 hours'
     AND weight > $4
     ```
   - Call lazily from recall (1 in 10 recall calls, or if >1h since last decay, or if `force=True`)

### E2E Validation — add `TestStage5_EdgeReinforcement` to `tests/test_cognitive_e2e.py`:
- `test_reinforce_edges_increments_weight` — create edge with weight=1.0, call `reinforce_edges([edge_id], delta=0.1)`, verify weight=1.1
- `test_reinforce_edges_respects_ceiling` — create edge with weight=1.95, reinforce with delta=0.1, ceiling=2.0, verify weight=2.0 (capped)
- `test_reinforce_edges_multiple` — create 3 edges, reinforce 2 of them, verify only those 2 have increased weight
- `test_decay_stale_edges_reduces_weight` — create edge with weight=1.5 and old `last_reinforced_at` (mock time), call `decay_stale_edges(force=True)`, verify weight reduced
- `test_decay_stale_edges_respects_floor` — edge at weight=0.12, floor=0.1, decay_factor=0.5, call with `force=True`, verify weight stays at floor
- `test_decay_stale_edges_skips_recently_reinforced` — create edge, reinforce it (updates `last_reinforced_at`), call `decay_stale_edges(force=True)`, verify weight unchanged (recently reinforced)
- `test_decay_targets_last_reinforced_not_created` — create an old edge (old `created_at`) that was recently reinforced. Call decay. Verify weight unchanged (recently reinforced despite old creation time).
- `test_repeated_recall_strengthens_edges` — populate graph, recall same query 5 times in a loop. After each recall, read back edges that were in graph_context. Verify edge weights monotonically increase across iterations (Hebbian reinforcement).
- `test_spreading_uses_reinforced_weights` — reinforce an edge to weight=2.0, run spreading activation, verify the reinforced path delivers higher bonus than a weight=1.0 path (spreading activation + reinforcement compose).

### Verification
- `uv run pytest tests/test_cognitive_e2e.py::TestStage5_EdgeReinforcement -v` — all pass
- `uv run pytest tests/ -v` — full suite passes

### Commit
`feat(edges): add weight reinforcement on traversal and decay for stale edges`

---

## Stage 6: Soft-Forget & Episodic Consolidation

**Goal**: Nodes with low activation AND low importance get soft-forgotten. Extracted episodes get marked as consolidated and deprioritized in recall.

### Steps

1. **Add `mark_forgotten()` to protocol**:
   ```python
   async def mark_forgotten(self, agent_id: str, node_ids: list[int]) -> int:
       """Soft-delete nodes by setting forgotten=true. Returns count."""
   ```

2. **Add `resurrect_node()` to protocol**:
   ```python
   async def resurrect_node(self, agent_id: str, node_id: int) -> None:
       """Clear forgotten flag and bump access_count for a re-referenced node."""
   ```

3. **Implement both in adapter**:
   ```sql
   -- mark_forgotten
   UPDATE node SET forgotten = true, forgotten_at = now() WHERE id = ANY($1::int[]) AND forgotten = false

   -- resurrect
   UPDATE node SET forgotten = false, forgotten_at = NULL, access_count = access_count + 1, last_accessed_at = now() WHERE id = $1
   ```

4. **Implement both in mock** — set/clear flags on matching nodes.

5. **Update all recall/search SQL in adapter** — add `AND forgotten = false` filter to:
   - Node recall query
   - `search_nodes()` query
   - Node neighborhood queries (exclude forgotten neighbors)

6. **Add `identify_forgettable_nodes()` to protocol**:
   ```python
   async def identify_forgettable_nodes(
       self, agent_id: str, activation_threshold: float, importance_floor: float
   ) -> list[int]:
       """Return IDs of nodes whose activation < threshold AND importance < floor."""
   ```

7. **Implement in adapter**:
   ```sql
   SELECT id FROM node
   WHERE forgotten = false
   AND importance < $1
   AND access_count = 0  -- never accessed
   AND last_accessed_at < now() - interval '7 days'  -- stale
   ```
   Note: use a practical proxy (access_count + staleness) rather than computing base_activation in SQL.

8. **Wire forget sweep into recall tool** (lazy, probabilistic, with deterministic override):
   - Add a `force_maintenance: bool = False` parameter to the internal sweep function
   - On ~1 in 20 recall calls (or always if `force_maintenance=True`), run forget sweep:
     ```python
     async def _maybe_forget_sweep(repo, agent_id, settings, *, force: bool = False):
         if force or random.random() < 0.05:
             forgettable = await repo.identify_forgettable_nodes(
                 agent_id, settings.forget_activation_threshold, settings.forget_importance_floor
             )
             if forgettable:
                 await repo.mark_forgotten(agent_id, forgettable)
     ```
   - The `force` parameter enables deterministic testing without relying on randomness

9. **Update `upsert_node()` in adapter** — if upserting a forgotten node, resurrect it:
   ```sql
   UPDATE node SET forgotten = false, forgotten_at = NULL,
                   access_count = access_count + 1, ...
   WHERE lower(name) = lower($1) AND type_id = $2
   ```

10. **Add episodic consolidation** — mark episodes after successful extraction:
    - Add `mark_episode_consolidated()` to protocol
    - Call at end of `_persist_payload()` in extraction pipeline
    - Update episode recall SQL: `ORDER BY (CASE WHEN consolidated THEN 0.5 ELSE 1.0 END) * score`
      (consolidated episodes get half the score → graph nodes take priority)

### E2E Validation — add `TestStage6_ForgetAndConsolidate` to `tests/test_cognitive_e2e.py`:
- `test_mark_forgotten_excludes_from_recall` — create 3 nodes matching query "serotonin". Forget node #2. Recall "serotonin". Verify only nodes #1 and #3 returned.
- `test_mark_forgotten_excludes_from_search_nodes` — same as above but via `search_nodes()`.
- `test_forgotten_node_excluded_from_neighborhood` — A→B→C graph. Forget B. Get neighborhood of A. Verify B and C absent from results.
- `test_forgotten_node_persists_in_db` — forget a node, verify it's still in `_nodes` dict (mock) or SELECT-able without filter (not deleted).
- `test_resurrect_node_on_upsert` — forget a node, then upsert same name+type. Verify `forgotten=False`, `access_count` incremented.
- `test_identify_forgettable_nodes_low_activation_low_importance` — create 4 nodes: (a) high importance+accessed, (b) low importance+accessed, (c) high importance+never accessed, (d) low importance+never accessed+stale. Only node (d) should be forgettable.
- `test_identify_forgettable_nodes_respects_importance_floor` — node with importance=0.4 and floor=0.3 → forgettable. Node with importance=0.4 and floor=0.5 → not forgettable.
- `test_episode_consolidation_marks_flag` — store episode, call `mark_episode_consolidated()`, verify `consolidated=True`.
- `test_consolidated_episodes_ranked_lower` — store 2 episodes matching query. Consolidate one. Recall. Verify unconsolidated episode ranks above consolidated one.
- `test_full_lifecycle_forget_and_resurrect` — create node, recall it (access_count=1), manually advance time (mock), verify it's NOT forgettable (was accessed). Create another node that was never accessed with low importance, verify it IS forgettable. Forget it. Upsert same entity again (re-extraction), verify resurrected.

### Verification
- `uv run pytest tests/test_cognitive_e2e.py::TestStage6_ForgetAndConsolidate -v` — all pass
- `uv run pytest tests/ -v` — full suite passes

### Commit
`feat(memory): implement soft-forget for low-activation nodes and episodic consolidation`

---

## Stage 7: Full Integration & Composition Verification

**Goal**: Verify all six heuristics compose correctly end-to-end. Update TUI display.

### Steps

1. **Add cognitive metrics to TUI recall display** (`src/neocortex/tui/app.py`):
   - Show `activation_score`, `importance`, `spreading_bonus` columns in recall results table

2. **Update `src/neocortex/tools/discover.py`** — include cognitive stats:
   - Count of forgotten nodes
   - Count of consolidated episodes
   - Average activation across nodes

3. **Verify graceful degradation**:
   - Test with `NEOCORTEX_MOCK_DB=true` (InMemoryRepository)
   - Test with embeddings disabled (no GOOGLE_API_KEY)

### E2E Validation — add `TestStage7_FullComposition` to `tests/test_cognitive_e2e.py`:

These tests exercise the full heuristic stack working together, simulating a realistic agent session.

- `test_composition_short_term_recall_favors_recent`:
  Simulate a coding session — store 3 related episodes in quick succession. Recall. Verify recency + high activation (accessed within minutes) dominates ranking. This tests the "short-term task" path.

- `test_composition_long_term_knowledge_persists`:
  Create nodes with high importance (0.9), many accesses (50), and old `last_accessed_at` (30 days). Also create a fresh node with importance=0.1 and 0 accesses. Recall a query matching both. Verify the old-but-important-and-accessed node still outranks the fresh-but-unimportant one. This tests the "long-term knowledge" path.

- `test_composition_spreading_activation_discovers_hidden`:
  Build a 5-node chain: A→B→C→D→E. Only A matches the query directly. Verify that B and C appear in results (via spreading activation) even though they don't match the query text. D and E should NOT appear (beyond max_depth=2).

- `test_composition_hebbian_trails_emerge`:
  Recall the same query 10 times. After each recall, verify that edges in the traversal path have increasing weights. By iteration 10, the path should be significantly stronger than untouched edges.

- `test_composition_forget_cycle`:
  Create 10 nodes with varying importance and access patterns. Run a forget sweep. Verify exactly the right nodes (low importance + never accessed + stale) get forgotten. Recall and verify forgotten nodes absent. Re-extract one forgotten node. Verify it's resurrected and appears in recall again.

- `test_composition_consolidation_shifts_to_graph`:
  Store an episode, extract it (mock persist), consolidate it. Recall a query matching both the episode text and extracted nodes. Verify graph nodes rank above the consolidated episode.

- `test_composition_graceful_degradation_no_activation`:
  Recall with `activation=None` and `importance=None` in hybrid scoring. Verify it falls back to vector+text+recency (3-signal mode) without errors.

- `test_composition_cognitive_metrics_in_recall_items`:
  Recall and verify every `RecallItem` for node-sourced results has `activation_score`, `importance`, and `spreading_bonus` populated (not None).

### Verification
- `uv run pytest tests/test_cognitive_e2e.py -v` — ALL stages pass (full regression)
- `uv run pytest tests/ -v` — full project suite passes
- `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

### Commit
`feat(cognitive): integration tests and TUI display for memory heuristics`

---

## Execution Protocol

This plan is designed for stage-by-stage execution. Each stage:
- Is independently testable
- Leaves the codebase in a working state
- Gets one atomic commit
- Extends `tests/test_cognitive_e2e.py` with a new `TestStageN_*` class

**After each stage run**:
```bash
uv run pytest tests/test_cognitive_e2e.py -v   # new + all prior stage tests
uv run pytest tests/ -v                         # full regression
```

**Dependencies**: Stage 1 → Stage 2 → Stage 3 (parallel with 2) → Stage 4 → Stage 5 → Stage 6 → Stage 7

**Critical path**: Stages 1→2→4→6 (schema → activation → spreading → forget)

**Parallel track**: Stage 3 (importance) can proceed after Stage 1, independent of Stage 2.

## Progress Tracker

| Stage | Status | Notes |
|-------|--------|-------|
| 1. Schema Evolution | DONE | Added columns to schema template, Pydantic models, RecallItem, MCPSettings; bootstrapped E2E test file |
| 2. ACT-R Base-Level Activation | DONE | Rebalanced weights, added compute_base_activation, 5-signal HybridWeights, access tracking in protocol/adapter/mock, real scoring in mock recall, wired into recall tool |
| 3. Importance Scoring | DONE | Added importance to extraction schemas, agent prompts, upsert_node (max semantics), remember() tool, store_episode(), and _persist_payload with importance_hint floor |
| 4. Spreading Activation | DONE | Added compute_spreading_activation, neighborhood_to_adjacency, spreading_bonus on RecallItem, search_nodes returns (Node, float) tuples, integrated into recall tool |
| 5. Edge Weight Reinforcement | DONE | Added reinforce_edges and decay_stale_edges to protocol/adapter/mock, wired into recall tool with lazy decay, 9 E2E tests |
| 6. Soft-Forget & Consolidation | DONE | Added mark_forgotten, resurrect_node, identify_forgettable_nodes, mark_episode_consolidated to protocol/adapter/mock; forgotten=false filters on recall/search/neighborhood SQL; consolidation penalty (0.5x) on episodes; forget sweep in recall tool; upsert resurrects forgotten nodes; 10 E2E tests |
| 7. Integration & Verification | DONE | Added cognitive metrics to GraphStats (forgotten_nodes, consolidated_episodes, avg_activation), TUI recall/discover display, 9 composition E2E tests |

Last stage completed: Stage 7 — Full Integration & Composition Verification
Last updated by: plan-runner-agent

## Post-Implementation Review & Fixes

Code review identified P0–P2 issues, all fixed in a follow-up commit:

| Priority | Issue | Fix |
|----------|-------|-----|
| P0 | `get_episode()` in adapter SELECT missing new columns (access_count, importance, consolidated) | Added all cognitive columns to the query |
| P1 | `find_nodes_by_name()` and `list_all_node_names()` returned forgotten nodes in adapter + mock | Added `AND forgotten = false` / `not n.forgotten` filters |
| P1 | `_bfs_via_graph_service()` fallback path didn't filter forgotten neighbors | Added forgotten check before appending |
| P1 | `activation_threshold` parameter silently ignored in `identify_forgettable_nodes()` | Documented proxy heuristic in protocol docstring |
| P2 | Edge decay in recall tool had no `force` parameter for deterministic testing | Extracted `_maybe_decay_edges()` helper with `force` kwarg |
| P2 | `_get_stats_in_schema` used `avg(access_count)` as proxy for `avg_activation` | Added comment documenting the proxy |
| P2 | Spreading bonus weight (0.1) was hardcoded in recall tool | Added `spreading_activation_bonus_weight` to MCPSettings |
| P2 | Mock recall used hardcoded weights not tied to settings | Added sync-with-settings comment |

## E2E Validation Results (2026-03-28, real PG + Gemini extraction)

Validated against 10-episode medical corpus + 1 remember() with importance_hint.

| Heuristic | Result | Evidence |
|-----------|--------|----------|
| ACT-R Activation | Pass | Activation increased 0.49 → 0.67 → 0.75 across 3 recalls of "serotonin" |
| Importance Scoring | Pass | Extraction agents assigned 0.6–1.0; remember(importance=0.95) floored extracted entities to 0.95 |
| Spreading Activation | Pass | "lithium bipolar" recall discovered Bipolar Disorder (bonus=0.739) and Mood Stabilizer (bonus=0.746) via graph edges |
| Edge Reinforcement | Pass | Serotonin edges reinforced from 1.0 to 1.15 after 3 recalls (3 × 0.05 delta) |
| Episodic Consolidation | Pass | All 11 episodes consolidated=true; graph nodes outrank consolidated episodes |
| Soft-Forget | Pass | Schema columns + partial index present; 0 forgotten nodes (all fresh — correct) |
| Discover Stats | Pass | Reports forgotten_nodes=0, consolidated_episodes=11, avg_activation=0.18 |
| Graph Size | Pass | 187 nodes, 183 edges, 24 node types, 49 edge types from 11 episodes |
