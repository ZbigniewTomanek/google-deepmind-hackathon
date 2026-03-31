# Stage 2: Alice Knowledge Ingestion

**Goal**: Alice ingests 5 episodes about Project Titan's backend architecture into the shared graph. Wait for extraction to complete.
**Dependencies**: Stage 1 DONE

---

## Steps

### 2.1 Ingest Alice's Episodes

Use the ingestion API with alice-token and `target_graph=ncx_shared__project_titan`.
Ingest episodes from `resources/episodes.md` — Alice's episodes (EP-A1 through EP-A5).

For each episode:
```bash
.claude/skills/neocortex/scripts/ingest.sh \
  --token alice-token \
  --target ncx_shared__project_titan \
  text "<episode_text>"
```

Or via curl for longer texts:
```bash
curl -s -X POST http://127.0.0.1:8001/ingest/text \
  -H "Authorization: Bearer alice-token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "<episode_text>",
    "target_graph": "ncx_shared__project_titan",
    "metadata": {"source": "alice", "stage": "02"}
  }'
```

**Important**: Record each `episode_id` returned.

### 2.2 Wait for Extraction

Poll the procrastinate jobs table until all extraction jobs from Alice's episodes complete:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT
    count(*) FILTER (WHERE status = 'todo') AS pending,
    count(*) FILTER (WHERE status = 'doing') AS running,
    count(*) FILTER (WHERE status = 'succeeded') AS completed,
    count(*) FILTER (WHERE status = 'failed') AS failed
  FROM procrastinate_jobs
  WHERE id > ${BASELINE_JOB_ID};"
```

Repeat every 10 seconds until `pending=0` and `running=0`. Timeout: 300 seconds.

### 2.3 Record Post-Alice Graph State

```bash
# Node count in shared graph
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ncx_shared__project_titan.node WHERE forgotten = false;"

# Edge count
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ncx_shared__project_titan.edge;"

# Episode count
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ncx_shared__project_titan.episode;"

# Node types
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT DISTINCT type FROM ncx_shared__project_titan.node WHERE forgotten = false ORDER BY type;"

# All node names
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT name, type, substring(content, 1, 80) AS content_preview
   FROM ncx_shared__project_titan.node
   WHERE forgotten = false
   ORDER BY name;"
```

Record as **POST_ALICE** baseline:
- `POST_ALICE_NODES`: ___
- `POST_ALICE_EDGES`: ___
- `POST_ALICE_EPISODES`: ___
- `POST_ALICE_TYPES`: [list]

### 2.4 Update New Baseline Job ID

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT coalesce(max(id), 0) FROM procrastinate_jobs;"
```

Record as `POST_ALICE_JOB_ID`.

---

## Verification

- [ ] All 5 Alice episodes ingested (5 episode_ids returned)
- [ ] Extraction completed (0 pending, 0 running, ≥5 completed jobs)
- [ ] Shared graph has nodes (POST_ALICE_NODES > 0)
- [ ] Shared graph has edges (POST_ALICE_EDGES > 0)
- [ ] No failed extraction jobs
- [ ] Node types are valid (no corrupted names)

---

## Commit

No commit — record results in this file and update index.md.
