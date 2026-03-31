# Diagnostic Queries

SQL queries for investigating shared graph consolidation issues.
Replace `{schema}` with the actual schema name (e.g., `ncx_shared__project_titan`).

---

## D1: Find orphaned type IDs (nodes with no matching node_type)

```sql
SELECT n.id, n.name, n.type_id, 'orphaned' AS issue
FROM {schema}.node n
LEFT JOIN {schema}.node_type nt ON nt.id = n.type_id
WHERE nt.id IS NULL
  AND n.forgotten = false;
```

If this returns rows, `cleanup_empty_types` deleted a type that still has nodes.

---

## D2: Check RLS status on shared graph tables

```sql
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname = '{schema}'
  AND tablename IN ('node', 'edge', 'episode');
```

After Stage 1: `rowsecurity` should be `false` for all three tables.

---

## D3: Check owner_role distribution in shared graph

```sql
SELECT owner_role, count(*) AS node_count
FROM {schema}.node
WHERE forgotten = false
GROUP BY owner_role
ORDER BY node_count DESC;
```

Healthy shared graph should show multiple distinct owner_role values.

---

## D4: Find nodes that exist in multiple schemas (cross-schema dedup check)

```sql
-- Run across two schemas to find potential duplicates
SELECT a.name, a.content AS schema_a_content, b.content AS schema_b_content
FROM {schema_a}.node a
JOIN {schema_b}.node b ON lower(a.name) = lower(b.name)
WHERE a.forgotten = false AND b.forgotten = false;
```

---

## D5: Check RLS policies (before removal)

```sql
SELECT policyname, tablename, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = '{schema}';
```

After Stage 1: this should return 0 rows for shared schemas.

---

## D6: Verify extraction job failure rate

```sql
SELECT status, count(*) AS job_count
FROM procrastinate_jobs
WHERE task_name = 'extract_episode'
GROUP BY status;
```

---

## D7: Check type_names resolution in recall

```sql
-- Simulate what recall does: fetch types for a set of node IDs
SELECT n.id, n.name, n.type_id, nt.name AS type_name
FROM {schema}.node n
LEFT JOIN {schema}.node_type nt ON nt.id = n.type_id
WHERE n.forgotten = false
ORDER BY n.updated_at DESC
LIMIT 20;
```

Any row where `type_name IS NULL` would produce "Unknown" in recall.
