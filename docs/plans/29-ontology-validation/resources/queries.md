# Diagnostic SQL Queries

All queries run against PostgreSQL via:
```bash
docker compose exec postgres psql -U neocortex -d neocortex
```

Replace `{schema}` with the actual schema name (e.g., `ncx_cc_work__personal`,
`ncx_shared__user_profile`, etc.).

---

## Schema Discovery

```sql
-- List all graph schemas
SELECT schema_name, agent_id, purpose, is_shared, created_at
FROM graph_registry
ORDER BY schema_name;
```

---

## Plan 28 Success Metrics — All-in-One

Run this for each schema to get all 6 metrics at once:

```sql
WITH active_node_types AS (
    SELECT COUNT(DISTINCT nt.id) AS cnt
    FROM {schema}.node_type nt
    JOIN {schema}.node n ON n.type_id = nt.id
),
active_edge_types AS (
    SELECT COUNT(DISTINCT et.id) AS cnt
    FROM {schema}.edge_type et
    JOIN {schema}.edge e ON e.type_id = et.id
),
all_edge_types AS (
    SELECT COUNT(DISTINCT id) AS cnt FROM {schema}.edge_type
),
unused_edge_types AS (
    SELECT COUNT(DISTINCT et.id) AS cnt
    FROM {schema}.edge_type et
    LEFT JOIN {schema}.edge e ON e.type_id = et.id
    WHERE e.id IS NULL
),
artifact_types AS (
    SELECT (
        SELECT COUNT(*) FROM {schema}.node_type
        WHERE name ~* '(functiondefault|calldefault|ApicreateOr|UpdateNode|UpdateEdge|createOrUpdate|defaultApi|endcall)'
    ) + (
        SELECT COUNT(*) FROM {schema}.edge_type
        WHERE name ~* '(functiondefault|calldefault|ApicreateOr|UpdateNode|UpdateEdge|createOrUpdate|defaultApi|endcall)'
    ) AS cnt
),
total_nodes AS (
    SELECT COUNT(*) AS cnt FROM {schema}.node
)
SELECT
    (SELECT cnt FROM active_node_types) AS active_node_types,
    (SELECT cnt FROM active_edge_types) AS active_edge_types,
    ROUND(
        (SELECT cnt FROM unused_edge_types)::numeric /
        NULLIF((SELECT cnt FROM all_edge_types), 0) * 100, 1
    ) AS unused_edge_type_pct,
    (SELECT cnt FROM artifact_types) AS garbage_types,
    ROUND(
        (SELECT cnt FROM total_nodes)::numeric /
        NULLIF((SELECT cnt FROM active_node_types), 0), 1
    ) AS type_reuse_ratio;
```

---

## Individual Metrics

### 1. Active Node Types (target: 25-35)

```sql
SELECT nt.name, COUNT(n.id) AS usage
FROM {schema}.node_type nt
LEFT JOIN {schema}.node n ON n.type_id = nt.id
GROUP BY nt.id, nt.name
ORDER BY usage DESC;
```

### 2. Active Edge Types (target: 30-50)

```sql
SELECT et.name, COUNT(e.id) AS usage
FROM {schema}.edge_type et
LEFT JOIN {schema}.edge e ON e.type_id = et.id
GROUP BY et.id, et.name
ORDER BY usage DESC;
```

### 3. Unused Edge Types (target: <15%)

```sql
SELECT et.name, et.created_at
FROM {schema}.edge_type et
LEFT JOIN {schema}.edge e ON e.type_id = et.id
WHERE e.id IS NULL
ORDER BY et.name;
```

### 4. Garbage Types — Tool-Call Artifacts (target: 0)

```sql
-- Node types
SELECT name FROM {schema}.node_type
WHERE name ~* '(functiondefault|calldefault|ApicreateOr|UpdateNode|UpdateEdge|createOrUpdate|defaultApi|endcall)';

-- Edge types
SELECT name FROM {schema}.edge_type
WHERE name ~* '(functiondefault|calldefault|ApicreateOr|UpdateNode|UpdateEdge|createOrUpdate|defaultApi|endcall)';
```

