# Stage 2: MMR Diversity Reranking

**Goal**: Add Maximal Marginal Relevance (MMR) postprocessing to recall results so that no single topic monopolizes the result set, even when activation scores are similar.
**Dependencies**: Stage 1 (activation dampening reduces the gap, MMR addresses remaining overlap)

---

## Background

Even with dampened activation (Stage 1), multiple nodes about the same topic can dominate recall results. For example, if 5 nodes all relate to "Fellegi-Sunter model", they may all score highly and push out unrelated but relevant results about debugging sessions or security bugs.

**MMR** (Carbonell & Goldberg, 1998) reranks by iteratively selecting the result that maximizes:
```
MMR(d) = λ × relevance(d) − (1 − λ) × max_similarity(d, already_selected)
```
Where:
- `λ` = 1.0 → pure relevance (no diversity)
- `λ` = 0.5 → balanced relevance + diversity
- `λ` = 0.0 → pure diversity (maximum spread)

We use **embedding cosine similarity** for the `max_similarity` term since every node and episode already has an embedding vector.

Default `λ = 0.7` (bias toward relevance but with meaningful diversity pressure).

---

## Steps

1. **Add MMR settings** to `mcp_settings.py`
   - File: `src/neocortex/mcp_settings.py`
   - Add after the recall weight settings:
     ```python
     # MMR diversity reranking
     # Lambda: 1.0 = pure relevance, 0.0 = pure diversity, default 0.7
     recall_mmr_lambda: float = 0.7
     # Enable/disable MMR postprocessing (disable to compare A/B)
     recall_mmr_enabled: bool = True
     ```

2. **Implement MMR reranking function** in `scoring.py`
   - File: `src/neocortex/scoring.py`
   - Add a new function after the existing scoring functions:
     ```python
     def mmr_rerank(
         results: list[dict],
         lambda_param: float = 0.7,
         score_key: str = "score",
         embedding_key: str = "embedding",
     ) -> list[dict]:
         """Maximal Marginal Relevance reranking for diversity.

         Iteratively selects items that balance high relevance with
         low similarity to already-selected items.

         Args:
             results: Scored recall results, each with a score and embedding.
             lambda_param: Trade-off between relevance (1.0) and diversity (0.0).
             score_key: Key for relevance score in result dicts.
             embedding_key: Key for embedding vector in result dicts.

         Returns:
             Reranked list in MMR order.
         """
         if len(results) <= 1 or lambda_param >= 1.0:
             return results

         # Filter to items that have embeddings (can't compute similarity without them)
         with_emb = [r for r in results if r.get(embedding_key) is not None]
         without_emb = [r for r in results if r.get(embedding_key) is None]

         if not with_emb:
             return results

         selected: list[dict] = []
         candidates = list(with_emb)

         # First pick: highest relevance score
         candidates.sort(key=lambda r: r[score_key], reverse=True)
         selected.append(candidates.pop(0))

         while candidates:
             best_mmr = -float("inf")
             best_idx = 0
             for i, cand in enumerate(candidates):
                 relevance = cand[score_key]
                 # Max cosine similarity to any already-selected item
                 max_sim = max(
                     _cosine_similarity(cand[embedding_key], s[embedding_key])
                     for s in selected
                 )
                 mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
                 if mmr_score > best_mmr:
                     best_mmr = mmr_score
                     best_idx = i
             selected.append(candidates.pop(best_idx))

         # Append items without embeddings at the end (no diversity signal available)
         return selected + without_emb


     def _cosine_similarity(a: list[float], b: list[float]) -> float:
         """Cosine similarity between two vectors. Returns value in [-1, 1]."""
         dot = sum(x * y for x, y in zip(a, b))
         norm_a = math.sqrt(sum(x * x for x in a))
         norm_b = math.sqrt(sum(x * x for x in b))
         if norm_a == 0 or norm_b == 0:
             return 0.0
         return dot / (norm_a * norm_b)
     ```

