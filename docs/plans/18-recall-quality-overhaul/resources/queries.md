# Diagnostic Queries

SQL queries for investigating and validating recall quality changes. Run against the per-graph schema (e.g., `ncx_alice__personal`).

## Activation Distribution

```sql
-- Check activation score distribution across nodes
SELECT
    name,
    access_count,
    importance,
    last_accessed_at,
    created_at,
    updated_at,
    -- Compute current activation (original formula)
    1.0 / (1.0 + exp(-(ln(access_count + 1) - 0.5 * ln(EXTRACT(EPOCH FROM (now() - last_accessed_at)) / 3600.0 + 1)))) AS activation_original,
    -- Compute dampened activation (new formula with α=0.5)
    1.0 / (1.0 + exp(-(ln(pow(access_count, 0.5) + 1) - 0.5 * ln(EXTRACT(EPOCH FROM (now() - last_accessed_at)) / 3600.0 + 1)))) AS activation_dampened
FROM node
WHERE NOT forgotten
ORDER BY access_count DESC
LIMIT 20;
```

## Gravity Well Detection

```sql
-- Find nodes with disproportionately high access counts
SELECT name, type_id, access_count, importance,
       (SELECT name FROM node_type WHERE id = node.type_id) as type_name
FROM node
WHERE access_count > (SELECT AVG(access_count) + 2 * STDDEV(access_count) FROM node)
ORDER BY access_count DESC;
```

## Episode Activation Distribution

```sql
-- Same for episodes
SELECT LEFT(content, 80) as content_preview,
       access_count, importance, created_at, last_accessed_at
FROM episode
ORDER BY access_count DESC
LIMIT 20;
```

## Domain Routing Status

```sql
-- Check if seed domains exist
SELECT slug, name, description, schema_name, seed, created_at
FROM ontology_domains;

-- Check domain classification results (in agent_actions.log, not SQL)
-- Look for: "domain_classification_result" entries
```

## Supersession Edges

```sql
-- Find supersession relationships (after Stage 6)
SELECT
    s.name as superseding_node,
    t.name as superseded_node,
    et.name as edge_type,
    e.created_at
FROM edge e
JOIN node s ON s.id = e.source_id
JOIN node t ON t.id = e.target_id
JOIN edge_type et ON et.id = e.type_id
WHERE et.name IN ('SUPERSEDES', 'CORRECTS')
ORDER BY e.created_at DESC;
```

## Type Corruption Check

```sql
-- Find node types with invalid characters
SELECT name, id, description
FROM node_type
WHERE name ~ '[^a-zA-Z0-9]';

-- Find edge types with invalid characters
SELECT name, id, description
FROM edge_type
WHERE name ~ '[^A-Z0-9_]';
```

## Semantic Duplicate Detection

```sql
-- Find nodes with same name but different types
SELECT n.name, array_agg(DISTINCT nt.name) as types, count(*) as type_count
FROM node n
JOIN node_type nt ON nt.id = n.type_id
WHERE NOT n.forgotten
GROUP BY n.name
HAVING count(DISTINCT n.type_id) > 1
ORDER BY count(*) DESC;
```

## Empty Types

```sql
-- Find types with zero nodes
SELECT nt.name, nt.description, nt.created_at
FROM node_type nt
LEFT JOIN node n ON n.type_id = nt.id AND NOT n.forgotten
WHERE n.id IS NULL
ORDER BY nt.created_at;
```

## Recency Score Comparison

```sql
-- Compare recency scores using created_at vs max(created_at, updated_at)
SELECT
    name,
    created_at,
    updated_at,
    -- Recency from created_at only (old behavior)
    pow(2, -EXTRACT(EPOCH FROM (now() - created_at)) / 3600.0 / 168.0) AS recency_created,
    -- Recency from max(created_at, updated_at) (new behavior)
    pow(2, -EXTRACT(EPOCH FROM (now() - GREATEST(created_at, updated_at))) / 3600.0 / 168.0) AS recency_updated,
    -- Difference
    pow(2, -EXTRACT(EPOCH FROM (now() - GREATEST(created_at, updated_at))) / 3600.0 / 168.0)
    - pow(2, -EXTRACT(EPOCH FROM (now() - created_at)) / 3600.0 / 168.0) AS recency_gain
FROM node
WHERE updated_at > created_at + interval '1 hour'
ORDER BY recency_gain DESC
LIMIT 20;
```
