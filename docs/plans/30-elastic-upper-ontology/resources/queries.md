# Diagnostic Queries

SQL queries for measuring upper ontology behavior before and after implementation.
Run via `psql` or the `scripts/ingest.sh` wrapper.

## Connection

```bash
psql "postgresql://neocortex:neocortex@localhost:5432/neocortex"
```

---

## Q1: Domain Registry — All Domains

```sql
SELECT id, slug, name, schema_name, seed, created_by, created_at
FROM ontology_domains
ORDER BY id;
```

**Baseline expectation**: Exactly 4 rows (seed domains).
**Post-implementation expectation**: 6-10 rows with new non-seed domains.

---

## Q2: Episode Count Per Domain Schema

```sql
SELECT
    d.slug AS domain,
    d.seed,
    s.schema_name,
    COALESCE(ep.episode_count, 0) AS episodes
FROM ontology_domains d
LEFT JOIN graph_registry s ON s.schema_name = d.schema_name
LEFT JOIN LATERAL (
    SELECT count(*) AS episode_count
    FROM (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = d.schema_name AND table_name = 'episode'
    ) tbl
    CROSS JOIN LATERAL (
        SELECT count(*) AS episode_count
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = d.schema_name AND c.relname = 'episode'
    ) cnt
) ep ON true
ORDER BY episodes DESC;
```

**Simpler alternative** (run per schema):

```sql
-- Replace {schema} with actual schema name
SELECT count(*) AS episode_count FROM {schema}.episode;
```

---

## Q3: Domain Utilization — Nodes and Types Per Domain

```sql
-- Run for each domain schema. Replace {schema}.
SELECT
    '{schema}' AS domain_schema,
    (SELECT count(*) FROM {schema}.node WHERE NOT forgotten) AS active_nodes,
    (SELECT count(*) FROM {schema}.edge) AS edges,
    (SELECT count(*) FROM {schema}.node_type) AS node_types,
    (SELECT count(*) FROM {schema}.edge_type) AS edge_types,
    (SELECT count(*) FROM {schema}.node_type nt
     WHERE EXISTS (SELECT 1 FROM {schema}.node n WHERE n.type_id = nt.id AND NOT n.forgotten)) AS used_node_types,
    (SELECT count(*) FROM {schema}.edge_type et
     WHERE EXISTS (SELECT 1 FROM {schema}.edge e WHERE e.type_id = et.id)) AS used_edge_types;
```

---

## Q4: Catch-All Absorption Rate

Measures what fraction of episodes end up in `domain_knowledge` vs specialized domains.

```sql
WITH domain_episodes AS (
    SELECT
        d.slug,
        (SELECT count(*) FROM ncx_shared__user_profile.episode) AS ct
    FROM ontology_domains d WHERE d.slug = 'user_profile'
    UNION ALL
    SELECT 'technical_knowledge',
        (SELECT count(*) FROM ncx_shared__technical_knowledge.episode)
    UNION ALL
    SELECT 'work_context',
        (SELECT count(*) FROM ncx_shared__work_context.episode)
    UNION ALL
    SELECT 'domain_knowledge',
        (SELECT count(*) FROM ncx_shared__domain_knowledge.episode)
)
SELECT
    slug,
    ct AS episodes,
    round(100.0 * ct / NULLIF(sum(ct) OVER (), 0), 1) AS pct
FROM domain_episodes
ORDER BY ct DESC;
```

---

## Q5: Type Landscape Per Domain

Shows all node types with usage counts — reveals whether seed types dominate
or new types emerge.

```sql
-- Replace {schema}
SELECT
    nt.name AS type_name,
    nt.description,
    count(n.id) AS usage_count,
    nt.created_at
FROM {schema}.node_type nt
LEFT JOIN {schema}.node n ON n.type_id = nt.id AND NOT n.forgotten
GROUP BY nt.id
ORDER BY usage_count DESC, nt.name;
```

---

## Q6: Domain Hierarchy (post-implementation)

```sql
SELECT
    d.id,
    d.slug,
    d.name,
    d.parent_id,
    p.slug AS parent_slug,
    d.depth,
    d.path,
    d.seed
FROM ontology_domains d
LEFT JOIN ontology_domains p ON p.id = d.parent_id
ORDER BY d.path, d.slug;
```

---

## Q7: Steward Health Metrics

Domain health snapshot for the taxonomy steward.

```sql
-- Type diversity (Shannon entropy proxy)
-- Replace {schema}
WITH type_usage AS (
    SELECT nt.name, count(n.id) AS cnt
    FROM {schema}.node_type nt
    LEFT JOIN {schema}.node n ON n.type_id = nt.id AND NOT n.forgotten
    GROUP BY nt.id
    HAVING count(n.id) > 0
)
SELECT
    count(*) AS active_types,
    sum(cnt) AS total_nodes,
    round(avg(cnt), 1) AS avg_nodes_per_type,
    max(cnt) AS max_type_usage,
    min(cnt) AS min_type_usage
FROM type_usage;
```

---

## Baseline Capture Template

Run all queries and record results in this format:

```markdown
### Baseline Results — [date]

| Metric | Value |
|--------|-------|
| Total domains | |
| Non-seed domains | |
| Episodes in domain_knowledge | |
| Catch-all absorption % | |
| Total unique node types (all domains) | |
| Total unique edge types (all domains) | |
| Novel-domain documents that created new domains | |
```
