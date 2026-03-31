# Stage 4: Shared Graph Consolidation Check

**Goal**: Verify that the shared graph correctly consolidated knowledge from both agents — entities are deduplicated, complementary facts merged, and ontology is clean.
**Dependencies**: Stage 3 DONE

---

## Steps

### 4.1 Measure M1: Entity Deduplication Rate

For each shared entity (from Stage 3.4 table), check if it appears as a single node:

```bash
# Check each expected-shared entity
for entity in "Project Titan" "Kubernetes" "PostgreSQL" "Sarah Chen" "Marcus Rivera"; do
  echo "=== $entity ==="
  docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
    "SELECT name, type, substring(content, 1, 100) AS content_preview
     FROM ncx_shared__project_titan.node
     WHERE forgotten = false AND lower(name) LIKE lower('%${entity}%')
     ORDER BY name;"
done
```

**Scoring**:
- Single node for entity = DEDUP_SUCCESS
- Multiple nodes for same entity = DEDUP_FAIL
- Dedup rate = DEDUP_SUCCESS / total_shared_entities

**Target**: M1 ≥ 70% (≥ 4/5 shared entities appear as single nodes)

### 4.2 Measure M3: Complementary Fact Merge

For deduplicated entities, verify that content reflects knowledge from BOTH agents.

Example checks:
```bash
# Project Titan: should mention BOTH backend architecture (alice) AND ML pipeline (bob)
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT name, content FROM ncx_shared__project_titan.node
   WHERE forgotten = false AND lower(name) LIKE '%titan%';"

# Check edges: should have relationships from both alice's and bob's episodes
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT e.source_name, e.type, e.target_name, substring(e.content, 1, 60)
   FROM ncx_shared__project_titan.edge e
   WHERE lower(e.source_name) LIKE '%titan%' OR lower(e.target_name) LIKE '%titan%'
   ORDER BY e.type;"
```

**Scoring for each multi-facet entity**:
- Content mentions knowledge from BOTH agents = MERGE_SUCCESS
- Content only reflects one agent's perspective = MERGE_FAIL

**Target**: M3 ≥ 3/5

### 4.3 Measure M6: Type Quality

Check for corrupted or invalid type names:

```bash
# Node types
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT DISTINCT type, count(*) as cnt
   FROM ncx_shared__project_titan.node
   WHERE forgotten = false
   GROUP BY type ORDER BY cnt DESC;"

# Edge types
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT DISTINCT type, count(*) as cnt
   FROM ncx_shared__project_titan.edge
   GROUP BY type ORDER BY cnt DESC;"
```

**Corrupted type indicators**: contains special characters, length > 50, lowercase with spaces (should be SCREAMING_SNAKE_CASE for edges, PascalCase/snake_case for nodes).

**Target**: M6 = 0 corrupted types

### 4.4 Inspect Node Neighborhoods

For the most important shared entities, inspect their full neighborhood:

```bash
# Project Titan neighborhood
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT e.source_name, e.type, e.target_name
   FROM ncx_shared__project_titan.edge e
   JOIN ncx_shared__project_titan.node n ON (n.name = e.source_name OR n.name = e.target_name)
   WHERE n.forgotten = false
     AND (lower(e.source_name) LIKE '%titan%' OR lower(e.target_name) LIKE '%titan%')
   ORDER BY e.type;"
```

Record the full neighborhood map for Project Titan and Sarah Chen.

### 4.5 Episode-to-Node Mapping

Verify that episodes from both agents contributed to graph nodes:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT ep.agent_id, count(DISTINCT n.name) AS nodes_from_agent
   FROM ncx_shared__project_titan.episode ep
   JOIN ncx_shared__project_titan.node n ON n.forgotten = false
   GROUP BY ep.agent_id;"
```

Both alice and bob should show node contributions.

---

## Verification

- [ ] M1 computed: dedup rate = ___/5 (target ≥ 4/5)
- [ ] M3 computed: merge rate = ___/5 (target ≥ 3/5)
- [ ] M6 computed: corrupted types = ___ (target = 0)
- [ ] Node neighborhoods recorded for key entities
- [ ] Both agents show node contributions in the shared graph

---

## Commit

No commit — record results in this file and update index.md.
