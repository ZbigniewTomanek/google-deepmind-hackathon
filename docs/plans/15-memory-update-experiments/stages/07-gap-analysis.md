# Stage 7: Gap Analysis & Recommendations

**Goal**: Synthesize all experiment results. Compare against telegram bot and research recommendations.

---

## 7.1 Observed Behavior Summary

| Scenario | Observed Behavior | Acceptable? | Notes |
|----------|-------------------|-------------|-------|
| Basic recall | Works well. Targeted queries return stored facts. | Yes | Episodes + nodes both returned |
| Fact update (Alice's team) | New episode ranks #1, but Alice node still says "billing team" | Partial | Episode saves the day, node content stale |
| Entity dedup (1 node vs 2) | 1 Alice node (good). UPSERT by (name,type) works. | Yes | Node dedup is solid |
| Edge accumulation vs replacement | ADDITIVE only. Old `MEMBER_OF→Billing` coexists with new `MEMBER_OF→Auth` | No | No mechanism to mark old edges as superseded |
| Deadline contradiction | Both episodes returned, new ranks slightly higher (0.754 vs 0.742) | Partial | Score gap too small — an LLM might not notice which is current |
| Explicit correction | "CORRECTION:" episode ranks #1 (0.779) | Partial | Works because of keyword matching, not semantic understanding |
| Preference reversal | RabbitMQ (0.694) and Kafka (0.689) nearly identical scores | No | No signal that RabbitMQ decision was reversed |
| Property accumulation | All 3 WNP data points available across episodes | Yes | Episodes preserve all data points |
| Property conflict (pipeline stages) | 6-stage (#17, 0.703) ranks above 4-stage (#16, 0.688) | Partial | Both present, gap too small |
| Complex domain queries | Excellent. Rich recall with graph context spanning multiple entities. | Yes | The real strength of the system |
| Fact supersession (scaling exponent) | UPDATE episode (#23, b=0.62) ranked #8/10 — buried | No | Old context ranked higher due to activation |
| Importance effect | importance=1.0 fact ranked #2, below highly-activated episode | Partial | Activation can overwhelm importance |
| Recency effect | Newer episodes rank slightly higher | Partial | Effect is small, often drowned by activation |
| Activation (access count) | Score increases ~0.006 per recall. Cumulative effect significant. | Yes | ACT-R model works as designed |

### Verdict on individual scenarios:
- **5 of 14 acceptable** (35%)
- **6 of 14 partial** (43%) — works-ish, fragile
- **3 of 14 not acceptable** (21%) — clear failure modes

---

## 7.2 Comparison: NeoCortex vs Telegram Bot

| Capability | NeoCortex (Observed) | Telegram Bot | Gap Severity |
|-----------|---------------------|--------------|-------------|
| Fact deduplication | Node UPSERT by (name,type) — works | Deterministic SHA1 IDs — works | None |
| Contradiction handling | No mechanism. Both old+new coexist with similar scores | LLM-driven delta: explicit ADD/UPDATE/REMOVE | **Critical** |
| Content update | COALESCE keeps OLD value — node content never updates | LLM decides what's current | **Critical** |
| Temporal tracking | created_at, updated_at on nodes | first_seen, last_seen per fact | Minor (similar) |
| Fact lifecycle | No status field. Forgotten flag only for deletion. | active/archived/deprecated | **High** |
| Consolidation trigger | Extraction pipeline only (at remember time) | Scheduled batch (every 2 days) — reviews ALL facts | **High** |
| Source attribution | episode_id in properties (single source) | Deduplicated source list per fact | Minor |
| Delta semantics | Append-only episodes + additive edges | Structured ADD/UPDATE/REMOVE deltas | **Critical** |
| Stale data signal | None. Old facts look identical to new facts. | Explicit archival/deprecation | **Critical** |
| Cross-run dedup | Relies on Librarian agent (LLM-based, inconsistent) | Deterministic SHA1 IDs | Moderate |

### Key insight:
The telegram bot's fundamental advantage is **LLM-driven comparison against current state**. When a new fact arrives, the LLM explicitly decides: is this an ADD (new), UPDATE (modifies existing), or REMOVE (invalidates existing)? NeoCortex has no such comparison — it just appends episodes and hopes the extraction pipeline's UPSERT handles dedup.

---

## 7.3 Comparison: NeoCortex vs Research Recommendations

| Recommendation | Status in NeoCortex | Priority |
|---------------|---------------------|----------|
| CONTRADICTS edge type | Ontology agent creates the type, but extraction never produces these edges | P0 |
| LLM-driven consolidation cycles | Not implemented. Extraction is a one-shot pipeline, not a review cycle. | P0 |
| Ebbinghaus decay curve | Partial: recency factor (7-day half-life) in scoring. No actual forgetting. | P1 |
| Intelligent pruning / garbage collection | Not implemented. Episodes and nodes accumulate forever. | P1 |
| Access_History array | Only access_count (scalar). No temporal access pattern. | P2 |
| Utility_Score override | importance field with max-semantics (can't decrease). | P1 |
| Episodic → semantic promotion | Implemented via extraction pipeline. Works well. | Done |
| Spreading activation in recall | Implemented. Graph context in recall results is valuable. | Done |
| ACT-R base-level activation | Implemented. ln(access_count) - decay * ln(time_since_access). | Done |

---

## 7.4 Additional Issues Discovered

### Edge Type Instability (P0)
The extraction LLM changes edge types on every run. The same edge `Plan 36d → Metaphone3` was typed as:
- IMPLEMENTS (run 1)
- HAS_DEADLINE (run 2)
- FORMER_MEMBER_OF (run 3)
- FOLLOWS (run 4)
- EXTRACTS_FROM (run 5)

This makes the graph's relationship semantics meaningless. The UPSERT by `(source, target, type)` treats each re-typing as a NEW edge rather than updating the existing one.

### Node Type Drift (P1)
Same problem with node types. Metaphone3 was typed as: Person → Algorithm → Metric → Document → Fact. Plan 36d: Metric → Event → DesignPattern. The extraction LLM doesn't maintain type consistency across runs.

### Edge Weight Creep (P2)
Every recall adds +0.05 to edge weights via spreading activation. After many recalls, frequently-accessed subgraphs dominate scoring regardless of query relevance. Weights grew from 1.0 to 1.75+ during this experiment.

### Node Content Never Updates (P0)
Alice's content is still "Senior engineer on the billing team" despite 2 subsequent memories saying she moved to auth. COALESCE(new, old) only replaces when new is non-null, but the extraction pipeline provides content, so it should update. Investigation needed — possible COALESCE semantics issue or the Librarian not passing content for existing nodes.

### Duplicate Entity Names (P1)
"WNP Pruning Algorithm" exists as TWO separate nodes (id=53 and id=56) because they were extracted with different type_ids. The UPSERT key is `(name, type)`, so different types create duplicates.

---

## 7.5 Prioritized Recommendations

### P0 — Must-have for real usage

1. **Implement consolidation cycle** — Scheduled background process (like telegram bot's every-2-days cron) that reviews recent episodes against existing graph state. Uses LLM to generate deltas: what's new, what's updated, what's contradicted. This is the single most impactful change.

2. **Fix node content updates** — Content field must update when new, more specific information is available. Current COALESCE behavior preserves stale content.

3. **Fix edge type stability** — Either constrain the extraction LLM to reuse existing edge types (provide current schema as context), or use a coarser UPSERT key `(source, target)` that ignores type for dedup.

4. **Add staleness signals** — When a newer episode updates a fact, mark old episode/edges as stale or deprecated. Give the consuming LLM explicit signals about what's current vs historical.

### P1 — Important for quality

5. **Add fact lifecycle status** — `active/archived/deprecated` on nodes, similar to telegram bot's PersistentFact.status. Enable soft deprecation without data loss.

6. **Fix node type stability** — Constrain extraction to reuse existing types or implement type-agnostic node dedup by name alone.

7. **Implement importance decay** — Currently importance only goes up (max semantics). Allow re-evaluation during consolidation: old deadlines should lose importance when superseded.

8. **Cap edge weight growth** — Add a maximum weight or logarithmic scaling to prevent activation-driven weight creep.

### P2 — Nice to have

9. **Implement pruning** — Identify and merge redundant episodes. Remove old episodes that have been fully superseded by consolidated graph state.

10. **Add access_history array** — Track temporal access patterns for more sophisticated decay modeling.

11. **CONTRADICTS edge generation** — The type exists but is never used. During consolidation, when a new fact contradicts an old one, create an explicit CONTRADICTS edge.

---

## 7.6 Final Verdict

**Is NeoCortex ready for personal/team usage?**

**Partially. The system works well for knowledge accumulation but poorly for knowledge evolution.**

**What works:**
- Storing and recalling knowledge: excellent
- Graph structure with spreading activation: genuinely useful for complex queries
- Episode-based temporal ordering: provides some recency signal
- Multi-schema isolation: solid architecture for team use

**What doesn't work:**
- Updating facts: node content doesn't update, edges accumulate without cleanup
- Contradictions: no mechanism to resolve or signal them
- Stale data: old and new facts look identical in recall results
- Extraction quality: types drift randomly across runs, creating graph noise

**Minimum viable improvement for real usage:**
1. Fix content updates (P0, likely a small code change)
2. Constrain extraction type stability (P0, prompt engineering + schema context)
3. Add a consolidation cycle (P0, significant new feature — follow telegram bot's pattern)

Without these three, an agent using NeoCortex will increasingly struggle with stale knowledge as the graph grows. The system gets *worse* at accuracy as more facts are stored, because old facts accumulate and compete with new facts for recall ranking.

With these three, NeoCortex would be competitive with the telegram bot's approach while adding the significant advantages of graph structure, spreading activation, and multi-schema isolation.
