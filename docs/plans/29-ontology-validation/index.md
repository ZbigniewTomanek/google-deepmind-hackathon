# Plan 29: Ontology Alignment Validation

| Field          | Value                                                   |
| -------------- | ------------------------------------------------------- |
| Date           | 2026-04-03                                              |
| Branch         | `ontology-alignment`                                    |
| Predecessors   | Plan 28 (ontology alignment)                            |
| Goal           | Validate that Plan 28's ontology alignment fixes produce clean, semantically meaningful knowledge graphs by ingesting diverse personal knowledge via CLI and measuring against quantitative success criteria |

---

## Context

### Problem Statement

Plan 28 implemented a 6-stage fix for ontology quality: type validation hardening,
domain-specific seed ontologies, agentic ontology agent, tuning/observability,
post-extraction type consolidation, and graph cleanup. All stages are DONE but
have only been validated in isolation (unit tests, manual spot checks). We need
end-to-end validation with realistic, diverse content to confirm the system
produces a clean ontology in practice.

### What We're Validating

The extraction pipeline processes text through 3 agents (ontology -> extractor -> librarian)
with domain routing to shared schemas. Plan 28 added:

1. **Validation layer** -- regex-based rejection of tool-call artifacts, instance-level
   type names, length/complexity limits
2. **Seed ontologies** -- 4 domain-specific type templates (user_profile, technical_knowledge,
   work_context, domain_knowledge) with 15-22 node types and 17-26 edge types each
3. **Agentic ontology agent** -- tool-using design with explore-validate-propose workflow
   (get_ontology_overview, find_similar_types, propose_type)
4. **Type consolidation** -- hardcoded merge map (8 mappings) + unused type archiving
5. **Improved prompts** -- type budget (max 2 node + 2 edge types per episode),
   reuse-over-creation guidance

### Why CLI Testing

The extraction pipeline runs asynchronously via job queue (Procrastinate). We need to:
- Restart the server between certain stages (fresh state, config changes)
- Monitor job completion via admin API (`GET /admin/jobs/summary`)
- Run diagnostic SQL directly against PostgreSQL
- Inspect logs for ontology agent behavior (`log/agent_actions.log`)

The embedded MCP server cannot be restarted mid-session, so all testing uses
`curl` against the ingestion API (:8001) and `docker compose exec` for SQL.

---

## Strategy

**Approach: Progressive complexity -- smoke test, multi-domain, adversarial, volume, then measure.**

**Phase A (Stage 1): Setup**
- Backup existing data, start fresh, verify clean state

**Phase B (Stages 2-5): Ingestion Testing**
- Stage 2: Single-document smoke test (verify basic pipeline works)
- Stage 3: Multi-domain ingestion (all 4 domains, verify routing + seed usage)
- Stage 4: Adversarial content (trigger known failure modes from Plan 28)
- Stage 5: Volume test (batch ingestion, consolidation triggers)

**Phase C (Stages 6-7): Assessment**
- Stage 6: Run diagnostic queries, compile metrics report vs Plan 28 targets
- Stage 7: Design targeted fixes for any failures

**Phase D (Stage 8): Re-validation**
- Fresh instance, re-run failed scenarios, verify fixes

### Trade-offs

**Why not automated pytest?** The extraction pipeline calls external LLMs (Gemini).
Results are non-deterministic. We need human judgment on whether types like
`HealthProtocol` vs `Protocol` are acceptable. Automated tests can check for
garbage but not semantic quality.

**Why restart between stages?** The ontology agent's behavior depends on existing
graph state. Testing in phases lets us observe how the ontology evolves
incrementally vs all-at-once.

---

## Success Criteria

Measured per schema after all ingestion completes (Stage 6):

| Metric | Baseline (Plan 28) | Target | Pass/Fail |
|--------|---------------------|--------|-----------|
| Node types with usage > 0 | ~90 | 25-35 | |
| Edge types with usage > 0 | ~140 | 30-50 | |
| Edge types with 0 usage (%) | ~70% | <15% | |
| Garbage types (tool artifacts) | ~8 | 0 | |
| Instance-level types | ~30 | 0 | |
| Type reuse ratio (nodes/active types) | ~7:1 | 20:1+ | |

Additional qualitative criteria:
- Domain routing assigns content to correct schemas
- Seed ontology types are actually used (not ignored)
- Ontology agent uses tools before proposing (visible in logs)
- No duplicate/near-duplicate types in final graph
- Edge types are semantically appropriate for personal knowledge

---

## Files That May Be Changed

### Test Resources (new)
- `docs/plans/29-ontology-validation/resources/test_documents.md` -- Test corpus
- `docs/plans/29-ontology-validation/resources/queries.md` -- Diagnostic SQL
- `docs/plans/29-ontology-validation/resources/commands.md` -- CLI commands reference

### Potential Fixes (Stage 7-8)
- `src/neocortex/normalization.py` -- Validation rule adjustments
- `src/neocortex/extraction/type_consolidation.py` -- Merge map updates
- `src/neocortex/extraction/agents.py` -- Prompt tuning
- `src/neocortex/domains/ontology_seeds.py` -- Seed ontology adjustments

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Environment Setup & Data Backup](stages/01-.md) | PENDING | | |
| 2 | [Single-Document Smoke Test](stages/02-.md) | PENDING | | |
| 3 | [Multi-Domain Ingestion](stages/03-.md) | PENDING | | |
| 4 | [Adversarial & Edge Case Testing](stages/04-.md) | PENDING | | |
| 5 | [Volume & Consolidation Testing](stages/05-.md) | PENDING | | |
| 6 | [Diagnostic Assessment & Report](stages/06-.md) | PENDING | | |
| 7 | [Fix Design & Implementation](stages/07-.md) | PENDING | | |
| 8 | [Re-validation of Failed Scenarios](stages/08-.md) | PENDING | | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** -- follow the link in the tracker to the stage's .md file
3. **Read resources** -- if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** -- if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Execute** -- run the commands described in the stage. All ingestion uses curl
   against http://localhost:8001. All SQL uses docker compose exec.
6. **Validate** -- run the verification checks listed in the stage.
   If validation fails, document the failure before proceeding.
7. **Update this index** -- mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** -- only commit if the stage produces code changes (Stages 7-8).
   Testing stages (1-6) update only this plan's notes.

**IMPORTANT**: Do not use the embedded MCP server for testing. All interactions
go through the REST API via curl. The server may need to be restarted between stages.

**IMPORTANT**: After ingesting documents, wait for extraction jobs to complete
before running diagnostic queries. Poll `GET /admin/jobs/summary` with
`Authorization: Bearer admin-token` until all jobs show `done` status.

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

*(None yet -- populated during execution)*

---

## Decisions

- **D1**: CLI-only testing (curl + psql) to allow server restarts between stages.
- **D2**: Progressive complexity -- single doc, multi-domain, adversarial, volume -- to isolate failure modes.
- **D3**: Human judgment on semantic quality, not just automated metrics. The metrics catch obvious failures; a human reviews type names for semantic appropriateness.
- **D4**: Fresh instance per major phase. Stage 1 starts fresh for Stages 2-6. Stage 8 starts fresh again for re-validation after fixes.
