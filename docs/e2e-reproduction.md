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

The seed corpus contains 3 medical-domain episodes covering neurotransmitters, pharmacology, and sexual function.

```bash
uv run python -m neocortex.extraction.cli --ingest-corpus --base-url http://localhost:8001
```

Expected output:

```
Ingesting seed corpus to http://localhost:8001...
  [1/3] Serotonin and Mood Regulation — stored
  [2/3] SSRIs: Mechanism and Clinical Use — stored
  [3/3] SSRI-Induced Sexual Dysfunction — stored
Done. Ingested 3 seed messages.
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

Wait until all 3 jobs show `succeeded`:

```
 status    | count
-----------+-------
 succeeded |     3
```

Expected final graph state (approximate — varies with Gemini output):

| Metric | Expected |
|--------|----------|
| Nodes | ~75 |
| Edges | ~80 |
| Node types | ~10 |
| Edge types | ~15 |

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

- Node results include `graph_context` with `center_node`, `neighbor_nodes`, and `edges`
- Each result has `activation_score`, `importance`, and `spreading_bonus` fields
- High-importance graph nodes outrank consolidated episodes
- Graph context shows connections like Serotonin -> Raphe Nuclei, SSRIs -> Major Depressive Disorder, etc.

## 7b. Validate cognitive heuristics in recall

After the initial recall in step 7, run the same query 2 more times and observe how the heuristics evolve:

```bash
# Run recall 3 times in sequence — activation should increase each time
for i in 1 2 3; do
  echo "=== Recall #$i ==="
  uv run python -c "
import asyncio
from neocortex.tui.client import NeoCortexClient

async def run():
    async with NeoCortexClient('http://localhost:8000') as client:
        r = await client.recall('serotonin', limit=5)
        for item in r['results']:
            act = item.get('activation_score', 'N/A')
            imp = item.get('importance', 'N/A')
            bonus = item.get('spreading_bonus', 'N/A')
            print(f'  {item[\"name\"][:45]:45s} score={item[\"score\"]:.3f} act={act} imp={imp} bonus={bonus}')

asyncio.run(run())
"
done
```

**Verify:**

- **ACT-R activation increases**: `activation_score` rises with each recall (~0.49 -> ~0.67 -> ~0.75) as `access_count` increments
- **Spreading activation**: results include `spreading_bonus > 0` for neighbors of matched nodes (discovered via graph edges, not text match)
- **Importance scoring**: nodes with higher `importance` (assigned by extraction agents) rank above nodes with lower importance, all else being equal
- **Consolidation penalty**: consolidated episodes (all 10 after extraction) rank below graph nodes for the same query

**Verify edge reinforcement** after the 3 recalls above:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c "
  SELECT src.name, tgt.name, e.weight
  FROM ncx_anonymous__personal.edge e
  JOIN ncx_anonymous__personal.node src ON src.id = e.source_id
  JOIN ncx_anonymous__personal.node tgt ON tgt.id = e.target_id
  WHERE e.weight > 1.0 ORDER BY e.weight DESC LIMIT 5;
"
```

Edges traversed during recall should have weight > 1.0 (reinforced by 0.05 per recall traversal).

**Verify importance_hint propagation** via remember with explicit importance:

```bash
uv run python -c "
import asyncio
from neocortex.tui.client import NeoCortexClient

async def run():
    async with NeoCortexClient('http://localhost:8000') as client:
        await client._client.call_tool('remember', {
            'text': 'Lithium is a critical mood stabilizer for bipolar disorder',
            'importance': 0.95
        })
        # Wait for extraction, then check:
        # All extracted entities should have importance >= 0.95 (floor from hint)

asyncio.run(run())
"
```

After the extraction job completes, verify:

```bash
docker exec neocortex-postgres psql -U neocortex -d neocortex -c "
  SELECT name, importance FROM ncx_anonymous__personal.node
  WHERE properties->>'_source_episode' = (
    SELECT max(id)::text FROM ncx_anonymous__personal.episode
  );
"
```

All nodes from that episode should have `importance >= 0.95`.

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
        print(f'Forgotten nodes: {s.get(\"forgotten_nodes\", \"N/A\")}')
        print(f'Consolidated episodes: {s.get(\"consolidated_episodes\", \"N/A\")}')
        print(f'Avg activation: {s.get(\"avg_activation\", \"N/A\")}')
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
- `forgotten_nodes == 0` (all nodes are fresh), `consolidated_episodes == 10` (all extracted)
- `avg_activation > 0` if you've run recalls (reflects access_count across nodes)
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
