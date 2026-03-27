# E2E Extraction Pipeline — Reproduction Guide

Step-by-step instructions to reproduce the full end-to-end validation of the knowledge extraction pipeline. Starting from a clean database, this guide walks through ingesting a medical-domain corpus, running the 3-agent extraction pipeline, and verifying recall with graph context.

## Prerequisites

- Python 3.13 + [uv](https://docs.astral.sh/uv/)
- Docker (for PostgreSQL)
- `GOOGLE_API_KEY` set in `.env` (Gemini API — used for extraction agents + embeddings)

## 1. Start PostgreSQL

```bash
docker compose up -d postgres
```

Wait for healthy status:

```bash
docker ps --filter name=neocortex-postgres --format "{{.Status}}"
# Expected: Up ... (healthy)
```

## 2. Install dependencies

```bash
uv sync
```

## 3. Clean slate (optional)

If you've run the pipeline before and want a fresh start:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c "
  DROP SCHEMA IF EXISTS ncx_anonymous__personal CASCADE;
  DELETE FROM procrastinate_jobs;
  DELETE FROM graph_registry WHERE schema_name = 'ncx_anonymous__personal';
"
```

## 4. Start services

Open two terminal tabs (or run in background). Both read config from `.env`.

**MCP server** (port 8000) — hosts remember/recall/discover tools + Procrastinate worker:

```bash
set -a && source .env && set +a
NEOCORTEX_MOCK_DB=false uv run python -m neocortex
```

**Ingestion API** (port 8001) — REST endpoints for bulk ingestion:

```bash
set -a && source .env && set +a
NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion
```

Verify both are running:

```bash
lsof -i :8000 -i :8001 | grep LISTEN
```

You should see healthy startup logs including:

```
Connecting to PostgreSQL at localhost:5432
Connection pool created (min=2, max=10)
EmbeddingService initialized with model=gemini-embedding-001
Uvicorn running on http://...
```

## 5. Ingest the medical corpus

The seed corpus contains 10 medical-domain episodes covering neurotransmitters, pharmacology, neuroanatomy, and neuroplasticity.

```bash
uv run python -m neocortex.extraction.cli --ingest-corpus --base-url http://localhost:8001
```

Expected output:

```
Ingesting seed corpus to http://localhost:8001...
  [1/10] Serotonin and Mood Regulation — stored
  [2/10] SSRIs: Mechanism and Clinical Use — stored
  ...
  [10/10] Neuroplasticity and Pharmacological Intervention — stored
Done. Ingested 10 seed messages.
```

## 6. Monitor extraction progress

Each episode triggers a background extraction job (ontology agent -> extractor agent -> librarian agent). Each job takes ~60-90 seconds (3 sequential Gemini API calls).

**Job queue status:**

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex \
  -c "SELECT status, count(*) FROM procrastinate_jobs GROUP BY status;"
```

**Graph growth:**

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c "
  SELECT 'nodes' as type, count(*) FROM ncx_anonymous__personal.node
  UNION ALL SELECT 'edges', count(*) FROM ncx_anonymous__personal.edge
  UNION ALL SELECT 'node_types', count(*) FROM ncx_anonymous__personal.node_type
  UNION ALL SELECT 'edge_types', count(*) FROM ncx_anonymous__personal.edge_type;
"
```

**Server logs** (look for `extraction_start` / `extraction_complete`):

```bash
tail -f log/mcp.log
```

**Agent action audit trail** (JSON structured entries):

```bash
tail -f log/agent_actions.log
```

Wait until all 10 jobs show `succeeded`:

```
 status    | count
-----------+-------
 succeeded |    10
```

Expected final graph state (approximate — varies with Gemini output):

| Metric | Expected |
|--------|----------|
| Nodes | ~250 |
| Edges | ~260 |
| Node types | ~28 |
| Edge types | ~45 |

## 7. Validate recall with graph context

```python
import asyncio
from neocortex.tui.client import NeoCortexClient

async def test_recall():
    async with NeoCortexClient("http://localhost:8000") as client:
        result = await client.recall("serotonin", limit=10)
        for r in result["results"]:
            ctx = "with graph" if r.get("graph_context") else "no graph"
            print(f"  [{r['source_kind']}] {r['name']} (score={r['score']:.3f}, {ctx})")

asyncio.run(test_recall())
```

Run it:

```bash
uv run python -c "$(cat <<'PYEOF'
import asyncio
from neocortex.tui.client import NeoCortexClient

async def test_recall():
    async with NeoCortexClient("http://localhost:8000") as client:
        result = await client.recall("serotonin", limit=10)
        print(f"Total results: {result['total']}")
        for r in result["results"]:
            ctx = "with graph" if r.get("graph_context") else "no graph"
            print(f"  [{r['source_kind']}] {r['name']} (score={r['score']:.3f}, {ctx})")

asyncio.run(test_recall())
PYEOF
)"
```

**Verify:**

- Episode results ranked by hybrid score (vector + text + recency)
- Node results include `graph_context` with `center_node`, `neighbor_nodes`, and `edges`
- Serotonin-related episodes appear at top (Episode #1, #2, #6, #3)
- Graph context shows connections like Serotonin -> Raphe Nuclei, SSRIs -> Major Depressive Disorder, etc.

## 8. Validate discover

```bash
uv run python -c "
import asyncio
from neocortex.tui.client import NeoCortexClient

