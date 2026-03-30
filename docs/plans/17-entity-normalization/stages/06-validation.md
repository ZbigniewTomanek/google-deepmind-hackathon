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
| 1 | Basic fact recall | Acceptable | | |
| 2 | Multi-entity recall | Acceptable | | |
| 3 | Content updates (person) | Acceptable | | |
| 4 | Content updates (tech) | Acceptable | | |
| 5 | Deadline updates | Acceptable | | |
| 6 | Contradiction handling | Acceptable | | |
| 7 | Correction framing | Partial | | Target: Acceptable |
| 8 | Property evolution | Partial | | Target: Acceptable |
| 9 | Domain knowledge query | Acceptable | | |
| 10 | Update buried by activation | Acceptable | | |
| 11 | Edge type stability | Acceptable | | |
| 12 | Node dedup | Partial | | Target: Acceptable (DataForge single node) |
| 13 | Edge weight creep | Acceptable | | |
| 14 | Importance vs activation | Acceptable | | |

### Step 4: Graph health audit

After all scenarios, check:

```
Total nodes: __ (expect < 74, improvement from dedup)
Total edges: __ (expect similar ~69)
Edge types: __ (expect < 25, improvement from normalization)
Node types: __ (expect < 16, improvement from normalization)
```

Specific checks:
- [ ] DataForge exists as exactly 1 node (not 2)
- [ ] "Kafka" and "Apache Kafka" resolve to same node or are aliased
- [ ] NLP model precision shows "94.2%" in node content
- [ ] Edge types are all SCREAMING_SNAKE_CASE
- [ ] No edge type format variants (no "RelatesTo" + "RELATES_TO")

### Step 5: Compute final score

```
Plan 16.5: 11 Acceptable / 3 Partial / 0 Fail  (79%)
Plan 17:   __/14 Acceptable / __/14 Partial / __/14 Fail
Target:    ≥13 Acceptable (93%)
```

### Step 6: Remaining gaps

Document any issues that Plan 17 did NOT fix:

| Gap | Severity | Notes |
|-----|----------|-------|
| | | |

---

## Verification

- [ ] All 14 scenarios scored
- [ ] ≥13/14 Acceptable (PASS) or document why target not met
- [ ] 0 Fails (hard requirement)
- [ ] No regressions from Plan 16.5 (11 previously-Acceptable scenarios still Acceptable)
- [ ] DataForge is single node
- [ ] Edge type count < 25
- [ ] Graph health metrics recorded

---

## Commit

```
test(e2e): validate Plan 17 entity normalization improvements

Replays Plan 15's 14-scenario framework against normalized graph.
Records final scorecard, graph health metrics, and remaining gaps.
```
