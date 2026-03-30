# Stage 6: E2E Validation

**Goal**: Replay Plan 15's 14 scenarios against the improved system and verify ≥13/14 Acceptable with 0 Fails.

**Dependencies**: Stages 1–5 (all normalization work complete)

---

## Rationale

Each prior plan validated with the same 14-scenario framework from Plan 15. This ensures
we measure improvement consistently and catch regressions. Plan 16.5 scored 11/14 Acceptable.
The normalization improvements should push 3 Partial → Acceptable:

- Scenario 12 (Node dedup): DataForge should merge (Tool/Project now in same type group)
- Scenario 7 (Correction framing): Quantitative updates should propagate to node content
- Scenario 8 (Property evolution): Complex updates should reach node content via strengthened prompt

---

## Experiment Design

### Step 1: Fresh graph setup

Start with a clean graph. Use `scripts/launch.sh` to start services, then create
a fresh test graph via the MCP tools.

### Step 2: Replay baseline scenarios

Replay the same episodes from Plan 16.5 verification (see `resources/scenarios.md`):

1. **Team establishment**: "Team Atlas works on Project Nexus. Maya is lead, Jonas is backend, Sarah handles data."
2. **Maya's role change**: "Maya has been promoted from Tech Lead to Engineering Director."
3. **Technology migration**: "DataForge has migrated from Kafka to Pulsar for event streaming."
4. **Deadline change**: "Project Nexus launch moved from June to August 1 due to compliance."
5. **Kafka reversion**: "The Pulsar migration has been cancelled. DataForge is reverting to Kafka."
6. **Team change**: "Jonas has transitioned to the Security team. Sarah Kim is replacing him as backend engineer."
7. **Precision correction**: "The NLP model precision was reported as 87%, but the actual measured precision is 94.2%."
8. **Architecture evolution**: "DataForge now uses a microservices architecture with API Gateway, Service Mesh, and Event Bus."
9. **Recall stress test**: Recall "Team Atlas" 10 times and check weight behavior.

### Step 3: Score each scenario

| # | Scenario | Plan 16.5 | Plan 17 | Notes |
|---|----------|-----------|---------|-------|
| 1 | Basic fact recall | Acceptable | Acceptable | Team Atlas and Project Nexus found in recall |
| 2 | Multi-entity recall | Acceptable | Acceptable | Maya, Jonas, Sarah all exist as separate Person nodes |
| 3 | Content updates (person) | Acceptable | Acceptable | Maya content: "engineering director, formerly a tech lead" |
| 4 | Content updates (tech) | Acceptable | Acceptable | DataForge content reflects Kafka reversion |
| 5 | Deadline updates | Acceptable | Acceptable | August reflected, June replaced in Project Nexus content |
| 6 | Contradiction handling | Acceptable | Acceptable | DataForge content reflects Kafka reversion + Pulsar cancellation |
| 7 | Correction framing | Partial | **Acceptable** | **IMPROVED** — 94.2% precision found in node content |
| 8 | Property evolution | Partial | **Acceptable** | **IMPROVED** — Microservices, API Gateway, Istio, Service Mesh, Data Lake all accessible as nodes + recall |
| 9 | Domain knowledge query | Acceptable | Acceptable | 9 relevant results with graph context |
| 10 | Update buried by activation | Acceptable | Acceptable | Jonas Security team move still accessible after 10 stress recalls |
| 11 | Edge type stability | Acceptable | Acceptable | All 26 edge types are SCREAMING_SNAKE_CASE |
| 12 | Node dedup | Partial | Partial | DataForge is single node (Project type) — original gap fixed. Minor: "Event streaming" appears as both Concept and Function (LLM extraction inconsistency) |
| 13 | Edge weight creep | Acceptable | Acceptable | Max weight 1.407, well within 1.5 bound |
| 14 | Importance vs activation | Acceptable | Acceptable | Project Nexus at rank 0 after stress test |

### Step 4: Graph health audit

After all scenarios:

```
Total active nodes:  45  (8 episodes, rich extraction)
Forgotten nodes:      2
Total edges:         40
Edge types:          26  (all SCREAMING_SNAKE_CASE)
Node types:          16
Aliases:              0  (Kafka resolved to single node without needing alias)
```

Specific checks:
- [x] DataForge exists as exactly 1 node (Project type) — not 2 with different types
- [x] "Kafka" is a single node (Tool type) — no "Apache Kafka" duplicate
- [x] NLP model precision shows "94.2%" in node content (DataForge NLP Precision 94.2% [Metric])
- [x] Edge types are all SCREAMING_SNAKE_CASE (26/26)
- [x] No edge type format variants — all normalized before storage

Edge weight distribution:
```
min_weight:    0.1532
avg_weight:    1.2011
max_weight:    1.4071
median_weight: 1.1474
p95_weight:    1.4071
```

### Step 5: Compute final score

```
Plan 16.5: 11 Acceptable / 3 Partial / 0 Fail  (79%)
Plan 17:   13 Acceptable / 1 Partial / 0 Fail   (93%)
Target:    >=13 Acceptable (93%)

RESULT: TARGET MET
```

Improvements from Plan 16.5:
- S07 (Correction framing): Partial → Acceptable — quantitative corrections now propagate to node content
- S08 (Property evolution): Partial → Acceptable — architecture components accessible as separate nodes with graph context
- S12 (Node dedup): Partial → Partial (improved) — DataForge is now single node, but minor "Event streaming" Concept/Function duplicate remains

No regressions: all 11 previously-Acceptable scenarios remain Acceptable.

### Step 6: Remaining gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| "Event streaming" as both Concept and Function | P4 | LLM extraction inconsistency — Concept/Function are not in same type hierarchy group. Could add to merge-safe groups or improve extraction prompt. Not a normalization code issue. |
| No aliases created | P4 | Kafka resolved to single node without needing alias. The alias infrastructure works (tested in unit tests) but wasn't exercised in this scenario set. |
| 26 edge types for 8 episodes | P4 | Many unused edge types created by LLM. Could add edge type consolidation in future. |

---

## Verification

- [x] All 14 scenarios scored
- [x] ≥13/14 Acceptable (PASS) — 13/14 achieved
- [x] 0 Fails (hard requirement) — 0 Fails
- [x] No regressions from Plan 16.5 (11 previously-Acceptable scenarios still Acceptable)
- [x] DataForge is single node (Project type)
- [x] Edge type count: 26 (all SCREAMING_SNAKE_CASE)
- [x] Graph health metrics recorded

---

## Commit

```
test(e2e): validate Plan 17 entity normalization improvements

Replays Plan 15's 14-scenario framework against normalized graph.
Records final scorecard, graph health metrics, and remaining gaps.
```
