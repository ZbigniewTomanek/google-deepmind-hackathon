# Stage 5: Fix Edge Weight Management

**Goal**: Prevent edge weight creep so scoring remains fair across frequently and infrequently accessed subgraphs.

**Dependencies**: None (independent of other stages)

**Priority**: P2

---

## Root Cause Analysis

### The reinforcement-decay asymmetry

**Reinforcement** (`adapter.py:955-971`):
- `weight = LEAST(weight + 0.05, 2.0)` — linear +0.05 per recall
- Triggers on EVERY recall that traverses the edge
- Applies to ALL edges in the 2-hop neighborhood

**Decay** (`adapter.py:973-996`, `recall.py:11-20`):
- `weight = GREATEST(weight * 0.95, 0.1)` — multiplicative 5% decay
- Triggers only 10% of recall calls (`random.random() >= 0.1`)
- Only affects edges where `last_reinforced_at < now() - 7 days`

### Why weights only go up

For a frequently-accessed edge (daily recalls):
- +0.05 on every recall → ~0.05/day minimum
- Decay never fires because `last_reinforced_at` is always recent (<7 days)
- Weight climbs: 1.0 → 1.05 → 1.10 → ... → 2.0 (ceiling)

After 20 recalls: weight = 2.0 (ceiling hit). The edge permanently dominates
spreading activation via `propagated = energy * edge_weight * decay` (`scoring.py:107`).

### The compounding effect

Higher weights → higher spreading activation bonus → higher recall scores →
more likely to be in results → more reinforcement → higher weights.
This is a positive feedback loop with no equilibrium.

### Experimental evidence (Plan 15, Stage 6)

> "Edge weight creep to 1.75+. importance=1.0 still beaten by high-activation episodes."

---

## Steps

### 5.1 Replace linear reinforcement with logarithmic diminishing returns

**File**: `src/neocortex/db/adapter.py`
**Lines**: 955-971

Change from `weight + delta` to a diminishing-returns formula:

```sql
UPDATE edge SET
    weight = LEAST(weight + $2 / (1.0 + (weight - 1.0) * 5.0), $3),
    last_reinforced_at = now()
WHERE id = ANY($1::int[])
```

This gives:
- At weight 1.0: increment = 0.05 / 1.0 = 0.05 (full delta)
- At weight 1.1: increment = 0.05 / 1.5 = 0.033
- At weight 1.2: increment = 0.05 / 2.0 = 0.025
- At weight 1.4: increment = 0.05 / 3.0 = 0.017
- At weight 1.5: practical ceiling (increments → 0)

This naturally caps weights around 1.4-1.5 without a hard ceiling change.

**Alternative (simpler)**: Just reduce the delta and ceiling:
```python
edge_reinforcement_delta: float = 0.02   # was 0.05
edge_weight_ceiling: float = 1.5          # was 2.0
```

The diminishing-returns approach is more principled (first recalls matter most,
matching real memory). Choose based on implementation preference.

### 5.2 Add bounded micro-decay during recall

**File**: `src/neocortex/tools/recall.py`
**Lines**: 185-195

After reinforcing traversed edges, apply a small decay to non-traversed edges.
This prevents the stagnation problem where active edges never enter the
stale-edge decay window.

**Scalability constraint**: A naive `UPDATE edge SET ... WHERE id != ALL(...)`
touches every edge in the schema on every recall. At 50K+ edges this is an
O(n) write per query — contradicting the plan's scalability goals.

**Solution**: Make micro-decay probabilistic (25% of recalls) and bound it
to edges not reinforced recently (last 1 hour), so only the "warm" edges
that would otherwise stagnate are touched:

```python
# Edge reinforcement — strengthen traversed edges
if traversed_edge_ids:
    await repo.reinforce_edges(agent_id, list(traversed_edge_ids), ...)

# Micro-decay — probabilistic, bounded to recently-active edges only
if random.random() < 0.25:
    await repo.micro_decay_edges(
        agent_id,
        exclude_ids=list(traversed_edge_ids),
        factor=0.998,  # 0.2% decay per application
        floor=settings.edge_weight_floor,
        recently_reinforced_hours=1.0,  # Only edges reinforced in last hour
    )
```

### 5.3 Add `micro_decay_edges` to protocol and implementations

**File**: `src/neocortex/db/protocol.py`

```python
async def micro_decay_edges(
    self, agent_id: str, exclude_ids: list[int],
    factor: float = 0.998, floor: float = 0.1,
    recently_reinforced_hours: float = 1.0,
) -> None:
    """Apply small multiplicative decay to recently-active edges (excluding given IDs).

    Targets edges reinforced within `recently_reinforced_hours` that are NOT in
    `exclude_ids`. This prevents weight stagnation without touching the entire table.
    Called probabilistically (~25% of recalls).
    """
```

**File**: `src/neocortex/db/adapter.py`

```sql
UPDATE edge SET weight = GREATEST(weight * $1, $2)
WHERE id != ALL($3::int[])
  AND weight > $2
  AND last_reinforced_at > now() - make_interval(hours => $4)
```

The `last_reinforced_at` filter bounds the update set to edges that were
recently active (and would otherwise never enter the stale-edge decay window).
Cold edges are already handled by `decay_stale_edges` (step 5.4).

**File**: `src/neocortex/db/mock.py` — equivalent in-memory implementation.

### 5.4 Reduce the stale-edge decay window

**File**: `src/neocortex/tools/recall.py`
**Lines**: 11-20

Change the stale-edge decay parameters:
- `older_than_hours`: 168.0 (7 days) → 48.0 (2 days)
- Increase probability: 10% → 25% of recalls

```python
async def _maybe_decay_edges(repo, agent_id, settings, *, force=False):
    if not force and random.random() >= 0.25:  # was 0.1
        return
    await repo.decay_stale_edges(
        agent_id,
        older_than_hours=48.0,   # was 168.0
        decay_factor=0.95,
        floor=settings.edge_weight_floor,
    )
```

### 5.5 Update settings with new defaults

**File**: `src/neocortex/mcp_settings.py`
**Lines**: 76-79

```python
# Edge reinforcement
edge_reinforcement_delta: float = 0.05      # kept for logarithmic formula
edge_weight_floor: float = 0.1
edge_weight_ceiling: float = 1.5            # was 2.0
edge_micro_decay_factor: float = 0.998      # NEW: per-recall decay for non-traversed
```

### 5.6 Add tests

Test scenarios:
1. **Diminishing returns**: reinforce same edge 20 times, verify weight < 1.5
2. **Micro-decay**: verify non-traversed edges decay each recall
3. **Equilibrium**: after many reinforce+decay cycles, weight converges (doesn't grow unbounded)
4. **Floor respected**: decayed weights don't go below 0.1
5. **Stale decay**: edges untouched for 48h get 5% decay

---

## Verification

```bash
# Run weight management tests
uv run pytest tests/test_weight_management.py -v

# Full suite
uv run pytest tests/ -v
```

- [ ] Edge weight after 20 reinforcements < 1.5 (was 2.0)
- [ ] Non-traversed edges decay on each recall
- [ ] Stale-edge decay fires more frequently (25%, 48h window)
- [ ] Weight floor (0.1) respected
- [ ] Existing tests pass

---

## Commit

```
fix(scoring): bounded edge reinforcement with continuous micro-decay

Replace linear weight reinforcement with logarithmic diminishing returns.
Add per-recall micro-decay for non-traversed edges. Reduce stale-edge
decay window from 7 days to 2 days. Prevents weight creep that caused
frequently-accessed subgraphs to dominate scoring.

Closes: Plan 15 Issue 4
```
