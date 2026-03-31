# Stage 1: Infrastructure Setup

**Goal**: Start services fresh, create a shared graph `ncx_shared__project_titan`, and grant alice + bob read+write access.
**Dependencies**: None

---

## Steps

### 1.1 Start Services Fresh

```bash
./scripts/manage.sh stop --all
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens_test.json ./scripts/manage.sh start --fresh
```

Wait for health checks to pass on both MCP (port 8000) and Ingestion (port 8001).

### 1.2 Verify Health

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
curl -s http://127.0.0.1:8001/health | python3 -m json.tool
```

Both should return `{"status": "ok"}`.

### 1.3 Verify Baseline State (Empty)

Using ingest.sh:
```bash
.claude/skills/neocortex/scripts/ingest.sh --token alice-token list-graphs
```

Alice should have no graphs (fresh DB). If any exist, `--fresh` didn't work — re-run.

### 1.4 Create the Shared Graph

```bash
.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  setup-shared project_titan alice
```

This creates `ncx_shared__project_titan` and grants alice read+write.

### 1.5 Grant Bob Access

```bash
.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  grant bob ncx_shared__project_titan rw
```

### 1.6 Verify Permissions

```bash
.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  list-permissions alice

.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  list-permissions bob
```

Both should show `can_read: true, can_write: true` for `ncx_shared__project_titan`.

### 1.7 Record Baseline Job ID

Query the max procrastinate job ID so we can track extraction jobs later:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT coalesce(max(id), 0) FROM procrastinate_jobs;"
```

Record this value as `BASELINE_JOB_ID`.

---

## Verification

- [x] MCP server healthy on :8000
- [x] Ingestion API healthy on :8001
- [x] `ncx_shared__project_titan` appears in `list-graphs` output with `is_shared=true`
- [x] Alice has read+write on `ncx_shared__project_titan`
- [x] Bob has read+write on `ncx_shared__project_titan`
- [x] `BASELINE_JOB_ID` recorded → **0**

---

## Results

All checks passed. Services started fresh with `dev_tokens_test.json` (required manual
restart to bypass `.env` override of `NEOCORTEX_DEV_TOKENS_FILE`). Shared graph
`ncx_shared__project_titan` created, alice and bob both have rw access.

## Commit

No commit — validation-only stage. Record results in this file and update index.md.
