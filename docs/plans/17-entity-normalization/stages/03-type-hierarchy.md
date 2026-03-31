# Stage 3: Semantic Type Hierarchy

**Goal**: Replace the prefix heuristic in `_types_are_merge_safe()` with a configurable semantic type grouping system, so sibling types like Tool/Project and Technology/Framework correctly merge.

**Dependencies**: Stage 1 (normalization utility, for `normalize_node_type`)

---

## Rationale

The current `_types_are_merge_safe()` at `adapter.py:38-56` uses a prefix heuristic:
`e.startswith(r) or r.startswith(e)`. This catches hierarchy patterns (Person/PersonRole)
but fails for sibling types that share a semantic domain:

| Pair | Prefix Match? | Should Merge? | Why |
|------|--------------|---------------|-----|
| Tool / Project | No | Yes | Same software entity, different LLM type choice |
| Technology / Framework | No | Yes | Same software entity |
| Person / PersonRole | Yes | Yes | Hierarchy (prefix works) |
| Drug / Neurotransmitter | No | No | Legitimate homonym |
| Person / Organization | No | No | Legitimate homonym |

The fix is to define **merge-safe type groups** — sets of types where any pair within the
same group is considered merge-safe. This is more expressive than prefix matching and
explicitly controllable.

---

## Steps

### Step 1: Define type groups in `src/neocortex/db/adapter.py`

Replace the prefix heuristic with a group-based approach:

```python
# Types within the same group are considered merge-safe (likely type drift, not homonyms)
_MERGE_SAFE_TYPE_GROUPS: list[frozenset[str]] = [
    # Software entities — LLM often oscillates between these
    # NOTE: Service, Application, Platform excluded — they are semantically
    # distinct enough that same-name entities may legitimately differ.
    frozenset({"Tool", "Project", "Software", "SoftwareTool", "Framework", "Library"}),
    # People — role vs person type drift
    frozenset({"Person", "PersonRole", "TeamMember", "Employee",
               "Researcher", "Engineer", "Scientist"}),
    # Organizations
    frozenset({"Organization", "Company", "Team", "Group", "Department"}),
    # Concepts / Topics
    frozenset({"Concept", "Topic", "Subject", "Theme", "Idea"}),
    # Technologies (specific)
    frozenset({"Technology", "Protocol", "Standard", "Specification"}),
    # Documents / Resources
    frozenset({"Document", "Resource", "Article", "Paper", "Report"}),
    # Events / Milestones
    # NOTE: Meeting, Sprint, Deadline excluded — a meeting ABOUT a sprint
    # is not the sprint. These have specific semantics worth preserving.
    frozenset({"Event", "Milestone"}),
    # Metrics / Measurements
    frozenset({"Metric", "Measurement", "Score", "KPI", "Statistic"}),
]

# Pre-compute a lookup: type_name_lower -> group_index for O(1) group check
_TYPE_TO_GROUP: dict[str, int] = {}
for i, group in enumerate(_MERGE_SAFE_TYPE_GROUPS):
    for t in group:
        _TYPE_TO_GROUP[t.lower()] = i
```

### Step 2: Rewrite `_types_are_merge_safe()`

```python
def _types_are_merge_safe(existing: str | None, requested: str | None) -> bool:
    """Return True if two type names likely refer to the same entity
    (LLM type drift) rather than a legitimate homonym.

    Uses three checks in order:
    1. Exact match → True
    2. Known homonym pairs → False (never merge)
    3. Same merge-safe group → True
    4. Prefix heuristic (backward compat) → True
    5. Default → False (conservative)
    """
    if not existing or not requested:
        return False
    if existing == requested:
        return True

    # Known homonym pairs — never merge
    pair = frozenset({existing, requested})
    if pair in _HOMONYM_TYPE_GROUPS:
        return False

    # Same merge-safe group → merge
    e_lower, r_lower = existing.lower(), requested.lower()
    e_group = _TYPE_TO_GROUP.get(e_lower)
    r_group = _TYPE_TO_GROUP.get(r_lower)
    if e_group is not None and r_group is not None and e_group == r_group:
        return True

    # Backward compat: prefix heuristic for types not in any group
    if e_lower.startswith(r_lower) or r_lower.startswith(e_lower):
        return True

    return False
```

### Step 3: Keep homonym blacklist, add new pairs

Review current homonym groups and expand:

```python
_HOMONYM_TYPE_GROUPS: frozenset[frozenset[str]] = frozenset({
    frozenset({"Drug", "Neurotransmitter"}),
    frozenset({"Person", "Organization"}),
    frozenset({"Language", "Country"}),
    frozenset({"Metric", "MetricUnit"}), # a metric and its unit are different (prefix guard)
})
```

**Important**: Homonym blacklist takes precedence over merge-safe groups. If a pair
appears in both, it is NOT merged. This is the safety valve.

### Step 4: Update tests in `tests/mcp/test_dedup_safety.py`

Expand the type hierarchy test cases:

```python
# New merge-safe cases (previously would create separate nodes)
assert _types_are_merge_safe("Tool", "Project") is True      # same group
assert _types_are_merge_safe("Tool", "Software") is True     # same group
assert _types_are_merge_safe("Framework", "Library") is True  # same group
assert _types_are_merge_safe("Person", "TeamMember") is True  # same group
assert _types_are_merge_safe("Team", "Organization") is True  # same group

# Still NOT merged (homonym blacklist overrides)
assert _types_are_merge_safe("Person", "Organization") is False
assert _types_are_merge_safe("Drug", "Neurotransmitter") is False

# Prefix heuristic still works for unlisted types
assert _types_are_merge_safe("CustomType", "CustomTypeExtended") is True

# Types excluded from groups — too distinct to auto-merge
assert _types_are_merge_safe("Service", "Application") is False  # not in software group
assert _types_are_merge_safe("Meeting", "Sprint") is False       # not in events group
assert _types_are_merge_safe("Platform", "Library") is False     # Platform excluded

# Unknown types default to conservative (no merge)
assert _types_are_merge_safe("Aardvark", "Zebra") is False
```

### Step 5: Update `src/neocortex/db/mock.py`

The mock adapter's `upsert_node()` also calls `_types_are_merge_safe()`.
Since it's a module-level function in `adapter.py`, the mock imports it.
Verify the import path works and add mock-specific tests if the mock has
its own inline type check.

---

## Verification

```bash
# Run dedup safety tests
uv run pytest tests/mcp/test_dedup_safety.py -v

# Run full test suite to check for regressions
uv run pytest tests/ -v --timeout=60

# Spot-check: "DataForge" as Tool should merge with "DataForge" as Project
# (This will be validated end-to-end in Stage 6)
```

Check:
- [ ] `_types_are_merge_safe("Tool", "Project")` → True
- [ ] `_types_are_merge_safe("Person", "Organization")` → False (homonym override)
- [ ] Prefix heuristic still works for types not in any group
- [ ] Pre-computed `_TYPE_TO_GROUP` lookup is correct
- [ ] All existing tests pass (no regressions)
- [ ] Mock adapter uses the same function

---

## Commit

```
feat(dedup): replace prefix heuristic with semantic type hierarchy

Introduces _MERGE_SAFE_TYPE_GROUPS — configurable sets of types where
any pair is considered merge-safe (likely LLM type drift). Solves the
DataForge Tool/Project split. Prefix heuristic retained as fallback
for types not in any defined group.
```
