# Investigation Queries

Reference SQL queries for verifying Plan 31 changes.
Replace `{schema}` with the actual per-agent schema name (e.g. `ncx_anonymous__personal`).

---

## Verify session columns exist

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'episode'
  AND column_name IN ('session_id', 'session_sequence')
ORDER BY column_name;
```

Expected: 2 rows (`session_id TEXT`, `session_sequence INTEGER`).

---

## List episodes in a session, in order

```sql
SELECT id, session_sequence, created_at, content
FROM {schema}.episode
WHERE session_id = '<target_session_id>'
ORDER BY session_sequence ASC NULLS LAST, created_at ASC;
```

---

## Check FOLLOWS edges created by extraction

```sql
SELECT
    e.id,
    e.properties->>'episode_follows' AS episode_follows,
    e.properties->>'episode_precedes' AS episode_precedes,
    et.name AS edge_type,
    sn.name AS source_node,
    tn.name AS target_node
FROM {schema}.edge e
JOIN {schema}.edge_type et ON et.id = e.type_id
JOIN {schema}.node sn ON sn.id = e.source_id
JOIN {schema}.node tn ON tn.id = e.target_id
WHERE et.name = 'FOLLOWS'
  AND e.properties ? 'episode_follows'
ORDER BY e.created_at DESC
LIMIT 20;
```

---

## Count FOLLOWS edges per session

```sql
SELECT
    ep.session_id,
    COUNT(DISTINCT e.id) AS follows_edges,
    COUNT(DISTINCT ep.id) AS total_episodes
FROM {schema}.episode ep
LEFT JOIN {schema}.edge e ON
    e.type_id = (SELECT id FROM {schema}.edge_type WHERE name = 'FOLLOWS')
    AND (e.properties->>'episode_follows')::int = ep.id
WHERE ep.session_id IS NOT NULL
GROUP BY ep.session_id
ORDER BY total_episodes DESC;
```

---

## Find episodes missing session_id (pre-migration data)

```sql
SELECT COUNT(*) AS episodes_without_session
FROM {schema}.episode
WHERE session_id IS NULL;
```

---

## Check _source_episode index is being used

```sql
EXPLAIN SELECT id FROM {schema}.node
WHERE properties->>'_source_episode' = '42';
```

After Stage 1 migration: this predicate is compatible with
`idx_node_source_episode`. On tiny tables PostgreSQL may still choose a
sequential scan; use enough rows or `SET enable_seqscan = off` when verifying
index compatibility.

---

## Verify neighbor expansion in recall (manual test)

```sql
-- Get a known episode_id and session_id:
SELECT id, session_id, created_at, content
FROM {schema}.episode
WHERE session_id IS NOT NULL
ORDER BY created_at DESC
LIMIT 5;

-- Then manually fetch neighbors for episode id=<X>:
SELECT id, session_id, created_at, content
FROM {schema}.episode
WHERE session_id = '<target_session_id>'
  AND id != <X>
  AND created_at < (SELECT created_at FROM {schema}.episode WHERE id = <X>)
ORDER BY created_at DESC
LIMIT 1;
-- (preceding episode)

SELECT id, session_id, created_at, content
FROM {schema}.episode
WHERE session_id = '<target_session_id>'
  AND id != <X>
  AND created_at > (SELECT created_at FROM {schema}.episode WHERE id = <X>)
ORDER BY created_at ASC
LIMIT 2;
-- (following episodes)
```
