# Stage 7: Temporal Edge Creation Reinforcement

**Goal**: Make the librarian reliably create SUPERSEDES/CORRECTS edges when correction episodes are extracted, closing the behavioral gap found in Stage 6.
**Dependencies**: Stages 3-4 (temporal schema + prompts), Stage 6 (smoke test results)

---

## Background

Stage 6 smoke test showed that temporal extraction is **half-working**:

- **Working**: The extractor detects CORRECTION markers and creates versioned entity
  names ("Metaphone3 Hybrid Strategy" vs "Uniform 4-char Metaphone3 Strategy").
  The `supersedes` field is populated and surfaced in the librarian's context
  injection as `[SUPERSEDES=..., signal=...]`.

- **Not working**: The librarian creates the new versioned node but does NOT call
  `create_or_update_edge` to create the temporal edge. It stops after node creation.

### Root Cause Analysis

The current prompt at `agents.py:331-346` tells the librarian what to do but has
several prompt-engineering weaknesses that likely cause the LLM to skip the edge
creation step:

1. **Buried instruction**: The temporal section is one of many sections in a long
   system prompt. The librarian processes many entities and the temporal workflow
   competes for attention with the general "check for existing entities" and
   "prefer updating existing nodes" rules (lines 350-352), which directly
   contradict the "DO NOT merge" directive.

2. **No worked example**: The prompt describes the abstract workflow but provides
   no concrete tool-call example showing the exact sequence:
   `create_or_update_node(name="X Hybrid Strategy", ...)` then
   `create_or_update_edge(source_name="X Hybrid Strategy", target_name="X", edge_type="SUPERSEDES")`.
   LLMs follow examples more reliably than abstract instructions.

3. **Context injection lacks call-to-action**: The `[SUPERSEDES=old_name, signal=CORRECTS]`
   annotation on entities (line 904-906) is informational. It should include an
   explicit imperative: "YOU MUST create a {signal} edge from this entity to {old_name}".

4. **Contradictory rules**: Lines 350-352 say "Prefer updating existing nodes over
   creating duplicates" and "ALWAYS check for existing entities before creating new ones."
   For temporal corrections, these are exactly the wrong behavior. The MANDATORY
   section says not to merge, but the Rules section reinforces merging. The LLM
   resolves the conflict by following the simpler, more general rule.

---

## Steps

### 1. Add concrete few-shot example to librarian temporal section

**File**: `src/neocortex/extraction/agents.py` (lines 331-346)

Replace the current "## Temporal Corrections (MANDATORY)" section with an
expanded version that includes a worked example with exact tool calls:

```python
"## Temporal Corrections (MANDATORY)",
"When an extracted entity has `supersedes` set (non-null), follow this",
"EXACT sequence — do NOT skip any step:",
"",
"  STEP 1: create_or_update_node with the NEW versioned name.",
"  STEP 2: create_or_update_edge with:",
"          source_name = <new versioned entity name>",
"          target_name = <supersedes value (old entity name)>",
"          edge_type   = <temporal_signal value: 'CORRECTS' or 'SUPERSEDES'>",
"  STEP 3: Report both actions in your CurationSummary.",
"",
"### Worked Example",
"",
"Given entity: Metaphone3 Hybrid Strategy [Algorithm]",
"  supersedes='Metaphone3', temporal_signal='SUPERSEDES'",
"",
"You must make these two tool calls:",
"",
"  1. create_or_update_node(",
"       name='Metaphone3 Hybrid Strategy',",
"       type_name='Algorithm',",
"       content='Updated strategy using 8-char codes for Latin...',",
"     )",
"  2. create_or_update_edge(",
"       source_name='Metaphone3 Hybrid Strategy',",
"       target_name='Metaphone3',",
"       edge_type='SUPERSEDES',",
"     )",
"",
"If you skip step 2, the temporal signal is permanently lost.",
"There is NO other mechanism to recover it.",
"",
```

### 2. Fix contradictory rules in the Rules section

**File**: `src/neocortex/extraction/agents.py` (lines 348-355)

