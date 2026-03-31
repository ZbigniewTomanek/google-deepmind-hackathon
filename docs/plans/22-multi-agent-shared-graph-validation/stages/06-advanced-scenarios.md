# Stage 6: Advanced Scenarios

**Goal**: Test conflict resolution between agents, permission boundaries, and edge cases.
**Dependencies**: Stage 5 DONE

---

## Steps

### 6.1 Scenario A: Conflicting Facts

Alice and Bob will ingest contradictory information about the same entity.

**Alice's assertion** (ingest via alice-token):
```
"The Project Titan production deployment target date has been confirmed as July 15, 2026.
Sarah Chen announced this at the last all-hands meeting. The backend services must be
feature-complete by June 30, 2026."
```

**Bob's assertion** (ingest via bob-token, AFTER alice):
```
"CORRECTION: Project Titan deployment has been pushed to August 1, 2026 due to the
ML model validation timeline. Sarah Chen confirmed the new date in today's standup.
The original July 15 date was too aggressive for the feature engineering pipeline."
```

Wait for extraction (poll jobs).

**Verify (M4)**:
```bash
# Recall the date
uv run python -c "
import asyncio
from fastmcp import Client

async def q():
    async with Client('http://127.0.0.1:8000/mcp', auth='alice-token') as c:
        r = await c.call_tool('recall', {'query': 'Project Titan deployment date', 'limit': 5})
        for item in r.structured_content.get('results', []):
            print(f\"Score: {item.get('score', 'N/A'):.3f}  Name: {item.get('name', 'N/A')}\")
            print(f\"  Content: {str(item.get('content', ''))[:120]}\")
            print()

asyncio.run(q())
"
```

Expected: August 1 (Bob's correction) should rank above July 15 (Alice's original) due to
recency and CORRECTION signal. Check for SUPERSEDES edge if present.

### 6.2 Scenario B: Importance Override

Alice ingests a LOW importance fact, Bob ingests a HIGH importance correction:

**Alice** (importance not specified, defaults to 0.5):
```bash
curl -s -X POST http://127.0.0.1:8001/ingest/text \
  -H "Authorization: Bearer alice-token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The data pipeline uses Apache Kafka for stream processing. This was decided early in the project.",
    "target_graph": "ncx_shared__project_titan"
  }'
```

Wait 10 seconds. Then **Bob** (high importance):
```bash
curl -s -X POST http://127.0.0.1:8001/ingest/text \
  -H "Authorization: Bearer bob-token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "IMPORTANT: We are migrating from Kafka to Apache Pulsar for the data pipeline. Kafka cannot handle our partition requirements for the ML feature store. This migration is P0 priority.",
    "target_graph": "ncx_shared__project_titan",
    "metadata": {"importance": 0.9}
  }'
```

Wait for extraction. Recall "streaming platform for data pipeline" — Pulsar should rank above Kafka.

### 6.3 Scenario C: Permission Boundary (Eve)

Verify eve cannot access the shared graph:

```bash
# Eve tries to recall — should NOT see shared graph content
uv run python -c "
import asyncio
from fastmcp import Client

async def q():
    async with Client('http://127.0.0.1:8000/mcp', auth='eve-token') as c:
        r = await c.call_tool('recall', {'query': 'Project Titan', 'limit': 5})
        results = r.structured_content.get('results', [])
        print(f'Eve got {len(results)} results')
        for item in results:
            print(f\"  {item.get('name', 'N/A')}: {str(item.get('content', ''))[:80]}\")

asyncio.run(q())
"
```

Expected: Eve gets 0 results (no access to shared graph, no personal graph).

```bash
# Eve tries to write — should fail
curl -s -X POST http://127.0.0.1:8001/ingest/text \
  -H "Authorization: Bearer eve-token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Eve should not be able to write here",
    "target_graph": "ncx_shared__project_titan"
  }'
```

Expected: HTTP 403 or permission error.

### 6.4 Scenario D: Read-Only Bob (Temporary)

Downgrade Bob to read-only, verify he can still recall but not write:

```bash
# Revoke bob's current permission
.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  revoke bob ncx_shared__project_titan

# Re-grant as read-only
.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  grant bob ncx_shared__project_titan r
```

```bash
# Bob recalls — should still work
uv run python -c "
import asyncio
from fastmcp import Client

async def q():
    async with Client('http://127.0.0.1:8000/mcp', auth='bob-token') as c:
        r = await c.call_tool('recall', {'query': 'Project Titan architecture', 'limit': 3})
        results = r.structured_content.get('results', [])
        print(f'Bob read-only recall: {len(results)} results')

asyncio.run(q())
"
```

```bash
# Bob writes — should fail
curl -s -X POST http://127.0.0.1:8001/ingest/text \
  -H "Authorization: Bearer bob-token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bob should not be able to write in read-only mode",
    "target_graph": "ncx_shared__project_titan"
  }'
```

Expected: Recall succeeds, write returns 403.

**Restore Bob's write access after test:**
```bash
.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  revoke bob ncx_shared__project_titan

.claude/skills/neocortex/scripts/ingest.sh --admin-token admin-token-neocortex \
  grant bob ncx_shared__project_titan rw
```

---

## Verification

- [ ] Scenario A: Correction (Aug 1) ranks above original (Jul 15) in recall
- [ ] Scenario B: High-importance Pulsar ranks above low-importance Kafka
- [ ] Scenario C: Eve gets 0 recall results and 403 on write
- [ ] Scenario D: Read-only Bob can recall but gets 403 on write
- [ ] M4 computed: ___/3 conflict queries resolved correctly (target ≥ 2/3)
- [ ] M5 computed: 0 unauthorized accesses (target = 0)

---

## Commit

No commit — record results in this file and update index.md.