3. **Integrate MMR into the adapter's recall pipeline**
   - File: `src/neocortex/db/adapter.py`, method `_recall_in_schema` (lines ~1717-1798)
   - Scoring and result building happen inline in this method — `tools/recall.py` calls `repo.recall()` which delegates here. After scoring all results and before sorting/truncating, apply MMR:
     ```python
     from neocortex.scoring import mmr_rerank

     # After computing hybrid scores for all results, before sorting:
     if self._settings.recall_mmr_enabled:
         result_dicts = mmr_rerank(
             result_dicts,
             lambda_param=self._settings.recall_mmr_lambda,
         )
     ```
   - The result dicts at this stage must include the `"embedding"` key (see Step 4).
   - After MMR reranking, strip embeddings before building `RecallItem` objects:
     ```python
     for r in result_dicts:
         r.pop("embedding", None)
     ```

4. **Fetch raw embedding vectors from SQL for MMR**
   - File: `src/neocortex/db/adapter.py`, method `_recall_in_schema`
   - Currently, vector similarity is computed entirely in PostgreSQL via pgvector's `<=>` operator — the raw embedding vector is **never fetched into Python**. MMR needs the actual vectors for pairwise cosine similarity.
   - In the node recall SQL query (around lines 1641-1659), add `embedding::float[]` to the SELECT:
     ```sql
     SELECT id, name, content, ..., created_at,
            embedding::float[] as embedding_vec,  -- ADD for MMR
            1 - (embedding <=> $1) as vector_sim
     FROM node WHERE ...
     ```
   - Similarly for the episode recall SQL query (around lines 1662-1679).
   - When building result dicts for scoring, include the embedding:
     ```python
     result["embedding"] = row["embedding_vec"]  # Keep for MMR; stripped after reranking
     ```
   - **Performance note**: Fetching 768-dim float vectors for ~50-100 candidates adds ~300KB to query results. This is acceptable for recall-time latency. The pure-Python `_cosine_similarity` in MMR is O(n² × d); if latency becomes an issue, limit MMR to the top 30 candidates by initial score before reranking.

5. **Add tests for MMR reranking**
   - File: `tests/test_scoring.py`
   - Add tests:
     ```python
     def test_mmr_rerank_promotes_diversity():
         """Three similar items + one outlier: outlier should rank higher after MMR."""
         similar_emb = [1.0, 0.0, 0.0]  # Three items with identical embeddings
         outlier_emb = [0.0, 1.0, 0.0]  # One item with orthogonal embedding
         results = [
             {"score": 0.9, "embedding": similar_emb, "name": "A"},
             {"score": 0.85, "embedding": similar_emb, "name": "B"},
             {"score": 0.80, "embedding": similar_emb, "name": "C"},
             {"score": 0.75, "embedding": outlier_emb, "name": "D"},
         ]
         reranked = mmr_rerank(results, lambda_param=0.7)
         # D (outlier) should be promoted above B or C
         names = [r["name"] for r in reranked]
         assert names[0] == "A"  # Highest score still first
         assert names.index("D") < names.index("C")  # Outlier promoted

     def test_mmr_lambda_1_preserves_order():
         """Lambda=1.0 should return original relevance order."""
         results = [
             {"score": 0.9, "embedding": [1, 0], "name": "A"},
             {"score": 0.5, "embedding": [0, 1], "name": "B"},
         ]
         reranked = mmr_rerank(results, lambda_param=1.0)
         assert [r["name"] for r in reranked] == ["A", "B"]

     def test_mmr_handles_missing_embeddings():
         """Items without embeddings appended at end."""
         results = [
             {"score": 0.9, "embedding": [1, 0], "name": "A"},
             {"score": 0.8, "embedding": None, "name": "B"},
             {"score": 0.7, "embedding": [0, 1], "name": "C"},
         ]
         reranked = mmr_rerank(results, lambda_param=0.7)
         assert reranked[-1]["name"] == "B"  # No embedding → last

     def test_mmr_single_result_passthrough():
         """Single result is returned as-is."""
         results = [{"score": 0.9, "embedding": [1, 0], "name": "A"}]
         assert mmr_rerank(results) == results
     ```

---

## Verification

- [ ] `uv run pytest tests/test_scoring.py -v -k mmr` — all MMR tests pass
- [ ] `uv run pytest tests/test_scoring.py -v` — all existing scoring tests still pass
- [ ] With 4 similar-embedding results + 1 outlier, MMR promotes the outlier above at least one similar result
- [ ] `recall_mmr_enabled=false` bypasses reranking (results match pre-MMR order)
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

---

## Commit

`feat(scoring): add MMR diversity reranking to prevent recall result monopolization`
