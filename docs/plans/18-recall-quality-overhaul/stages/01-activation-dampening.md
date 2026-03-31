# Stage 1: Activation Dampening

**Goal**: Replace the unbounded ACT-R activation formula with a sublinear-dampened variant that prevents gravity wells while preserving cognitive plausibility.
**Dependencies**: None

---

## Background

The current ACT-R base-level learning formula (`scoring.py:27-47`):
```
B_i = ln(access_count + 1) − decay_rate × ln(hours_since + 1)
activation = sigmoid(B_i)
```

`ln(access_count + 1)` grows without bound. After 9 recall queries, Episode #24's activation climbed from 0.49 → 0.91. The sigmoid maps this to [0,1] but asymptotes slowly — by the time access_count reaches ~20, activation is >0.95 regardless of age.

**Fix**: Replace `ln(access_count + 1)` with `ln(access_count^α + 1)` where `α < 1` (default 0.5). This is equivalent to `ln(√access_count + 1)` — sublinear growth that compresses high access counts toward a lower ceiling.

| access_count | Current ln(n+1) | Dampened ln(√n + 1) |
|-------------|-----------------|---------------------|
| 1  | 0.69 | 0.69 |
| 5  | 1.79 | 1.18 |
| 10 | 2.40 | 1.44 |
| 20 | 3.04 | 1.64 |
| 50 | 3.93 | 1.97 |

Additionally, introduce a **per-query access increment cap**: when a single recall query returns multiple results, limit how many nodes/episodes get their `access_count` incremented (default: top 3). This prevents a single broad query from boosting many items.

---

## Steps

1. **Add new settings** to `mcp_settings.py`
   - File: `src/neocortex/mcp_settings.py`
   - Add after `activation_decay_rate` (around line 65):
     ```python
     # Sublinear dampening exponent for access_count in ACT-R formula.
     # 1.0 = original (unbounded log growth), 0.5 = square-root dampening.
     activation_access_exponent: float = 0.5

     # Max nodes/episodes whose access_count is incremented per recall query.
     # Prevents broad queries from boosting many items simultaneously.
     recall_access_increment_limit: int = 3
     ```

2. **Modify `compute_base_activation`** in `scoring.py`
   - File: `src/neocortex/scoring.py`, function `compute_base_activation` (lines 27-47)
   - Change the frequency term from `ln(access_count + 1)` to `ln(access_count^α + 1)`:
     ```python
     def compute_base_activation(
         access_count: int,
         last_accessed_at: datetime,
         decay_rate: float = 0.5,
         access_exponent: float = 0.5,  # NEW parameter
     ) -> float:
         ...
         # Dampened frequency: sublinear growth prevents gravity wells
         dampened_count = math.pow(max(access_count, 0), access_exponent)
         frequency = math.log(dampened_count + 1)
         recency_penalty = decay_rate * math.log(hours_since + 1)
         base_level = frequency - recency_penalty
         return 1.0 / (1.0 + math.exp(-base_level))  # sigmoid
     ```

3. **Thread `access_exponent` through the adapter's inline scoring**
   - File: `src/neocortex/db/adapter.py`, method `_recall_in_schema` (lines ~1717-1798)
   - Note: `compute_hybrid_score` does NOT call `compute_base_activation` — they are independent functions. Activation is pre-computed and passed into `compute_hybrid_score` as the `activation` parameter. Scoring is done **inline** in `_recall_in_schema`, not in separate `_score_and_rank_*` functions (those don't exist).
   - Find all calls to `compute_base_activation` in `_recall_in_schema` (there are multiple — for nodes and episodes) and add the `access_exponent` kwarg. Settings are available as `self._settings`.

4. **Pass `access_exponent` from settings at each call site**
   - File: `src/neocortex/db/adapter.py`, method `_recall_in_schema` (lines ~1717-1798)
   - Scoring is done inline in this method — `tools/recall.py` calls `repo.recall()` which delegates to the adapter. Find each `compute_base_activation(...)` call and add the new parameter:
     ```python
     activation = compute_base_activation(
         row["access_count"],
         row["last_accessed_at"],
         decay_rate=self._settings.activation_decay_rate,
         access_exponent=self._settings.activation_access_exponent,  # NEW
     )
     ```
   - There are multiple calls (for nodes and episodes). Update all of them.

5. **Cap per-query access increments** in `db/adapter.py`
   - File: `src/neocortex/db/adapter.py`
   - In `record_node_access` and `record_episode_access` (around lines 1250-1276):
     - Add a `limit` parameter (default from `recall_access_increment_limit`)
     - Only update `access_count` for the first N node/episode IDs
     ```python
     async def record_node_access(self, node_ids: list[int], ..., limit: int = 3) -> None:
         ids_to_update = node_ids[:limit]
         await conn.execute(
             "UPDATE node SET access_count = access_count + 1, last_accessed_at = now() "
             "WHERE id = ANY($1::int[])",
             ids_to_update,
         )
     ```
   - Similarly for `record_episode_access`.
   - At the call sites (inside `recall()` or `_recall_in_schema`), pass the setting:
     ```python
     await self.record_node_access(
         agent_id, node_ids, limit=self._settings.recall_access_increment_limit
     )
     ```

6. **Update existing tests** in `test_scoring.py`
   - File: `tests/test_scoring.py`
   - Update any tests that call `compute_base_activation` to pass the new parameter.
   - Add new tests:
     ```python
     def test_activation_dampening_reduces_high_access():
         """access_count=50 with dampening should score lower than without."""
         undampened = compute_base_activation(50, now, decay_rate=0.5, access_exponent=1.0)
         dampened = compute_base_activation(50, now, decay_rate=0.5, access_exponent=0.5)
         assert dampened < undampened
         assert dampened < 0.85  # Should not approach ceiling

     def test_activation_dampening_preserves_low_access():
         """access_count=1 should score similarly with and without dampening."""
         undampened = compute_base_activation(1, now, decay_rate=0.5, access_exponent=1.0)
         dampened = compute_base_activation(1, now, decay_rate=0.5, access_exponent=0.5)
         assert abs(undampened - dampened) < 0.05  # Minimal difference at low counts

     def test_activation_gravity_well_prevention():
         """After 20 accesses, activation should stay below 0.80."""
         score = compute_base_activation(20, now, decay_rate=0.5, access_exponent=0.5)
         assert score < 0.80
     ```

---

## Verification

- [ ] `uv run pytest tests/test_scoring.py -v` — all tests pass including new dampening tests
- [ ] `compute_base_activation(50, now, 0.5, 0.5)` returns < 0.85 (vs ~0.98 before)
- [ ] `compute_base_activation(1, now, 0.5, 0.5)` returns within 0.05 of the undampened value
- [ ] Settings `activation_access_exponent` and `recall_access_increment_limit` load correctly from env vars
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

---

## Commit

`fix(scoring): add sublinear activation dampening to prevent recall gravity wells`
