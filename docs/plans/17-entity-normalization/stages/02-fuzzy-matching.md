# Stage 2: Fuzzy Name Matching & Alias Table

**Goal**: Add a `node_alias` table and integrate trigram-based fuzzy name lookup into the adapter's dedup pipeline, so name variants like "Kafka" / "Apache Kafka" resolve to the same node.

**Dependencies**: Stage 1 (normalization utility)

---

## Rationale

The adapter's `upsert_node()` uses `WHERE lower(name) = lower($1)` for Phase 1 lookup.
This misses name variants entirely. The trigram GIN index (`idx_node_name_trgm`) already
exists on every graph schema but is **never used** for dedup lookups. This stage activates it.

The alias table provides a second lookup path: when the librarian creates "Apache Kafka"
and later the extractor produces "Kafka", the alias table maps "Kafka" → node(Apache Kafka).

---

## Steps

### Step 1: Create migration `migrations/init/009_node_alias.sql`

```sql
-- Node alias table for name variant resolution
CREATE TABLE node_alias (
    id          SERIAL PRIMARY KEY,
    node_id     INT NOT NULL REFERENCES node(id) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    source      TEXT DEFAULT 'extraction',  -- 'extraction', 'canonicalization', 'manual'
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (alias)  -- Each alias maps to exactly one node
);

-- Index for fast alias lookup (case-insensitive)
CREATE INDEX idx_node_alias_lower ON node_alias (lower(alias));
```

### Step 2: Add alias table to `migrations/templates/graph_schema.sql`

Add the same table + index to the template, after the node table definition.
Use `{schema_name}.node_alias` and `{schema_name}.node(id)` references.

### Step 3: Add protocol methods to `src/neocortex/db/protocol.py`

```python
@runtime_checkable
class MemoryRepository(Protocol):
    # ... existing methods ...

    async def find_nodes_fuzzy(
        self, agent_id: str, name: str,
        threshold: float = 0.3,
        limit: int = 5,
        target_schema: str | None = None,
    ) -> list[tuple[Node, float]]:
        """Find nodes by trigram similarity to name.
        Returns (node, similarity_score) pairs sorted by score descending.
        Also checks the node_alias table for alias matches.
        """
        ...

    async def register_alias(
        self, agent_id: str, node_id: int, alias: str,
        source: str = "extraction",
        target_schema: str | None = None,
    ) -> None:
        """Register an alias for an existing node.
        Silently ignores if alias already exists for same node.
        """
        ...

    async def resolve_alias(
        self, agent_id: str, alias: str,
        target_schema: str | None = None,
    ) -> Node | None:
        """Resolve an alias to its canonical node, or None."""
        ...
```

### Step 4: Implement in `src/neocortex/db/adapter.py`

#### 4a. `find_nodes_fuzzy()`

```sql
-- Trigram similarity search (uses existing GIN index)
SELECT n.id, n.type_id, n.name, n.content, n.properties, n.source,
       n.importance, n.created_at, n.updated_at,
       similarity(n.name, $1) AS sim
FROM node n
WHERE n.forgotten = false
  AND (similarity(n.name, $1) >= $2
       OR n.id IN (SELECT node_id FROM node_alias WHERE lower(alias) = lower($1)))
ORDER BY sim DESC
LIMIT $3
```

Note: `similarity()` requires `pg_trgm` extension (already enabled — the GIN index uses `gin_trgm_ops`).

#### 4b. `register_alias()`

```sql
INSERT INTO node_alias (node_id, alias, source)
VALUES ($1, $2, $3)
ON CONFLICT (alias) DO NOTHING
```

#### 4c. `resolve_alias()`

```sql
SELECT n.* FROM node n
JOIN node_alias a ON a.node_id = n.id
WHERE lower(a.alias) = lower($1)
  AND n.forgotten = false
```

#### 4d. Enhance `upsert_node()` Phase 1

After the existing exact-match lookup (`WHERE lower(name) = lower($1)`) returns no rows,
add a **Phase 1.5**: fuzzy + alias resolution:

