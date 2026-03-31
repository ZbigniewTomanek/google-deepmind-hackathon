# E2E Revalidation: Plan 22 Metrics After Plan 23 Fixes

Re-run the Plan 22 multi-agent shared knowledge graph validation to verify
that the 3 failing metrics (M3, M4, M7) now pass after the fixes in Plan 23.

## Prerequisites

- Docker running (for PostgreSQL)
- `uv sync` completed
- Gemini API key set (`GOOGLE_API_KEY` or `GEMINI_API_KEY`)

## Steps

### 1. Start fresh

```bash
./scripts/manage.sh stop --all
./scripts/manage.sh start --fresh
```

### 2. Create shared graph and permissions

Follow [Plan 22 Stage 1](../../22-multi-agent-shared-graph-validation/index.md) —
create a shared research graph and grant both agents access:

```bash
# Create shared graph (via admin API)
./scripts/ingest.sh admin create-graph --purpose research --shared

# Grant permissions to alice and bob
./scripts/ingest.sh admin grant --agent alice --schema ncx_shared__research --read --write
./scripts/ingest.sh admin grant --agent bob --schema ncx_shared__research --read --write
```

### 3. Ingest Alice's episodes

Ingest Alice's research content targeting the shared graph:

```bash
./scripts/ingest.sh text --agent alice --target ncx_shared__research \
  --content "Python is a general-purpose programming language created by Guido van Rossum in 1991."

./scripts/ingest.sh text --agent alice --target ncx_shared__research \
  --content "PostgreSQL is an advanced open-source relational database with ACID compliance."
```

Wait for extraction jobs to complete (check logs or `./scripts/manage.sh status`).

### 4. Ingest Bob's complementary and corrective episodes

```bash
# Complementary: adds ML context to Python
./scripts/ingest.sh text --agent bob --target ncx_shared__research \
  --content "Python is widely used in machine learning with libraries like TensorFlow and PyTorch."

# Correction: supersedes incorrect information
./scripts/ingest.sh text --agent bob --target ncx_shared__research \
  --content "Note: Python was first released in 1991, not 1989 as sometimes reported. Guido van Rossum started development in 1989 but the first public release was February 1991."
```

Wait for extraction jobs to complete.

### 5. Check M3: Complementary fact merge

Query the shared graph for Python nodes — content should reflect contributions
from both Alice and Bob:

```bash
./scripts/ingest.sh recall --agent alice --query "Python programming language"
```

**Expected**: The Python node's content mentions both general-purpose programming
AND machine learning use. Score: ≥ 3/5 content merge indicators present.

### 6. Check M4: Conflict handling

Verify that corrections propagate — Bob's corrective episode should update or
supersede Alice's original information:

```bash
./scripts/ingest.sh recall --agent bob --query "Python release date"
```

**Expected**: Corrected information is reflected. Score: ≥ 2/3 corrections propagated.

### 7. Check M7: Recall type resolution

Verify no "Unknown" types appear in recall results:

```bash
./scripts/ingest.sh recall --agent alice --query "Python" | grep -i "unknown"
./scripts/ingest.sh recall --agent alice --query "PostgreSQL" | grep -i "unknown"
```

**Expected**: Zero occurrences of "Unknown" in `item_type` fields.

## Expected Outcomes After Fixes

| Metric | Baseline (Plan 22) | Expected After Plan 23 |
|--------|---------------------|------------------------|
| M3: Complementary fact merge | 0/5 (0%) | ≥ 3/5 (60%) |
| M4: Conflict handling | 0/3 (0%) | ≥ 2/3 (67%) |
| M7: Recall type resolution | Many "Unknown" | 0 "Unknown" types |
| Extraction failure rate | 29% (4/14) | ≤ 10% |

## Root Causes Fixed

1. **RLS removed from shared graphs** (Stage 1) — cross-agent writes no longer blocked
2. **Content merging awareness** (Stage 2) — librarian prompt instructs content consolidation
3. **tool_calls_limit raised** (Stage 3) — complex episodes no longer exceed budget
4. **Graceful update failure** (Stage 4) — UPDATE 0 rows falls through to INSERT
5. **Type resolution via JOIN** (Stage 5) — item_type always resolved, no separate lookup
