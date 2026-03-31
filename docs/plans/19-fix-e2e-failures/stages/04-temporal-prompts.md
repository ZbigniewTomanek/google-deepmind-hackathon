# Stage 4: Temporal Prompt Strengthening

**Goal**: Update extractor and librarian agent prompts so correction markers in episode text reliably produce SUPERSEDES/CORRECTS edges in the graph.
**Dependencies**: Stage 3 (temporal schema fields must exist)

---

## Background

The current librarian prompt (agents.py:312-320) mentions temporal relationships as guidelines:
```
## Temporal Relationships
- If new information CORRECTS a previous fact...
- Look for signals: 'CORRECTION', 'UPDATE', 'REVERSAL', ...
```

This is passive guidance. The agent follows the simpler path: merge into existing node. Only 1 SUPERSEDES edge was created across 206 nodes in the E2E test.

The fix has two parts:
1. **Extractor**: detect temporal signals and populate the new `supersedes`/`temporal_signal` fields
2. **Librarian**: when `supersedes` is set, create a NEW node (not merge) and create the temporal edge

---

## Steps

### 1. Add temporal detection to extractor agent prompt

**File**: `src/neocortex/extraction/agents.py` -- find the extractor system prompt (around lines 162-234)

Add a dedicated section to the extractor's system prompt, AFTER the existing entity extraction instructions:

```python
"## Temporal Corrections",
"When the text contains signals that new information CORRECTS or SUPERSEDES",
"previous knowledge, you MUST populate the `supersedes` and `temporal_signal`",
"fields on the relevant entity:",
"",
"- CORRECTION signals: 'CORRECTION', 'actually', 'error', 'bug fix',",
"  'misconception', 'wrong', 'incorrect'",
"  → Set temporal_signal='CORRECTS', supersedes='<old entity name>'",
"",
"- SUPERSESSION signals: 'UPDATE', 'REVERSAL', 'instead of', 'no longer',",
"  'changed to', 'replaced by', 'switched from', 'new strategy',",
"  'decided to switch', 'moving from X to Y'",
"  → Set temporal_signal='SUPERSEDES', supersedes='<old entity name>'",
"",
"When a correction is detected, use a VERSIONED name for the new entity:",
"  - Old: 'Metaphone3' → New: 'Metaphone3 Hybrid Strategy'",
"  - Old: 'Jonas Weber' role → New entity: 'Jonas Weber Security Role'",
"This prevents the librarian from merging the new entity into the old one.",
```

### 2. Strengthen librarian temporal workflow

**File**: `src/neocortex/extraction/agents.py` -- find the librarian system prompt (around lines 272-330)

Replace the current "## Temporal Relationships" section with a mandatory workflow:

```python
"## Temporal Corrections (MANDATORY)",
"When an extracted entity has `supersedes` set (non-null):",
"",
"  1. DO NOT merge this entity into the existing node with the superseded name.",
"  2. Create a NEW node with the extracted name (versioned name).",
"  3. Create an edge of the type specified in `temporal_signal`",
"     (either 'CORRECTS' or 'SUPERSEDES') FROM the new node TO the old node.",
"  4. Report both the new node creation and the temporal edge in your actions.",
"",
"This is non-negotiable. Temporal correction edges are critical for recall quality.",
"If you merge a correction into an existing node, the temporal signal is lost.",
"",
"Even without explicit `supersedes` fields, watch for these signals in the",
"episode text and create temporal edges when appropriate:",
"  - 'CORRECTION', 'UPDATE', 'REVERSAL', 'actually', 'instead',",
"    'no longer', 'changed to', 'replaced by', 'switched from'",
```

### 3. Pass temporal metadata to librarian deps

**File**: `src/neocortex/extraction/pipeline.py:166-182`

The `LibrarianAgentDeps` receives `extracted_entities` from the extractor. The `supersedes` and `temporal_signal` fields are already part of `ExtractedEntity` (from Stage 3), so they flow through automatically. No pipeline change needed.

However, verify that the librarian's user message includes the extracted entities with their temporal fields. Currently (line 167):
```python
"Integrate the extracted entities and relations into the knowledge graph."
```

This is fine -- the entities are in `LibrarianAgentDeps.extracted_entities`, which the librarian accesses via `ctx.deps`.

### 4. Verify temporal edge types exist in the system

The SUPERSEDES and CORRECTS edge types must exist in the ontology. Check:
- `migrations/init/` for a migration that creates these types
- OR the ontology agent must propose them

From Plan 18.5 results: 1 SUPERSEDES edge was created, so the type exists. CORRECTS should also exist (Plan 18 Stage 6 seeded it). Verify by checking the migration files.

---

## Verification

```bash
# All tests pass
uv run pytest tests/ -v -x

# Check the extractor prompt includes temporal section
python3 -c "
from neocortex.extraction.agents import build_extractor_agent
agent = build_extractor_agent()
prompt = ' '.join(agent._system_prompts)
assert 'supersedes' in prompt.lower(), 'Missing supersedes in extractor prompt'
assert 'temporal_signal' in prompt.lower(), 'Missing temporal_signal in extractor prompt'
print('OK: Extractor prompt includes temporal detection instructions')
"

# Check the librarian prompt includes mandatory workflow
python3 -c "
from neocortex.extraction.agents import build_librarian_agent
agent = build_librarian_agent()
prompt = ' '.join(agent._system_prompts)
assert 'non-negotiable' in prompt.lower() or 'mandatory' in prompt.lower(), 'Missing enforcement language'
assert 'DO NOT merge' in prompt or 'do not merge' in prompt.lower(), 'Missing merge prevention'
print('OK: Librarian prompt includes mandatory temporal workflow')
"
```

---

## Commit

```
feat(extraction): enforce temporal correction detection in extractor and librarian

Extractor now detects CORRECTION/UPDATE signals and populates
supersedes/temporal_signal fields. Librarian's temporal section
upgraded from passive guidance to mandatory workflow: create NEW
node + temporal edge, never merge corrections into existing nodes.

Fixes M4 (0/3 temporal recall) from Plan 18.5 E2E revalidation.
```
