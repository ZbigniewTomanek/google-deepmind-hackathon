# Diagnostic Queries

SQL queries for measuring ontology quality before/after changes.
Replace `{schema}` with the target schema name.

---

## Type Proliferation Metrics

### Count types per graph
```sql
SELECT
    'node_types' AS kind,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE (SELECT COUNT(*) FROM {schema}.node WHERE type_id = nt.id) = 0) AS unused
FROM {schema}.node_type nt
UNION ALL
SELECT
    'edge_types',
    COUNT(*),
    COUNT(*) FILTER (WHERE (SELECT COUNT(*) FROM {schema}.edge WHERE type_id = et.id) = 0) AS unused
FROM {schema}.edge_type et;
```

### Type reuse ratio
```sql
SELECT
    ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT type_id), 0), 1) AS nodes_per_type
FROM {schema}.node;
```

### Most/least used node types
```sql
SELECT nt.name, COUNT(n.id) AS node_count
FROM {schema}.node_type nt
LEFT JOIN {schema}.node n ON n.type_id = nt.id
GROUP BY nt.name
ORDER BY node_count DESC;
```

---

## Garbage Detection

### Tool-call artifact types
```sql
SELECT name, description
FROM {schema}.node_type
WHERE name ~* '(functiondefault|calldefault|ApicreateOr|UpdateNode|UpdateEdge|createOrUpdate|defaultApi|endcall)';

SELECT name, description
FROM {schema}.edge_type
WHERE name ~* '(functiondefault|calldefault|ApicreateOr|UpdateNode|UpdateEdge|createOrUpdate|defaultApi|endcall)';
```

### Instance-level types (3+ PascalCase segments, starts with common base)
```sql
SELECT name, description,
       (SELECT COUNT(*) FROM {schema}.node WHERE type_id = nt.id) AS node_count
FROM {schema}.node_type nt
WHERE name ~ '^(Asset|Dish|Dream|Event|Insight|Location|Device|Activity|Condition|Mentalstate|Utensil|Preparation|Specification)[A-Z].*[A-Z]';
```

### Zero-usage edge types
```sql
SELECT et.name, et.description, et.created_at
FROM {schema}.edge_type et
WHERE NOT EXISTS (SELECT 1 FROM {schema}.edge e WHERE e.type_id = et.id)
ORDER BY et.created_at;
```

---

## Quality Audit

### Types with suspiciously long names (>40 chars)
```sql
SELECT name, LENGTH(name) AS len, description
FROM {schema}.node_type
WHERE LENGTH(name) > 40
ORDER BY len DESC;
```

### Potential duplicate types (trigram similarity)
```sql
SELECT a.name AS type_a, b.name AS type_b,
       similarity(a.name, b.name) AS sim
FROM {schema}.node_type a
JOIN {schema}.node_type b ON a.id < b.id
WHERE similarity(a.name, b.name) > 0.5
ORDER BY sim DESC;
```

---

## Commands

```bash
# Run all queries against a specific schema
SCHEMA=ncx_ccprivate__personal
psql -d neocortex -c "$(cat query.sql | sed "s/{schema}/$SCHEMA/g")"

# Quick type count across all schemas
for schema in ncx_ccprivate__personal ncx_shared__user_profile ncx_shared__domain_knowledge ncx_shared__work_context ncx_shared__technical_knowledge; do
    echo "=== $schema ==="
    psql -d neocortex -c "SELECT COUNT(*) AS node_types FROM $schema.node_type; SELECT COUNT(*) AS edge_types FROM $schema.edge_type;"
done
```