```python
# Phase 1: Exact name match
rows = await conn.fetch(
    "SELECT ... FROM node WHERE lower(name) = lower($1)", name
)

# Phase 1.5: If no exact match, try alias resolution then trigram
if not rows:
    # 1.5a: Check alias table
    alias_row = await conn.fetchrow(
        "SELECT n.* FROM node n "
        "JOIN node_alias a ON a.node_id = n.id "
        "WHERE lower(a.alias) = lower($1) AND n.forgotten = false",
        name,
    )
    if alias_row:
        rows = [alias_row]
        logger.bind(action_log=True).info(
            "node_alias_resolved", alias=name,
            canonical=alias_row["name"], agent_id=agent_id,
        )
    else:
        # 1.5b: Trigram similarity (threshold 0.4 = fairly strict)
        fuzzy_rows = await conn.fetch(
            "SELECT id, type_id, name, content, properties, source, "
            "importance, forgotten, created_at, updated_at, "
            "similarity(name, $1) AS sim "
            "FROM node WHERE forgotten = false "
            "AND similarity(name, $1) >= $2 "
            "ORDER BY sim DESC LIMIT 1",
            name, 0.4,
        )
        if fuzzy_rows:
            rows = [fuzzy_rows[0]]
            logger.bind(action_log=True).info(
                "node_fuzzy_matched", input=name,
                matched=fuzzy_rows[0]["name"],
                similarity=fuzzy_rows[0]["sim"],
                agent_id=agent_id,
            )
```

**Important**: Phase 1.5 only fires when Phase 1 returns zero rows. This means:
- Exact matches still take the fast path (no trigram overhead)
- Fuzzy matching is a fallback, not a replacement
- Alias resolution is checked before trigram (cheaper)

#### 4e. Auto-register aliases on canonicalization

In `upsert_node()`, after a successful insert (new node), check if canonicalization
produced aliases and register them:

```python
from neocortex.normalization import canonicalize_name

# At the top of upsert_node:
canonical, aliases = canonicalize_name(name)
# Use canonical for the lookup, register aliases after insert

# After successful INSERT:
for alias in aliases:
    await self.register_alias(agent_id, new_node.id, alias,
                              source="canonicalization", target_schema=target_schema)
```

### Step 5: Implement in `src/neocortex/db/mock.py`

Mirror the protocol methods using in-memory data structures:
- `_aliases: dict[str, int]` mapping `lower(alias) -> node_id`
- `find_nodes_fuzzy()` uses `names_are_similar()` from Stage 1
- `register_alias()` adds to `_aliases` dict
- `resolve_alias()` looks up in `_aliases` dict

### Step 6: Tests

Create `tests/mcp/test_fuzzy_dedup.py`:

```python
# Test: exact match still preferred over fuzzy
# Test: alias resolution ("Prozac" → Fluoxetine node)
# Test: trigram match ("Kafka" → "Apache Kafka" node, sim ≥ 0.4)
# Test: no false positive ("Alice" should NOT match "Bob")
# Test: Phase 1.5 only triggers when Phase 1 returns empty
# Test: auto-alias registration on insert with parenthetical
# Test: fuzzy match + type compatibility (Phase 1.5 → Phase 3 chain)
```

Use `InMemoryRepository` for fast unit tests. Add one integration test with
real PostgreSQL if the test suite supports it.

---

## Verification

```bash
# Unit tests
uv run pytest tests/unit/test_normalization.py tests/mcp/test_fuzzy_dedup.py -v

# Check that pg_trgm extension is available (should already be)
docker compose exec postgres psql -U neocortex -c "SELECT 'kafka' % 'Apache Kafka';"
# Expected: true (if similarity threshold met)

# Check trigram similarity score
docker compose exec postgres psql -U neocortex -c "SELECT similarity('Kafka', 'Apache Kafka');"
# Expected: ~0.33-0.5 (depends on pg_trgm version)
```

Check:
- [ ] Migration applies cleanly (no conflicts with existing schemas)
- [ ] Alias table created in both init migration and schema template
- [ ] `find_nodes_fuzzy()` works on both adapter and mock
- [ ] `upsert_node()` Phase 1.5 resolves aliases before trying trigram
- [ ] Auto-alias registration works on insert
- [ ] Exact match still takes fast path (no regression)
- [ ] All tests pass

**Trigram threshold tuning note**: Start with 0.4. If "Kafka" vs "Apache Kafka"
scores below 0.4 in practice, lower to 0.3. Log the similarity score on every
fuzzy match so we can tune from production data.

---

## Commit

```
feat(dedup): add alias table and trigram fuzzy matching to adapter

Adds node_alias table for name variant resolution.
Enhances upsert_node() with Phase 1.5: alias lookup then trigram
similarity fallback when exact name match fails.
Auto-registers canonicalization aliases on new node creation.
```
