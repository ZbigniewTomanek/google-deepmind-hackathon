# Stage 4: Short-Term Recency Boost

**Goal**: Add a separate short-term recency boost for episodes created within the last N hours so that intra-session context naturally surfaces above older memories, without disrupting the existing 7-day exponential decay curve for longer-term recall.
**Dependencies**: None for the scoring helper. Adapter wiring can be done independently of session work, but tests that combine STM with neighbor expansion depend on Stage 3.

---

## Background

MemMachine's Short-Term Memory (STM) design ensures that the N most recent episodes are always available without retrieval — agents get natural recency bias for immediate context. NeoCortex doesn't have an STM layer, but it can approximate this effect by boosting the hybrid score of very recent episodes.

The current recency component uses a single exponential decay with a 168-hour (7-day) half-life. A 2-hour-old episode decays to `2^(-2/168) ≈ 0.992` — nearly indistinguishable from a brand-new one. A 24-hour-old episode scores `2^(-24/168) ≈ 0.906`. The decay only becomes meaningful at the day-to-week scale.

The fix: add a secondary "short-term boost" that gives a multiplicative bonus to episodes younger than `episode_stm_window_hours` (default 2 hours). This boost decays to 1.0 (no effect) at the window boundary, providing a smooth transition. The boost applies only to episodes, not to nodes, preserving the existing scoring behavior for the knowledge graph.

---

## Steps

### 1. Add STM boost settings to `MCPSettings`

File: `src/neocortex/mcp_settings.py`

In the recall settings block (around lines 52–104), add:

```python
episode_stm_window_hours: float = 2.0   # episodes younger than this get STM boost
episode_stm_boost_factor: float = 1.5   # peak multiplier for brand-new episodes
```

The `episode_stm_boost_factor` is applied to an episode aged 0 hours; it decays linearly to 1.0 at `episode_stm_window_hours`. Outside the window, no boost is applied (factor = 1.0).

### 2. Add `compute_stm_boost()` function to scoring.py

File: `src/neocortex/scoring.py`

Add after the existing `compute_recency_score()` function (around line 30):

```python
def compute_stm_boost(
    hours_ago: float,
    stm_window_hours: float,
    boost_factor: float,
) -> float:
    """Return a multiplicative boost for episodes within the STM window.

    Linear decay from `boost_factor` at age=0 to 1.0 at age=stm_window_hours.
    Returns 1.0 (no boost) for episodes older than the window.

    Args:
        hours_ago: Age of the episode in hours.
        stm_window_hours: Window boundary in hours. Episodes older than this get 1.0.
        boost_factor: Peak multiplier for brand-new (0-hour-old) episodes. Must be >= 1.0.

    Returns:
        Boost multiplier >= 1.0.
    """
    if hours_ago >= stm_window_hours or stm_window_hours <= 0 or boost_factor <= 1.0:
        return 1.0
    fraction_remaining = 1.0 - (hours_ago / stm_window_hours)
    return 1.0 + (boost_factor - 1.0) * fraction_remaining
```

### 3. Apply STM boost in `_recall_in_schema`

File: `src/neocortex/db/adapter.py`

In the episode scoring section of `_recall_in_schema` (around lines 2132–2241), after `compute_hybrid_score()` is called for an episode, apply the STM boost:

```python
from datetime import timezone

# ... existing scoring code that produces `base_score` for an episode ...

hours_ago = (
    datetime.now(timezone.utc) - ep["created_at"]
).total_seconds() / 3600.0

stm_multiplier = compute_stm_boost(
    hours_ago=hours_ago,
    stm_window_hours=self._settings.episode_stm_window_hours,
    boost_factor=self._settings.episode_stm_boost_factor,
)
score = score * stm_multiplier
```

Import `compute_stm_boost` at the top of the file where the other scoring imports live.

Apply the same setting names consistently everywhere. The canonical names are:

- `episode_stm_window_hours`
- `episode_stm_boost_factor`

Do not use `episode_stm_boost`.

### 4. Extend existing recency weight documentation in settings

File: `src/neocortex/mcp_settings.py`

Update the docstring or comment on `recency_weight` to note: "For episodes, a separate short-term boost (`episode_stm_boost_factor`) is applied multiplicatively on top of the recency component when the episode is within `episode_stm_window_hours`. This is independent of recency_weight."

---

## Verification

- [ ] `uv run pytest tests/ -v` passes
- [ ] Unit test for `compute_stm_boost`:
  - `compute_stm_boost(0.0, 2.0, 1.5)` → `1.5` (brand-new)
  - `compute_stm_boost(1.0, 2.0, 1.5)` → `1.25` (halfway through window)
  - `compute_stm_boost(2.0, 2.0, 1.5)` → `1.0` (at boundary)
  - `compute_stm_boost(5.0, 2.0, 1.5)` → `1.0` (outside window)
  - `compute_stm_boost(0.0, 0.0, 1.5)` → `1.0` (window disabled)
- [ ] Integration test: ingest two episodes with same query-matching content, one "now" and one 24 hours ago (set `created_at` directly in test DB). Recall the query and assert the recent episode ranks above the older one.
- [ ] Confirm STM boost does NOT apply to graph nodes — only episodes.
- [ ] Confirm disabling `episode_stm_boost_factor = 1.0` (or `episode_stm_window_hours = 0`) has no effect on scores.
- [ ] Confirm `InMemoryRepository.recall` either mirrors the STM boost or documents that mock recall intentionally uses simplified scoring. If tests assert STM behavior, run them against the implementation that actually applies the boost.

---

## Commit

`feat(scoring): add short-term recency boost for intra-session episode prioritization`
