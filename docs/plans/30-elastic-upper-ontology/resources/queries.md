# Diagnostic Queries

SQL queries for measuring upper-ontology behavior before and after implementation.
Run via `psql`.

Important: shared domain schemas are populated by routed `extract_episode` jobs.
Episodes themselves remain in the personal graph unless `target_graph` is
explicitly set. Measure routing via `procrastinate_jobs`, `ontology_domains`, and
shared-schema nodes/edges.

## Connection

```bash
psql "postgresql://neocortex:neocortex@localhost:5432/neocortex"
```

---

## Q1: Domain Registry

Pre-hierarchy (Stages 1–2):

```sql
SELECT
    d.id,
    d.slug,
    d.name,
    d.schema_name,
    d.seed,
    d.created_by,
    d.created_at
FROM ontology_domains d
ORDER BY d.slug;
```

Post-hierarchy (Stage 3+):

```sql
SELECT
    d.id,
    d.slug,
    d.name,
    d.parent_id,
    p.slug AS parent_slug,
    d.depth,
    d.path,
    d.schema_name,
    d.seed,
    d.created_by,
    d.created_at
FROM ontology_domains d
LEFT JOIN ontology_domains p ON p.id = d.parent_id
ORDER BY d.path NULLS FIRST, d.slug;
```

Use for:
- baseline domain count
- non-seed domain detection
- hierarchy verification after Stage 3+

---

## Q2: Routed Episodes Per Domain

Counts successful shared-schema extraction jobs by target domain.

```sql
SELECT
    d.slug AS domain,
    d.schema_name,
    count(*) FILTER (
        WHERE j.task_name = 'extract_episode'
          AND j.status = 'succeeded'
          AND j.args->>'target_schema' = d.schema_name
    ) AS routed_jobs,
    count(DISTINCT (j.args->'episode_ids'->>0)) FILTER (
        WHERE j.task_name = 'extract_episode'
          AND j.status = 'succeeded'
          AND j.args->>'target_schema' = d.schema_name
    ) AS routed_episodes
FROM ontology_domains d
LEFT JOIN procrastinate_jobs j ON j.args->>'target_schema' = d.schema_name
GROUP BY d.slug, d.schema_name
ORDER BY routed_episodes DESC, d.slug;
```

This is the primary routing-distribution metric for this plan.

---

## Q3: Shared Graph Utilization Per Domain

Run in `psql`; this uses `\gexec` to expand one query per registered domain schema.

```sql
SELECT format($fmt$
SELECT
    %L AS domain,
    %L AS schema_name,
    (SELECT count(*) FROM %I.node WHERE NOT forgotten) AS active_nodes,
    (SELECT count(*) FROM %I.edge) AS edges,
    (SELECT count(*) FROM %I.node_type) AS node_types,
    (SELECT count(*) FROM %I.edge_type) AS edge_types,
    (SELECT count(*)
       FROM %I.node_type nt
      WHERE EXISTS (
          SELECT 1 FROM %I.node n
           WHERE n.type_id = nt.id AND NOT n.forgotten
      )
    ) AS used_node_types,
    (SELECT count(*)
       FROM %I.edge_type et
      WHERE EXISTS (
          SELECT 1 FROM %I.edge e
           WHERE e.type_id = et.id
      )
    ) AS used_edge_types;
$fmt$,
    slug, schema_name,
    schema_name, schema_name, schema_name, schema_name,
    schema_name, schema_name,
    schema_name, schema_name
)
FROM ontology_domains
WHERE schema_name IS NOT NULL
ORDER BY slug
\gexec
```

---

## Q4: Catch-All Absorption Rate

Measures what fraction of routed shared-schema episodes end up in
`domain_knowledge` versus all routed shared-domain extractions.

```sql
WITH routed AS (
    SELECT
        d.slug,
        count(DISTINCT (j.args->'episode_ids'->>0)) AS routed_episodes
    FROM ontology_domains d
    LEFT JOIN procrastinate_jobs j
      ON j.task_name = 'extract_episode'
     AND j.status = 'succeeded'
     AND j.args->>'target_schema' = d.schema_name
    GROUP BY d.slug
)
SELECT
    slug,
    routed_episodes,
    round(100.0 * routed_episodes / NULLIF(sum(routed_episodes) OVER (), 0), 1) AS pct
FROM routed
ORDER BY routed_episodes DESC, slug;
```

---

## Q5: Type Landscape Per Domain

Run in `psql`; this uses `\gexec`.

```sql
SELECT format($fmt$
SELECT
    %L AS domain,
    nt.name AS type_name,
    nt.description,
    count(n.id) AS usage_count,
    nt.created_at
FROM %I.node_type nt
LEFT JOIN %I.node n
  ON n.type_id = nt.id
 AND NOT n.forgotten
GROUP BY nt.id
ORDER BY usage_count DESC, nt.name;
$fmt$, slug, schema_name, schema_name)
FROM ontology_domains
WHERE schema_name IS NOT NULL
ORDER BY slug
\gexec
```

---

## Q6: Unmatched / Unrouted Summary

Use this after Stage 4 removes the default `domain_knowledge` fallback.
This is log-driven because there is no route ledger table yet.

```bash
grep -i "domain_classification_result\|domain_provisioned\|route_episode_completed" log/agent_actions.log | tail -200
```

Record manually:
- docs with `domain_provisioned`
- docs routed only to `domain_knowledge`
- docs with no routed shared schema

---

## Q7: Steward Health Inputs

Report-oriented snapshot combining routed-episode counts with shared-graph usage.

```sql
WITH routed AS (
    SELECT
        args->>'target_schema' AS schema_name,
        count(DISTINCT (args->'episode_ids'->>0)) AS routed_episodes
    FROM procrastinate_jobs
    WHERE task_name = 'extract_episode'
      AND status = 'succeeded'
      AND args->>'target_schema' IS NOT NULL
    GROUP BY args->>'target_schema'
)
SELECT
    d.slug,
    d.schema_name,
    coalesce(r.routed_episodes, 0) AS routed_episodes
FROM ontology_domains d
LEFT JOIN routed r ON r.schema_name = d.schema_name
ORDER BY routed_episodes DESC, d.slug;
```

Combine with `Q3` for full steward reporting.

---

## Baseline Capture Template

```markdown
### Baseline Results — [date]

| Metric | Value |
|--------|-------|
| Total domains | |
| Non-seed domains | |
| Total personal-graph episodes ingested | |
| Total successful route jobs | |
| Total successful shared extract jobs | |
| Routed episodes in domain_knowledge | |
| Catch-all absorption % | |
| Novel docs that created non-seed domains | |
| Novel docs routed outside domain_knowledge | |
| Novel docs left unrouted | |
```
