# Diagnostic Queries

SQL queries for verifying fixes against a running PostgreSQL instance.
Replace `{schema}` with the target graph schema name (e.g., `ncx_anonymous__personal`).

---

## Node Content Verification (Stage 1)

```sql
-- Q1: Find nodes with stale content (content doesn't match latest episode)
SELECT n.id, n.name, nt.name AS type, LEFT(n.content, 80) AS content,
       n.updated_at, n.created_at
FROM {schema}.node n
JOIN {schema}.node_type nt ON n.type_id = nt.id
ORDER BY n.updated_at DESC
LIMIT 20;

-- Q2: Compare node content to source episodes
SELECT n.name, LEFT(n.content, 60) AS node_content,
       e.id AS episode_id, LEFT(e.content, 60) AS episode_content,
       e.created_at AS episode_time
FROM {schema}.node n
JOIN {schema}.node_type nt ON n.type_id = nt.id
JOIN {schema}.episode e ON (n.properties->>'_source_episode')::int = e.id
ORDER BY n.name, e.created_at DESC;
```

## Duplicate Node Detection (Stage 3)

```sql
-- Q3: Find duplicate node names (same name, different type)
SELECT n.name, COUNT(*) AS count,
       array_agg(nt.name ORDER BY n.id) AS types,
       array_agg(n.id ORDER BY n.id) AS node_ids
FROM {schema}.node n
JOIN {schema}.node_type nt ON n.type_id = nt.id
GROUP BY lower(n.name)
HAVING COUNT(*) > 1
ORDER BY count DESC;
```

## Duplicate Edge Detection (Stage 4)

```sql
-- Q4: Find duplicate edges (same source-target, different types)
SELECT src.name AS source, tgt.name AS target,
       COUNT(*) AS edge_count,
       array_agg(et.name ORDER BY e.id) AS edge_types,
       array_agg(e.weight ORDER BY e.id) AS weights
FROM {schema}.edge e
JOIN {schema}.node src ON e.source_id = src.id
JOIN {schema}.node tgt ON e.target_id = tgt.id
JOIN {schema}.edge_type et ON e.type_id = et.id
GROUP BY e.source_id, e.target_id
HAVING COUNT(*) > 1
ORDER BY edge_count DESC;
```

## Edge Weight Distribution (Stage 5)

```sql
-- Q5: Weight distribution histogram
SELECT
    CASE
        WHEN weight < 1.0 THEN '< 1.0'
        WHEN weight < 1.2 THEN '1.0 - 1.2'
        WHEN weight < 1.5 THEN '1.2 - 1.5'
        WHEN weight < 1.8 THEN '1.5 - 1.8'
        ELSE '>= 1.8'
    END AS weight_bucket,
    COUNT(*) AS edge_count,
    ROUND(AVG(weight)::numeric, 3) AS avg_weight
FROM {schema}.edge
GROUP BY weight_bucket
ORDER BY weight_bucket;

-- Q6: Top edges by weight (potential creep victims)
SELECT src.name AS source, et.name AS rel, tgt.name AS target,
       e.weight, e.last_reinforced_at
FROM {schema}.edge e
JOIN {schema}.node src ON e.source_id = src.id
JOIN {schema}.node tgt ON e.target_id = tgt.id
JOIN {schema}.edge_type et ON e.type_id = et.id
ORDER BY e.weight DESC
LIMIT 15;
```

## Type Drift Monitoring (Stages 2-4)

```sql
-- Q7: Node type diversity per name (high = drift)
SELECT n.name, COUNT(DISTINCT nt.name) AS type_count,
       array_agg(DISTINCT nt.name) AS types
FROM {schema}.node n
JOIN {schema}.node_type nt ON n.type_id = nt.id
GROUP BY n.name
HAVING COUNT(DISTINCT nt.name) > 1;

-- Q8: Edge type diversity per source-target pair
SELECT src.name AS source, tgt.name AS target,
       COUNT(DISTINCT et.name) AS type_count,
       array_agg(DISTINCT et.name) AS types
FROM {schema}.edge e
JOIN {schema}.node src ON e.source_id = src.id
JOIN {schema}.node tgt ON e.target_id = tgt.id
JOIN {schema}.edge_type et ON e.type_id = et.id
GROUP BY src.name, tgt.name
HAVING COUNT(DISTINCT et.name) > 1;

-- Q9: Graph summary stats
SELECT
    (SELECT COUNT(*) FROM {schema}.node) AS nodes,
    (SELECT COUNT(*) FROM {schema}.edge) AS edges,
    (SELECT COUNT(*) FROM {schema}.episode) AS episodes,
    (SELECT COUNT(*) FROM {schema}.node_type) AS node_types,
    (SELECT COUNT(*) FROM {schema}.edge_type) AS edge_types;
```