### 5. Instance-Level Types (target: 0)

```sql
-- Heuristic: multi-segment PascalCase where first segment is a known base type
-- Manual review needed — query returns candidates, human judges
SELECT name FROM {schema}.node_type
WHERE name ~ '^[A-Z][a-z]+[A-Z]'  -- at least 2 PascalCase segments
  AND name !~ '^(Body|Health|Architecture|Food|Flavor|Preparation|Financial|Medical|Benchmark|Professional|Configuration|Workflow)' -- skip known compounds
ORDER BY name;
```

### 6. Type Reuse Ratio (target: 20:1+)

```sql
SELECT
    COUNT(n.id) AS total_nodes,
    COUNT(DISTINCT n.type_id) AS active_types,
    ROUND(COUNT(n.id)::numeric / NULLIF(COUNT(DISTINCT n.type_id), 0), 1) AS reuse_ratio
FROM {schema}.node n;
```

---

## Qualitative Checks

### Seed Type Usage

Check whether seed types from `ontology_seeds.py` are actually being used:

```sql
-- Node types from seeds that have 0 usage (should be low)
SELECT nt.name
FROM {schema}.node_type nt
LEFT JOIN {schema}.node n ON n.type_id = nt.id
WHERE nt.name IN (
    'Person', 'Location', 'HealthState', 'Routine', 'Dream', 'Substance',
    'Symptom', 'Emotion', 'Trip', 'FoodItem', 'Ingredient', 'MediaWork',
    'Vehicle', 'Reflection', 'Interest', 'Contract', 'FinancialEvent',
    'BodyPart', 'Specification', 'Insight', 'Skill', 'Protocol',
    'Tool', 'Component', 'Concept', 'Schema', 'DataFormat', 'Model',
    'Algorithm', 'Infrastructure', 'ConfigurationSetting', 'Strategy',
    'Rule', 'BenchmarkResult', 'Repository', 'Issue', 'WorkflowStep',
    'ArchitecturePattern', 'Discipline',
    'Project', 'Task', 'Organization', 'Epic', 'Ticket', 'Benchmark',
    'Presentation', 'Company', 'ProfessionalRole', 'Article', 'Hackathon',
    'Salary', 'Benefit', 'Challenge', 'ReviewProcess', 'ResearchProject',
    'Experiment', 'Phase',
    'Dish', 'PreparationTechnique', 'Utensil', 'FlavorProfile',
    'FoodCategory', 'Publication', 'Service', 'Brand', 'Agreement',
    'Supplement', 'Condition', 'MedicalReport'
)
GROUP BY nt.id, nt.name
HAVING COUNT(n.id) = 0
ORDER BY nt.name;
```

### Near-Duplicate Detection

```sql
-- Node types that share a common prefix (potential duplicates)
SELECT a.name AS type_a, b.name AS type_b
FROM {schema}.node_type a
JOIN {schema}.node_type b ON a.id < b.id
WHERE LEFT(a.name, 4) = LEFT(b.name, 4)
  AND a.name != b.name
ORDER BY a.name;
```

### Semantically Inappropriate Edge Types

```sql
-- Edge types that seem wrong for personal knowledge (manual review)
SELECT et.name, COUNT(e.id) AS usage
FROM {schema}.edge_type et
LEFT JOIN {schema}.edge e ON e.type_id = et.id
GROUP BY et.id, et.name
HAVING COUNT(e.id) > 0
ORDER BY et.name;
```

---

## Job Monitoring

```sql
-- Extraction job status summary
SELECT status, COUNT(*) AS cnt
FROM procrastinate_jobs
WHERE task_name IN ('extract_episode', 'route_episode')
GROUP BY status
ORDER BY status;

-- Failed jobs with error details
SELECT id, task_name, args, status, attempts,
       events->(jsonb_array_length(events)-1)->>'message' AS last_error
FROM procrastinate_jobs
WHERE status = 'failed'
ORDER BY id DESC
LIMIT 10;
```
