# Stage 1: Name Canonicalization Utility

**Goal**: Create a deterministic name normalization module that strips noise from entity names and edge type names, producing canonical forms for consistent matching.

**Dependencies**: None (first stage)

---

## Rationale

The current system relies entirely on the LLM to produce normalized names. This works ~80% of the time but fails for:
- Parenthetical aliases: "Fluoxetine (Prozac)" vs "Fluoxetine"
- Prefix variants: "Apache Kafka" vs "Kafka"
- Casing drift: "dataForge" vs "DataForge"
- Edge type format: "RelatesTo" vs "RELATES_TO" vs "relates_to"

A deterministic layer handles these mechanically, reserving LLM judgment for genuinely ambiguous cases.

---

## Steps

### Step 1: Create `src/neocortex/normalization.py`

```python
"""Entity name and type normalization utilities.

These functions are called in the adapter layer BEFORE database lookups,
ensuring consistent matching regardless of how the LLM formats names.
"""
```

Implement the following functions:

#### 1a. `canonicalize_name(name: str) -> tuple[str, list[str]]`

Returns `(canonical_name, aliases)` where aliases are alternative forms extracted during canonicalization.

Rules (applied in order):
1. **Strip whitespace**: `name.strip()`
2. **Extract parenthetical aliases**: `"Fluoxetine (Prozac)"` → canonical=`"Fluoxetine"`, aliases=`["Prozac"]`
   - Pattern: `r"^(.+?)\s*\(([^)]+)\)\s*$"` — extract content before paren as canonical, content inside paren as alias
   - Only for single parenthetical at end, not mid-name
3. **Title case normalization** for entity names: `"apache kafka"` → `"Apache Kafka"`
   - Use `str.title()` but preserve known acronyms: `["API", "SQL", "AI", "ML", "LLM", "HTTP", "REST", "gRPC", "OAuth", "SSO", "JWT", "5-HT"]`
   - Acronym list should be a module-level constant `_KNOWN_ACRONYMS`
4. **Collapse internal whitespace**: `"  Apache   Kafka  "` → `"Apache Kafka"`

Do NOT attempt to resolve abbreviations ("5-HT" → "Serotonin") — that's the librarian's job with semantic search.

#### 1b. `normalize_edge_type(name: str) -> str`

Convert any edge type name to SCREAMING_SNAKE_CASE:

Rules:
1. `"RelatesTo"` → `"RELATES_TO"` (PascalCase → insert underscore before uppercase)
2. `"relates_to"` → `"RELATES_TO"` (lowercase → uppercase)
3. `"relates-to"` → `"RELATES_TO"` (kebab-case → underscore + uppercase)
4. `"RELATES TO"` → `"RELATES_TO"` (space → underscore)
5. Collapse multiple underscores: `"RELATES__TO"` → `"RELATES_TO"`
6. Strip leading/trailing underscores

Use `re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', name)` for PascalCase splitting, then uppercase + collapse.

#### 1c. `normalize_node_type(name: str) -> str`

Ensure PascalCase for node type names:

Rules:
1. `"software_tool"` → `"SoftwareTool"` (snake_case → PascalCase)
2. `"software tool"` → `"SoftwareTool"` (space-separated → PascalCase)
3. `"SOFTWARETOOL"` → `"Softwaretool"` (ALL_CAPS → Title case; not ideal but safe)
4. Already PascalCase → keep as-is

#### 1d. `names_are_similar(a: str, b: str, threshold: float = 0.6) -> bool`

Pure-Python string similarity check (no DB required) for use in the mock adapter:

1. Exact match after lowering → True
2. One is a substring of the other (after lowering, length ratio ≥ 0.5) → True
   - "Kafka" is substring of "Apache Kafka", len ratio = 5/12 = 0.42 → False by ratio
   - But "Kafka" is a word in "Apache Kafka" → True (word-level containment)
3. Word-level containment: split both on whitespace, if all words of shorter are in longer → True

This is a cheap heuristic for the mock adapter. The real adapter uses pg_trgm.

### Step 2: Create `tests/unit/test_normalization.py`

Test cases for each function:

```python
# canonicalize_name
("Fluoxetine (Prozac)", ("Fluoxetine", ["Prozac"]))
("Apache Kafka", ("Apache Kafka", []))
("  apache   kafka  ", ("Apache Kafka", []))
("DataForge", ("DataForge", []))
("5-HT", ("5-HT", []))  # preserve acronym
("serotonin (5-hydroxytryptamine, 5-HT)", ("Serotonin", ["5-hydroxytryptamine, 5-HT"]))

# normalize_edge_type
("RelatesTo", "RELATES_TO")
("relates_to", "RELATES_TO")
("RELATES_TO", "RELATES_TO")  # idempotent
("relates-to", "RELATES_TO")
("hasMember", "HAS_MEMBER")
("MEMBER_OF", "MEMBER_OF")  # idempotent

# normalize_node_type
("SoftwareTool", "SoftwareTool")  # idempotent
("software_tool", "SoftwareTool")
("Person", "Person")  # idempotent

# names_are_similar
("Kafka", "Apache Kafka", True)
("DataForge", "DataForge", True)
("Alice", "Bob", False)
("Team Atlas", "Atlas", True)  # word containment
```

---

## Verification

```bash
# Run unit tests
uv run pytest tests/unit/test_normalization.py -v

# Verify all tests pass
# Expected: ~15-20 test cases, 100% pass
```

Check:
- [ ] `canonicalize_name` handles all edge cases (parenthetical, whitespace, casing)
- [ ] `normalize_edge_type` is idempotent (applying twice gives same result)
- [ ] `normalize_node_type` is idempotent
- [ ] `names_are_similar` catches word-level containment without false positives
- [ ] No external dependencies added (pure Python, stdlib only)

---

## Commit

```
feat(normalization): add deterministic name and type canonicalization utility

Adds src/neocortex/normalization.py with:
- canonicalize_name(): strips parenthetical aliases, normalizes casing
- normalize_edge_type(): converts any format to SCREAMING_SNAKE_CASE
- normalize_node_type(): ensures PascalCase for node types
- names_are_similar(): word-level containment check for mock adapter
```