async def test():
    async with NeoCortexClient('http://localhost:8000') as client:
        result = await client.discover()
        s = result['stats']
        print(f'Nodes: {s[\"total_nodes\"]}, Edges: {s[\"total_edges\"]}, Episodes: {s[\"total_episodes\"]}')
        print(f'Node types ({len(result[\"node_types\"])}):')
        for t in sorted(result['node_types'], key=lambda x: x['count'], reverse=True)[:10]:
            print(f'  {t[\"name\"]}: {t[\"count\"]}')
        print(f'Edge types ({len(result[\"edge_types\"])}):')
        for t in sorted(result['edge_types'], key=lambda x: x['count'], reverse=True)[:10]:
            print(f'  {t[\"name\"]}: {t[\"count\"]}')

asyncio.run(test())
"
```

**Verify:**

- `total_nodes > 0`, `total_edges > 0`, `total_episodes == 10`
- Node types include medical domain types: AnatomicalStructure, Disease, Drug, Receptor, PhysiologicalFunction, etc.
- Edge types include: TREATS, ASSOCIATED_WITH, INHIBITS, FOUND_IN, REGULATES, etc.

## 9. Validate structured logging

After running recall/discover above, check the log files:

```bash
# Service log (human-readable)
cat log/mcp.log

# Agent action audit trail (JSON structured)
cat log/agent_actions.log | python -m json.tool
```

The audit trail should contain entries like:

```json
{
  "text": "recall_with_graph_traversal",
  "record": {
    "extra": {
      "action_log": true,
      "agent_id": "anonymous",
      "query": "serotonin",
      "total_results": 10,
      "node_results_with_context": 2
    }
  }
}
```

## 10. Validate TUI (optional)

```bash
uv run python -m neocortex.tui --url http://localhost:8000
```

- **Recall mode**: search for "serotonin" — should show episodes + graph context trees
- **Discover mode**: should show ontology with node/edge types and counts
- **Remember mode**: enter free text — should store and trigger extraction

## Troubleshooting

**`uv.toml` parse error**: If your global `~/.config/uv/uv.toml` has settings that cause parse errors, use `uv run --no-config` instead of `uv run`.

**Jobs stuck in `todo`**: Check that the MCP server (port 8000) is running — it hosts the Procrastinate worker that processes extraction jobs.

**Empty graph context in recall**: Extraction jobs may still be processing. Check job status (step 6) and wait for all to succeed.

**`GOOGLE_API_KEY` not set**: The extraction agents and embedding service require a valid Gemini API key. Ensure it's in `.env`.
