# Stage 3: Temporal Recency Bias

**Goal**: Make the recency signal aware of content updates (not just creation time) so that corrected/revised nodes and recently-stored episodes naturally surface above stale predecessors.
**Dependencies**: Stage 1 (dampening must be in place to prevent the old activation dominance from overshadowing recency changes)

---

## Background

The current recency formula (`scoring.py:18-24`):
```python
hours_ago = (now - created_at).total_seconds() / 3600
return 2^(-hours_ago / half_life_hours)
```

Problem: it uses `created_at`, which is set once at node creation and never changes. When a node is updated (content corrected), `updated_at` changes but recency still reflects the original creation date. A node created in January and corrected in March gets the same recency as if it were never corrected.

**Fix**: Use `max(created_at, updated_at)` as the timestamp for recency, and increase the recency weight from 0.10 to 0.15 (taking 0.05 from activation weight, which drops from 0.25 to 0.20 after dampening makes activation less dominant).

New default weights:
```
vector=0.30, text=0.20, recency=0.15, activation=0.20, importance=0.15
```

Additionally, for episodes specifically, add an **extraction-freshness bonus**: episodes that have not yet been consolidated into the graph (i.e., `consolidated = false`) get a temporary recency boost. This addresses Finding 8 from the E2E report (recently stored memories have a recall gap because they lack graph traversal bonuses).

---

## Steps

1. **Change default recall weights** in `mcp_settings.py`
   - File: `src/neocortex/mcp_settings.py`
   - Change:
     ```python
     recall_weight_recency: float = 0.15      # was 0.10
     recall_weight_activation: float = 0.20   # was 0.25
     ```
   - Add setting for unconsolidated episode boost:
     ```python
     # Bonus multiplier for unconsolidated episodes (not yet extracted into graph).
     # Compensates for lack of graph traversal bonus on fresh memories.
     recall_unconsolidated_episode_boost: float = 1.3
     ```

2. **Modify `compute_recency_score`** to accept any timestamp (not assume `created_at`)
   - File: `src/neocortex/scoring.py`, function `compute_recency_score` (lines 18-24)
   - Rename parameter for clarity:
     ```python
     def compute_recency_score(timestamp: datetime, half_life_hours: float) -> float:
         """Exponential decay score based on age. Returns value in [0, 1].

         Args:
             timestamp: The relevant timestamp — use max(created_at, updated_at)
                       for nodes, or created_at for episodes.
             half_life_hours: Time in hours for score to decay to 0.5.
         """
         now = datetime.now(UTC)
         if timestamp.tzinfo is None:
             timestamp = timestamp.replace(tzinfo=UTC)
         hours_ago = max((now - timestamp).total_seconds() / 3600.0, 0.0)
         return math.pow(2.0, -hours_ago / half_life_hours)
     ```
   - Note: The parameter rename from `created_at` to `timestamp` is a signature change. Update all call sites.

3. **Pass `max(created_at, updated_at)` for node recency**
   - File: `src/neocortex/db/adapter.py`
   - In `_recall_in_schema` (around lines 1641-1710) where node results are prepared for scoring, ensure the timestamp used for recency is `max(created_at, updated_at)`:
     ```python
     # When building the result dict for scoring:
     recency_ts = max(row["created_at"], row["updated_at"]) if row["updated_at"] else row["created_at"]
     ```
   - Ensure `updated_at` is included in the SELECT query if not already present.

4. **Include `updated_at` in recall SQL for nodes**
   - File: `src/neocortex/db/adapter.py`
   - Check the SELECT in the node recall query (around line 1650). If `updated_at` is not selected, add it:
     ```sql
     SELECT id, type_id, name, content, ..., created_at, updated_at, ...
     FROM node WHERE ...
     ```

5. **Add unconsolidated episode boost**
   - File: `src/neocortex/db/adapter.py` or `src/neocortex/scoring.py`
   - When scoring episodes in the recall path, check the `consolidated` flag.
   - If `consolidated = false`, multiply the episode's final score by `recall_unconsolidated_episode_boost`:
     ```python
     if not episode.get("consolidated", True):
         score *= settings.recall_unconsolidated_episode_boost
     ```
   - This must happen BEFORE sorting/ranking but AFTER the base hybrid score computation.
   - Note: Currently the adapter applies a 0.5× penalty for consolidated episodes (lines 1779-1780). Review whether this penalty should be adjusted or removed now that unconsolidated episodes get a boost instead.

6. **Add tests for temporal recency**
   - File: `tests/test_scoring.py`
   - Add tests:
     ```python
     def test_recency_uses_updated_timestamp():
         """Node updated recently should score higher than stale node."""
         old_ts = datetime(2026, 1, 1, tzinfo=UTC)
         recent_ts = datetime(2026, 3, 30, tzinfo=UTC)
         old_score = compute_recency_score(old_ts, half_life_hours=168)
         updated_score = compute_recency_score(recent_ts, half_life_hours=168)
         assert updated_score > old_score * 2  # Significantly higher

     def test_default_weights_sum_to_one():
         """Default recall weights should sum to 1.0."""
         s = MCPSettings()
         total = (s.recall_weight_vector + s.recall_weight_text +
                  s.recall_weight_recency + s.recall_weight_activation +
                  s.recall_weight_importance)
         assert abs(total - 1.0) < 0.001
     ```

---

## Verification

- [ ] `uv run pytest tests/test_scoring.py -v` — all tests pass, including new temporal tests
- [ ] Default weights sum to 1.0: vector(0.30) + text(0.20) + recency(0.15) + activation(0.20) + importance(0.15) = 1.00
- [ ] A node created in January but updated in March scores higher recency than a node created in January and never updated
- [ ] Unconsolidated episodes get the 1.3× boost
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

---

## Commit

`fix(scoring): use updated_at for recency, rebalance weights, boost unconsolidated episodes`
