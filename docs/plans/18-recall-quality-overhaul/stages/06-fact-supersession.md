# Stage 6: Fact Supersession

**Goal**: Enable the extraction pipeline to detect corrections/reversals and create temporal relationship edges so that recall can prefer newer facts over outdated ones.
**Dependencies**: Stage 5 (type validation must be in place since we're adding new edge types)

---

## Background

The E2E test stored a 3-step fact evolution:
1. Feb 28: "4-char Metaphone3 creates too many pairs" (concern)
2. Mar 5: "Switching to 8-char Metaphone3" (decision)
3. Mar 30: "CORRECTION — hybrid approach: 8-char Latin, 4-char non-Latin" (reversal)

Recall for "current Metaphone3 strategy" returned the February nodes, not the March correction. The system has no mechanism to prefer newer facts.

The seed ontology (`004_seed_ontology.sql`) includes `CONTRADICTS` and `SUPPORTS` but lacks explicit supersession types. The librarian agent is instructed to handle corrections ("if new info SUPERSEDES old...") but only overwrites content — it doesn't create temporal edges.

**Fix**: Three changes:
1. Seed `SUPERSEDES` and `CORRECTS` edge types
2. Teach the librarian agent to create these edges when it detects corrections
3. Add a supersession boost in scoring: nodes with incoming `SUPERSEDES`/`CORRECTS` edges get a penalty, while the superseding node gets a boost

---

## Steps

1. **Seed temporal edge types**
   - **Do NOT modify** `migrations/init/004_seed_ontology.sql` — it has already been applied in existing databases. Modifying it won't retroactively add the new types.
   - Create a new migration file (use the next available number, e.g., `migrations/init/009_temporal_edge_types.sql`):
     ```sql
     -- Temporal edge types for fact supersession (Plan 18, Stage 6)
     INSERT INTO edge_type (name, description) VALUES
       ('SUPERSEDES', 'Source supersedes/replaces target — target is outdated'),
       ('CORRECTS', 'Source corrects an error or misconception in target')
     ON CONFLICT (name) DO NOTHING;
     ```
   - Also add these to the schema template so new per-graph schemas get them:
   - File: `migrations/templates/graph_schema.sql`
   - Find the seed edge types section and append the same INSERT.

2. **Update the librarian agent prompt to create supersession edges**
   - File: `src/neocortex/extraction/agents.py`
   - In the librarian agent's system prompt (around line 260), add explicit guidance:
     ```
     TEMPORAL RELATIONSHIPS:
     - If new information CORRECTS a previous fact (error fix, misconception):
       After updating the node, also create an edge of type "CORRECTS" from the
       new/updated node to the old node.
     - If new information SUPERSEDES a previous decision or version (newer version,
       reversed decision, updated strategy): After updating the node, also create
       an edge of type "SUPERSEDES" from the new/updated node to the old node.
     - Look for signals: "CORRECTION", "UPDATE", "REVERSAL", "actually", "instead",
       "no longer", "changed to", "replaced by", "switched from".
     ```
   - Ensure the librarian has access to a tool for creating edges (it should already have `create_or_update_edge` or similar from the existing tool-driven mode).

3. **Add supersession scoring function**
   - File: `src/neocortex/scoring.py`
   - Add a function to compute a supersession adjustment:
     ```python
     def compute_supersession_adjustment(
         node_id: int,
         supersession_edges: dict[str, dict[int, list]],
     ) -> float:
         """Returns a score multiplier based on supersession edges.

         Args:
             node_id: The node to check.
             supersession_edges: Dict with keys "superseded_by" (node_id → edges where
                 this node is the target of SUPERSEDES/CORRECTS) and "supersedes"
                 (node_id → edges where this node is the source).

         Returns:
             0.5 for superseded nodes, 1.2 for superseding nodes, 1.0 otherwise.
         """
         if node_id in supersession_edges.get("superseded_by", {}):
             return 0.5  # Penalize outdated nodes

         if node_id in supersession_edges.get("supersedes", {}):
             return 1.2  # Boost correcting nodes

         return 1.0  # Neutral
     ```

4. **Fetch supersession edges during recall**
   - File: `src/neocortex/db/adapter.py`, method `_recall_in_schema`
   - After fetching candidate nodes but **before the inline scoring block** (lines ~1717-1798), fetch supersession edges:
     ```python
     # Fetch supersession relationships for candidate nodes
     supersession_type_ids = await conn.fetch(
         "SELECT id FROM edge_type WHERE name IN ('SUPERSEDES', 'CORRECTS')"
     )
     type_ids = [r["id"] for r in supersession_type_ids]

     supersession_edges: dict[str, dict[int, list]] = {"superseded_by": {}, "supersedes": {}}

     if type_ids and candidate_node_ids:
         superseded_rows = await conn.fetch(
             "SELECT target_id, source_id FROM edge "
             "WHERE type_id = ANY($1::int[]) AND target_id = ANY($2::int[])",
             type_ids, candidate_node_ids,
         )
         superseding_rows = await conn.fetch(
             "SELECT source_id, target_id FROM edge "
             "WHERE type_id = ANY($1::int[]) AND source_id = ANY($2::int[])",
             type_ids, candidate_node_ids,
         )
         for r in superseded_rows:
             supersession_edges["superseded_by"].setdefault(r["target_id"], []).append(r)
         for r in superseding_rows:
             supersession_edges["supersedes"].setdefault(r["source_id"], []).append(r)
     ```

5. **Apply supersession adjustment in the inline scoring block**
   - File: `src/neocortex/db/adapter.py`, method `_recall_in_schema` (lines ~1717-1798)
   - After computing `hybrid_score` for each node, apply the adjustment:
     ```python
     from neocortex.scoring import compute_supersession_adjustment

     # After: score = compute_hybrid_score(...)
     adjustment = compute_supersession_adjustment(node_id, supersession_edges)
     score *= adjustment
     ```
   - Supersession adjustment applies to **nodes only** (episodes don't have SUPERSEDES edges).

6. **Add settings for supersession adjustments**
   - File: `src/neocortex/mcp_settings.py`
   - Add:
     ```python
     # Supersession scoring adjustments
     recall_superseded_penalty: float = 0.5    # Multiplier for outdated nodes
     recall_superseding_boost: float = 1.2     # Multiplier for correcting nodes
     ```

7. **Add tests**
   - File: `tests/test_scoring.py`
   - Add tests:
     ```python
     def test_superseded_node_penalized():
         """Node that has been superseded should get 0.5× score."""
         edges = {"superseded_by": {42: [{"source_id": 99}]}, "supersedes": {}}
         assert compute_supersession_adjustment(42, edges) == 0.5

     def test_superseding_node_boosted():
         """Node that supersedes another should get 1.2× score."""
         edges = {"superseded_by": {}, "supersedes": {99: [{"target_id": 42}]}}
         assert compute_supersession_adjustment(99, edges) == 1.2

     def test_neutral_node_unaffected():
         """Node with no supersession edges gets 1.0× score."""
         edges = {"superseded_by": {}, "supersedes": {}}
         assert compute_supersession_adjustment(7, edges) == 1.0
     ```

---

## Verification

- [ ] `uv run pytest tests/test_scoring.py -v -k supersession` — supersession tests pass
- [ ] New edge types `SUPERSEDES` and `CORRECTS` exist in seed ontology SQL
- [ ] Schema template also includes the new edge types
- [ ] The librarian prompt mentions temporal relationship signals (CORRECTION, UPDATE, REVERSAL)
- [ ] `uv run pytest tests/ -v` — no regressions
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

---

## Commit

`feat(temporal): add fact supersession edges and scoring adjustments for corrections`
