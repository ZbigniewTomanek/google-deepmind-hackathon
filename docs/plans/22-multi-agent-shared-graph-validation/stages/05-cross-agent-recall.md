# Stage 5: Cross-Agent Recall Validation

**Goal**: Verify that both alice and bob can recall knowledge contributed by the other agent from the shared graph, and that recall quality is good.
**Dependencies**: Stage 4 DONE

---

## Steps

### 5.1 Define 10 Recall Queries

Mix of queries that target alice-only knowledge, bob-only knowledge, and overlapping knowledge:

| # | Query | Expected Source | Tests |
|---|-------|-----------------|-------|
| Q1 | "What database does Project Titan use for storage?" | Alice (EP-A2) | Bob recalls alice's knowledge |
| Q2 | "What ML model is used for feature engineering?" | Bob (EP-B2) | Alice recalls bob's knowledge |
| Q3 | "Who is the project manager for Titan?" | Both (EP-A1, EP-B1) | Dedup recall |
| Q4 | "How is the API gateway architected?" | Alice (EP-A3) | Bob recalls alice's infra knowledge |
| Q5 | "What data quality metrics are tracked?" | Bob (EP-B3) | Alice recalls bob's ML knowledge |
| Q6 | "What are the project deadlines?" | Both (EP-A1, EP-B1) | Cross-agent temporal info |
| Q7 | "How is Kubernetes used in the deployment?" | Both (EP-A3, EP-B4) | Merged infra knowledge |
| Q8 | "What is Marcus Rivera's role?" | Both (EP-A1, EP-B2) | Person entity dedup recall |
| Q9 | "Describe the data ingestion pipeline" | Bob (EP-B1) | Alice recalls bob's pipeline design |
| Q10 | "What monitoring and observability tools are used?" | Alice (EP-A4) | Bob recalls alice's ops knowledge |

### 5.2 Execute Queries as Alice

For each query, call recall via MCP as alice:

```bash
# Using ingest.sh or direct curl to MCP
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer alice-token" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "recall",
      "arguments": {"query": "<query_text>", "limit": 5}
    },
    "id": 1
  }'
```

**Alternative**: Use the TUI or a Python one-liner with fastmcp Client:
```bash
uv run python -c "
import asyncio
from fastmcp import Client

async def q():
    async with Client('http://127.0.0.1:8000/mcp', auth='alice-token') as c:
        r = await c.call_tool('recall', {'query': '<query>', 'limit': 5})
        print(r.structured_content)

asyncio.run(q())
"
```

Record for each query:
- Top result name, score, activation_score
- Whether the result contains knowledge from the OTHER agent
- Overall relevance (RELEVANT / PARTIAL / IRRELEVANT)

### 5.3 Execute Queries as Bob

Repeat the same 10 queries using bob-token. Record the same data.

### 5.4 Measure M2: Cross-Agent Recall

For each query:
- PASS if at least one result in top 5 contains knowledge from the other agent's episodes
- FAIL if no cross-agent knowledge appears

**Target**: M2 ≥ 8/10 queries return cross-agent results for at least one of the two agents.

### 5.5 Measure M7: Activation Score Sanity

Across all queries from both agents, record the maximum activation_score observed.

**Target**: M7 ≤ 0.80 (no single item dominates shared recall)

### 5.6 Compare Alice vs Bob Result Rankings

For the 5 queries targeting overlapping knowledge (Q3, Q6, Q7, Q8, Q10):
- Do alice and bob get the same top result?
- Are scores similar (within 0.1)?
- Any systematic bias toward one agent's content?

Record as a comparison table.

---

## Verification

- [ ] All 10 queries executed as alice (results recorded)
- [ ] All 10 queries executed as bob (results recorded)
- [ ] M2 computed: ___/10 cross-agent recall passes (target ≥ 8)
- [ ] M7 computed: max activation = ___ (target ≤ 0.80)
- [ ] No systematic bias in overlapping queries
- [ ] All queries returned at least 1 result (no empty recalls)

---

## Commit

No commit — record results in this file and update index.md.