Add a temporal exception to the "prefer updating" rule so it doesn't override
the temporal workflow:

```python
"## Rules",
"- ALWAYS provide comprehensive content when creating/updating nodes.",
"- ALWAYS check for existing entities before creating new ones.",
"- Prefer updating existing nodes over creating duplicates",
"  UNLESS the entity has `supersedes` set — then create a NEW node (see Temporal Corrections above).",
"- Normalize names to canonical form (proper casing, full names).",
"- When in doubt about type assignment, match the existing node's type.",
```

### 3. Make context injection imperative, not informational

**File**: `src/neocortex/extraction/agents.py` (lines 903-907)

Change `_format_entity` to include an explicit action directive:

```python
def _format_entity(e: ExtractedEntity) -> str:
    base = f"- {e.name} [{e.type_name}]: {e.description or 'no description'}"
    if e.supersedes:
        base += (
            f"\n  ^^^ ACTION REQUIRED: Create this as a NEW node, then call "
            f"create_or_update_edge(source_name='{e.name}', "
            f"target_name='{e.supersedes}', edge_type='{e.temporal_signal or 'SUPERSEDES'}')"
        )
    return base
```

This puts the exact tool call in front of the LLM at the point where it processes
each entity, not buried in the system prompt.

### 4. Add a post-curation temporal edge audit

**File**: `src/neocortex/extraction/pipeline.py`

After the librarian finishes (around line 180-190, after `curation_complete` log),
add a check: for each `ExtractedEntity` with `supersedes` set, verify that a
SUPERSEDES or CORRECTS edge was actually created. If not, create it programmatically
as a fallback.

This is the belt-and-suspenders approach: prompt engineering is the primary fix,
but structured enforcement catches any remaining LLM failures.

```python
# After librarian completes, enforce temporal edges
for entity in extraction_result.output.entities:
    if entity.supersedes and entity.temporal_signal:
        edge_type = entity.temporal_signal  # 'CORRECTS' or 'SUPERSEDES'
        # Check if the edge already exists
        existing = await repo.find_edges(
            source_name=entity.name,
            target_name=entity.supersedes,
            edge_type=edge_type,
            schema_name=target_schema or personal_schema,
        )
        if not existing:
            logger.warning(
                "temporal_edge_missing — creating programmatically",
                source=entity.name,
                target=entity.supersedes,
                edge_type=edge_type,
            )
            await repo.upsert_edge(
                source_name=entity.name,
                target_name=entity.supersedes,
                edge_type=edge_type,
                schema_name=target_schema or personal_schema,
                agent_id=agent_id,
            )
```

**Note**: The exact API for `find_edges` / `upsert_edge` will need to match the
`MemoryRepository` protocol. Check `db/protocol.py` and `db/adapter.py` for the
actual signatures. The concept is: query for the edge, create if missing.

---

## Verification

```bash
# All existing tests pass
uv run pytest tests/ -v -x

# Prompt changes are present
grep -q "Worked Example" src/neocortex/extraction/agents.py && echo "OK: few-shot example" || echo "FAIL"
grep -q "ACTION REQUIRED" src/neocortex/extraction/agents.py && echo "OK: imperative context" || echo "FAIL"
grep -q "UNLESS the entity has" src/neocortex/extraction/agents.py && echo "OK: rule exception" || echo "FAIL"
```

Then re-run the Episode 2 smoke test (correction episode) and verify:
- `inspect_node("Metaphone3 Hybrid Strategy")` shows a SUPERSEDES edge to the old entity
- OR the post-curation audit log shows `temporal_edge_missing` followed by programmatic creation

---

## Commit

```
fix(extraction): reinforce temporal edge creation with few-shot examples and fallback

Librarian prompt: added worked example showing exact tool-call sequence for
temporal corrections, fixed contradictory "prefer updating" rule, made context
injection imperative with ACTION REQUIRED directives.

Pipeline: added post-curation audit that programmatically creates temporal
edges when the librarian fails to create them (belt-and-suspenders).

Closes temporal edge gap found in Plan 19 Stage 6 smoke test.
```
