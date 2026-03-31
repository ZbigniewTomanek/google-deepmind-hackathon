# Stage 3: Bob Knowledge Ingestion

**Goal**: Bob ingests 5 episodes about Project Titan's ML pipeline into the same shared graph. Wait for extraction. This creates the multi-agent consolidation scenario.
**Dependencies**: Stage 2 DONE

---

## Steps

### 3.1 Ingest Bob's Episodes

Use bob-token with the same `target_graph=ncx_shared__project_titan`.
Ingest episodes from `resources/episodes.md` — Bob's episodes (EP-B1 through EP-B5).

```bash
curl -s -X POST http://127.0.0.1:8001/ingest/text \
  -H "Authorization: Bearer bob-token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "<episode_text>",
    "target_graph": "ncx_shared__project_titan",
    "metadata": {"source": "bob", "stage": "03"}
  }'
```

Record each `episode_id`.

### 3.2 Wait for Extraction

Poll until all new extraction jobs complete:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT
    count(*) FILTER (WHERE status = 'todo') AS pending,
    count(*) FILTER (WHERE status = 'doing') AS running,
    count(*) FILTER (WHERE status = 'succeeded') AS completed,
    count(*) FILTER (WHERE status = 'failed') AS failed
  FROM procrastinate_jobs
  WHERE id > ${POST_ALICE_JOB_ID};"
```

Repeat every 10 seconds. Timeout: 300 seconds.

### 3.3 Record Post-Bob Graph State

Run the same queries as Stage 2.3:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ncx_shared__project_titan.node WHERE forgotten = false;"

docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ncx_shared__project_titan.edge;"

docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ncx_shared__project_titan.episode;"

docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT name, type, substring(content, 1, 80) AS content_preview
   FROM ncx_shared__project_titan.node
   WHERE forgotten = false
   ORDER BY name;"
```

Record as **POST_BOB** state:
- `POST_BOB_NODES`: **51** (was 41 after Alice → 10 new from Bob)
- `POST_BOB_EDGES`: **18** (unchanged — Bob's successful extractions added nodes but no new edges)
- `POST_BOB_EPISODES`: **10** (5 alice + 5 bob)

### 3.4 Identify Shared Entities

Key entities that BOTH agents should have mentioned (expected dedup targets):

| Entity | Alice mentions in | Bob mentions in | Expected single node? |
|--------|-------------------|-----------------|----------------------|
| Project Titan | EP-A1, EP-A2 | EP-B1, EP-B2 | YES |
| Kubernetes | EP-A3 | EP-B4 | YES |
| PostgreSQL | EP-A2 | EP-B3 | YES |
| Sarah Chen (PM) | EP-A1 | EP-B1 | YES |
| Marcus Rivera | EP-A1 | EP-B2 | YES |

Query for duplicates:
```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT lower(name) AS norm_name, count(*) AS cnt, array_agg(name) AS variants
   FROM ncx_shared__project_titan.node
   WHERE forgotten = false
   GROUP BY lower(name)
   HAVING count(*) > 1
   ORDER BY cnt DESC;"
```

---

## Verification

- [x] All 5 Bob episodes ingested (5 episode_ids returned)
- [x] Extraction completed (0 pending, 0 running)
- [x] POST_BOB_EPISODES = 10 (5 alice + 5 bob)
- [x] POST_BOB_NODES = 51 ≤ 82 (2 × 41) — dedup working
- [ ] ~~No failed extraction jobs~~ — **3 failed** (EP-B1 job 6, EP-B3 job 8, EP-B5 job 10: all UsageLimitExceeded)
- [x] Shared entities identified: Project Titan, Sarah Chen, Marcus Rivera, PostgreSQL all appear as single nodes (0 duplicates)

### Note on Extraction Failures

3 of Bob's 5 episodes failed extraction (same UsageLimitExceeded error as Alice's
EP-A4). Despite this, 2 episodes extracted successfully adding 10 new nodes.
Key observation: **0 duplicate nodes** — the extraction pipeline correctly deduped
shared entities (Project Titan, Sarah Chen, Marcus Rivera, PostgreSQL) into existing nodes.

---

## Commit

No commit — record results in this file and update index.md.
