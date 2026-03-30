# Diagnostic Queries

SQL queries for investigating normalization behavior. Run these against the
graph schema (replace `{schema}` with the actual schema name, e.g., `ncx_alice__personal`).

## Node Dedup Audit

```sql
-- Find potential duplicate nodes (same name, different type)
SELECT n.name, nt.name AS type_name, n.id, n.content, n.importance
FROM {schema}.node n
JOIN {schema}.node_type nt ON n.type_id = nt.id
WHERE n.forgotten = false
ORDER BY lower(n.name), nt.name;

-- Find nodes with high trigram similarity (potential duplicates)
SELECT a.name AS name_a, b.name AS name_b,
       similarity(a.name, b.name) AS sim,
       nta.name AS type_a, ntb.name AS type_b
FROM {schema}.node a
CROSS JOIN {schema}.node b
JOIN {schema}.node_type nta ON a.type_id = nta.id
JOIN {schema}.node_type ntb ON b.type_id = ntb.id
WHERE a.id < b.id
  AND a.forgotten = false AND b.forgotten = false
  AND similarity(a.name, b.name) >= 0.3
ORDER BY sim DESC;
```

## Alias Table

```sql
-- List all aliases
SELECT a.alias, n.name AS canonical_name, nt.name AS type_name, a.source
FROM {schema}.node_alias a
JOIN {schema}.node n ON a.node_id = n.id
JOIN {schema}.node_type nt ON n.type_id = nt.id
ORDER BY n.name, a.alias;

-- Check if an alias resolves
SELECT n.name, n.content, nt.name AS type_name
FROM {schema}.node n
JOIN {schema}.node_alias a ON a.node_id = n.id
JOIN {schema}.node_type nt ON n.type_id = nt.id
WHERE lower(a.alias) = lower('Kafka');
```

## Edge Type Audit

```sql
-- Edge type distribution (sorted by usage count)
SELECT et.name, et.description, COUNT(e.id) AS edge_count
FROM {schema}.edge_type et
LEFT JOIN {schema}.edge e ON e.type_id = et.id
GROUP BY et.id, et.name, et.description
ORDER BY edge_count DESC;

-- Unused edge types (potential cleanup candidates)
SELECT et.name, et.description
FROM {schema}.edge_type et
LEFT JOIN {schema}.edge e ON e.type_id = et.id
WHERE e.id IS NULL;

-- Similar edge type names (potential normalization targets)
SELECT a.name AS name_a, b.name AS name_b, similarity(a.name, b.name) AS sim
FROM {schema}.edge_type a
CROSS JOIN {schema}.edge_type b
WHERE a.id < b.id AND similarity(a.name, b.name) >= 0.6
ORDER BY sim DESC;
```

## Node Type Audit

```sql
-- Node type distribution
SELECT nt.name, nt.description, COUNT(n.id) AS node_count
FROM {schema}.node_type nt
LEFT JOIN {schema}.node n ON n.type_id = nt.id AND n.forgotten = false
GROUP BY nt.id, nt.name, nt.description
ORDER BY node_count DESC;

-- Unused node types
SELECT nt.name, nt.description
FROM {schema}.node_type nt
LEFT JOIN {schema}.node n ON n.type_id = nt.id AND n.forgotten = false
WHERE n.id IS NULL;
```

## Graph Health

```sql
-- Overall stats
SELECT
    (SELECT count(*) FROM {schema}.node WHERE forgotten = false) AS active_nodes,
    (SELECT count(*) FROM {schema}.node WHERE forgotten = true) AS forgotten_nodes,
    (SELECT count(*) FROM {schema}.edge) AS edges,
    (SELECT count(*) FROM {schema}.episode) AS episodes,
    (SELECT count(*) FROM {schema}.node_type) AS node_types,
    (SELECT count(*) FROM {schema}.edge_type) AS edge_types,
    (SELECT count(*) FROM {schema}.node_alias) AS aliases;

-- Edge weight distribution
SELECT
    min(weight) AS min_weight,
    avg(weight) AS avg_weight,
    max(weight) AS max_weight,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY weight) AS median_weight,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY weight) AS p95_weight
FROM {schema}.edge;
```
