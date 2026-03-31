# Episode Data -- 28 Episodes for E2E Re-Validation

Source material: `/Users/zbigniewtomanek/PycharmProjects/datawalk-entity-resolution`

Each episode includes: ID, phase label, importance, and the exact text to pass to `remember`.

---

## Phase 1: Onboarding (Jan 2026) -- 8 episodes

### Episode 1 -- Project Overview
**Importance**: 0.7
**Context**: "e2e_revalidation_phase1"

```
Started working on DataWalk Entity Resolution -- a production system for deduplicating and linking entity records at scale. The system implements a hybrid architecture: Stage 1 uses deterministic rules with Vertica UDXs for normalization and feature extraction, Stage 2 uses probabilistic scoring based on the Fellegi-Sunter model for pair comparison. The target scale is 252 million entities across person and organization types. The system runs entirely inside Vertica (columnar MPP database) using SQL + custom UDX functions, with Python orchestration. Configuration is driven by atomic YAML files so field engineers can tune rules without code changes.
```

### Episode 2 -- Team Composition
**Importance**: 0.6
**Context**: "e2e_revalidation_phase1"

```
Met the DataWalk ER team today. Tomek Zbigniew is the tech lead and primary architect. Anya Kowalski handles the Vertica infrastructure and projection optimization. Jonas Weber is the backend engineer working on the normalization pipeline and blocking rules. Sarah Kim specializes in data quality and the evaluation framework. The team follows TDD-first development with pytest, and uses Poetry for Python dependency management. Key principle: "researcher mode" -- prioritize quality metrics (Precision, Recall, F1) over code polish.
```

### Episode 3 -- Fellegi-Sunter Fundamentals
**Importance**: 0.8
**Context**: "e2e_revalidation_phase1"

```
Deep dive into the Fellegi-Sunter probabilistic record linkage model that powers Stage 2 scoring. Core concepts: m-probability (agreement probability given true match), u-probability (agreement probability given non-match), and the Bayes Factor (likelihood ratio m/u). The model assumes Conditional Independence between features (CIA) -- a known simplification. Key insight: features with high information content (IC) measured in Shannon entropy bits are most discriminative. The system uses Term Frequency Adjustments for non-uniform distributions (common names like "Smith" get lower weight). Parameters estimated via EM algorithm with convergence stabilization. Mathematical details in docs/Fellegi-Sunter Model Research.md (4000+ lines).
```

### Episode 4 -- Normalized Tables Architecture
**Importance**: 0.7
**Context**: "e2e_revalidation_phase1"

```
Stage 1 produces ~15 normalized tables from raw entity data. Key tables: person_normalized_data (core attributes via ParseHumanName, ParseDate, FixUnicodeText UDXs), phones_normalized (E.164 format via ParsePhoneNumber), addresses_normalized (Libpostal normalization), online_identities_normalized (email/website domain extraction), identifiers_normalized (SSN, passport, NPI validation). All CREATE TABLE statements include ORDER BY + SEGMENTED BY clauses for local joins. Feature tables have buddy projections segmented by entity_object_id for scoring co-location. Blocking projections ordered by (feature_value, delta_batch_id, entity_object_id).
```

### Episode 5 -- Feature Catalog
**Importance**: 0.6
**Context**: "e2e_revalidation_phase1"

```
Reviewed the feature engineering specification. The system defines 39 atomic features for person entities and 27 for organization entities. Person features span: name components (given, family, full name similarity), date of birth (exact, year, decade), phone (E.164 normalized, country code), email (full, domain, local part), address (street, city, postal, country), and identifiers (SSN, passport, NPI). Organization features cover: legal name, trade name, business ID, incorporation details. There are also 15 composite features combining multiple atomics (e.g., NAMEPHONE = phonetic_family_name + phone_e164, NAMEDATE = phonetic_given + birth_year). Each feature has per-entity regex exclusion patterns to filter garbage values (keyboard walks, system defaults, repeating chars).
```

### Episode 6 -- Blocking Strategy
**Importance**: 0.7
**Context**: "e2e_revalidation_phase1"

```
Blocking is how we avoid the O(n^2) comparison problem in entity resolution. The system uses union blocking: multiple independent blocking rules execute in parallel, and candidate pairs are the UNION of all rule hits. Rules are organized into tiers: Tier 1 (exact matches on phone, document ID -- highest confidence), Tier 2 (composed keys like phonetic_name + postal_code), Tier 3 (single-feature keys like city alone). Each rule generates pairs where entities share the same blocking key value. Information Content (IC) filtering suppresses low-discriminative keys -- if a feature value appears too frequently (low IC in bits), it's added to a stop-list. IC thresholds: Tier 2 = 8.0 bits, Tier 3 = 6.0 bits. Safety net: max_block_size = 10,000 pairs per key value.
```

### Episode 7 -- Vertica Architecture
**Importance**: 0.7
**Context**: "e2e_revalidation_phase1"

```
Understanding why we use Vertica natively instead of extracting data to Python. Vertica is a columnar MPP database -- data is distributed across nodes via hash segmentation, and queries execute in parallel across segments. Key architecture patterns: (1) Super projections optimized for common queries, (2) Entity buddy projections segmented by entity_id for scoring joins (local, no resegment), (3) Feature buddy projections segmented by feature_value for blocking (local, no broadcast), (4) Delta buddy projections for incremental processing. Critical rule: avoid BROADCAST joins at all costs -- they copy entire tables across nodes. Our dual-projection strategy forces LOCAL merge joins, eliminating ~32% broadcast cost. Encoding optimization (RLE, COMMONDELTA) based on data characteristics. Statistics management with ANALYZE_STATISTICS at 7 checkpoints.
```

### Episode 8 -- Incremental Processing
**Importance**: 0.6
**Context**: "e2e_revalidation_phase1"

```
The ER pipeline supports incremental processing for batch updates. Infrastructure: 5 core tables -- er_process_control (batch metadata), er_entity_watermark (change detection fingerprints), er_delta_entities (delta staging with types: NEW=1, MODIFIED=2, UNCHANGED=3, DELETED=4), er_duplicate_groups (exact-duplicate mapping), er_batch_stage_status (execution tracking). Delta flow: fingerprint all entities, compare to watermarks, classify changes, delete stale blocking pairs for MODIFIED/DELETED, run delta-by-history + delta-by-delta blocking, score only new pairs. Key design choice: DELETE strategy for MODIFIED entities (not FLAG + rescore) -- old blocking keys are stale and must be regenerated.
```

---

## Phase 2: Active Development (Feb 2026) -- 9 episodes

### Episode 9 -- Blocking Implementation with IC Stop-Lists
**Importance**: 0.8
**Context**: "e2e_revalidation_phase2"

```
Implemented the full blocking pipeline with Information Content stop-lists. The IC computation uses Shannon entropy: IC(v) = -log2(freq(v) / total_distinct). Values below the tier threshold are added to a per-feature stop-list table. During blocking, pairs involving stop-listed values are excluded. Key implementation detail: IC reference count was initially hardcoded at 195,000 (the Senzing benchmark dataset size). This works fine at that scale but will cause incorrect thresholds at 252M. Also implemented the multi-tier rule evaluation: 8 person blocking rules and 5 organization blocking rules, each with configurable IC thresholds per feature. Blocking results stored in er_candidate_pairs with (entity_id_1, entity_id_2, blocking_rule_id, delta_batch_id).
```

### Episode 10 -- SQL Injection in IdentifierLinkNormalizationService
**Importance**: 0.7
**Context**: "e2e_revalidation_phase2"

```
Found a SQL injection vulnerability in the IdentifierLinkNormalizationService during code review. The service was constructing SQL queries using string interpolation for identifier type names, which come from user-provided data mapping configuration. An identifier_type value like "SSN'; DROP TABLE person_normalized_data; --" would execute arbitrary SQL against Vertica. Fixed by switching to parameterized queries using the db/quoting.py helpers (quote_identifier for column/table names, parameterized $1/$2 for values). Also audited all other normalization services -- phone_link_service.py and address_link_service.py had similar patterns. All fixed and covered by new unit tests.
```

### Episode 11 -- Exact Duplicate Fingerprinting
**Importance**: 0.6
**Context**: "e2e_revalidation_phase2"

```
Implemented always-on exact duplicate deduplication using composite fingerprinting. Each entity gets a 64-bit HASH computed across all its normalized attributes. Detection uses window functions: ROW_NUMBER() OVER (PARTITION BY entity_type, composite_fingerprint ORDER BY object_id). The first entity (MIN object_id) becomes the representative; others go to er_duplicate_groups. Duplicates are excluded from er_delta_entities via NOT EXISTS anti-join before they enter the pipeline. Matched duplicates exported as EXACT_MATCH pairs with score=100.0. Ally Bank benchmark: 187,635 source entities, 1,756 duplicates in 903 groups, 185,879 unique representatives.
```

### Episode 12 -- Incremental Blocking Strategy
**Importance**: 0.7
**Context**: "e2e_revalidation_phase2"

```
Implemented the incremental blocking strategy for delta processing. The key insight: when new or modified entities arrive, we need to block them against (1) the existing history (delta-by-history) and (2) each other (delta-by-delta). For MODIFIED entities, we first DELETE their old blocking pairs since the keys may have changed. The dual-projection approach ensures merge joins stay local: one projection sorted by (feature_value, delta_batch_id, entity_object_id) for the delta side, another without delta_batch_id for the history side. Correctness testing via scripts/test_incremental_correctness.sh: multi-batch orchestration with controlled INSERT/UPDATE/DELETE batches and 7 integrity invariants (I1-I7).
```

### Episode 13 -- Deterministic Scoring
**Importance**: 0.6
**Context**: "e2e_revalidation_phase2"

```
Built the Stage 3 scoring pipeline. For each candidate pair, the system materializes feature comparison vectors (66 features) and computes a match score. The scoring engine supports both deterministic rules (exact match thresholds) and probabilistic Bayes Factor computation. Feature materialization uses batched execution with memory-aware ceiling to prevent OOM on large block sizes. Each batch gets a separate materialization query, and results are written to er_pair_features. The scoring query then joins pair features with the Fellegi-Sunter weight table to produce final scores. Explainability output: each pair gets a JSON evidence document showing which features matched, their individual weights, and the aggregate score.
```

### Episode 14 -- Performance Profiling
**Importance**: 0.7
**Context**: "e2e_revalidation_phase2"

```
Ran performance profiling on the blocking stage and found several issues. The Vertica EXPLAIN output showed 3 queries doing BROADCAST joins instead of local merge joins -- this was caused by missing buddy projections on the blocking tables. After adding projections segmented by feature_value, broadcast cost dropped by 32%. Also found that ANALYZE_STATISTICS was not being called after feature materialization, causing the query optimizer to use stale cardinality estimates. Added statistics checkpoints at 7 stages: after normalization, after feature extraction, after blocking, after IC computation, after pruning, after scoring, and after export. Pipeline throughput improved from 1,200 to 1,850 pairs/second.
```

### Episode 15 -- Fingerprint 32-to-64 Bit Collision Fix
**Importance**: 0.6
**Context**: "e2e_revalidation_phase2"

```
Discovered a critical bug in the exact duplicate fingerprinting: we were using 32-bit HASH instead of 64-bit. At 252 million entities, the birthday paradox predicts ~7,600 hash collisions with 32-bit hashes (50% collision probability at ~77,000 entities). This means thousands of non-duplicate entity pairs would be falsely grouped as exact duplicates and excluded from the pipeline. Switched to 64-bit HASH which pushes the 50% collision threshold to ~5 billion entities -- well beyond our 252M target. The fix required updating the er_entity_watermark table schema and all fingerprint computation queries. Verified with a probabilistic analysis: P(collision) = 1 - e^(-n^2 / 2k) where n=252M and k=2^64 gives P < 0.002.
```

### Episode 16 -- Korean Character UDX Crash
**Importance**: 0.6
**Context**: "e2e_revalidation_phase2"

```
The ParseHumanName UDX crashes with a NullPointerException when processing Korean hangul characters (Unicode block U+AC00-U+D7AF). The UDX's internal tokenizer assumes whitespace-delimited name parts, but Korean names are often written without spaces (e.g., "김철수" = Kim Cheol-su). When the tokenizer finds no whitespace, it returns null for the family_name component, and the downstream normalization code dereferences it without a null check. Workaround: added a pre-processing step that inserts a space after the first character for CJK-range names. Proper fix requires modifying the Java UDX source in vertica-functions-datawalk-library.jar to handle CJK Unicode blocks with a language-aware tokenizer.
```

### Episode 17 -- Chaos Testing Framework
**Importance**: 0.5
**Context**: "e2e_revalidation_phase2"

```
Built the chaos testing (fuzzing) framework for pipeline robustness validation. The fuzzer uses a clone-and-mutate strategy: take a clean dataset, apply controlled mutations, run the pipeline, verify results. 8 mutation profiles defined in config/fuzzing-profiles/: null_injection (random NULL fields), encoding_corruption (invalid UTF-8 sequences), boundary_values (max-length strings, zero dates), format_mixing (phone formats across countries), transliteration (Latin<->Cyrillic), duplicate_injection (exact + near duplicates), deletion_simulation (random entity removal), update_cascade (linked entity modifications). Each profile has a severity level and expected pipeline behavior. Framework outputs: mutation log, pipeline results, regression diff against clean baseline.
```

---

## Phase 3: Scaling & Optimization (Mar 2026) -- 8 episodes

### Episode 18 -- Metaphone3 Evaluation: 4-Char Concerns
**Importance**: 0.7
**Context**: "e2e_revalidation_phase3"

```
Evaluated Metaphone3 as a replacement for Soundex in our phonetic blocking rules. Metaphone3 offers >98% accuracy on the reference corpus vs Soundex's ~70%. However, the default 4-character code length creates too many candidate pairs -- with 252M entities, 4-char Metaphone3 codes map to very large equivalence classes. For example, "SMITH" and "SCHMIDT" both produce code "XMT0" (4-char), creating a block of potentially millions of pairs. The pair explosion at 4-char is worse than Soundex because Metaphone3's normalization is more aggressive about collapsing similar sounds. We need to investigate longer code lengths or combined blocking keys to control block sizes while keeping the accuracy benefit.
```

### Episode 19 -- WNP Meta-Blocking
**Importance**: 0.8
**Context**: "e2e_revalidation_phase3"

```
Implemented Weighted Node Pruning (WNP) with ECBS edge weights as a meta-blocking stage (Stage 2.5) to reduce candidate pairs by 25-40% with less than 1% recall loss. Algorithm: (1) Build bipartite blocking graph where edges = candidate pairs, (2) Compute edge weights = inverse block cardinality + tier-based boosts (Tier 1: +10.0, Tier 2: +3.0, Tier 3: +0.0-2.0), (3) For each node, compute average neighbor weight, (4) Prune pair if edge_weight < threshold_multiplier * both endpoints' avg_weight. Storage: INSERT-only er_pruned_pairs table -- no mutation of original candidate pairs, enabling A/B toggle. Results on BPID benchmark (186K entities): 18.1 pairs/entity with WNP (vs 24.5 without), 90.25% recall preserved. Plan: docs/plans/36-blocking-pruning-meta-blocking.md.
```

### Episode 20 -- Switching to 8-Char Metaphone3
**Importance**: 0.7
**Context**: "e2e_revalidation_phase3"

```
Decision made: switching from 4-character to 8-character Metaphone3 codes for all phonetic blocking rules. The 8-char codes are more discriminative -- "SMITH" (XMT0) vs "SCHMIDT" (XMTT) are now distinct, reducing block sizes by approximately 60%. Migrated all person blocking rules (rules P1-P8) and organization blocking rules (rules O1-O5) to use Metaphone3 with maxCodeLen=8. Also replaced DoubleMetaphone with Metaphone3 for organization name blocking. The Metaphone3 UDX is implemented as a Java function in vertica-functions-datawalk-library.jar with configurable parameters: maxCodeLen, encodeVowels (false), encodeExact (false). Benchmarking the impact on pair counts and recall at 1M scale before scaling up.
```

### Episode 21 -- IC Scaling: Dynamic Reference Count
**Importance**: 0.7
**Context**: "e2e_revalidation_phase3"

```
Fixed the IC reference count scaling issue identified during Phase 2 development. The IC computation formula IC(v) = -log2(freq(v) / reference_count) was using a hardcoded reference_count of 195,000 (the Senzing benchmark size). At 252M entities, this makes every feature value appear hyper-frequent, collapsing IC scores toward zero and putting almost everything on the stop-list. Fix: switched to dynamic reference count via SELECT COUNT(DISTINCT entity_object_id) FROM the appropriate normalized table. This makes IC thresholds scale-adaptive. Also implemented per-tier IC thresholds (Tier 2: 8.0 bits, Tier 3: 6.0 bits, Tier 4: 5.0 bits) instead of a single global threshold. Verified: at 1M entities, the dynamic approach produces IC distributions matching the expected entropy curves.
```

### Episode 22 -- Scaling Benchmarks
**Importance**: 0.7
**Context**: "e2e_revalidation_phase3"

```
Ran scaling benchmarks at 1M, 5M, 10M, and 30M entity counts to validate the pipeline before the 252M production run. Key results: At 1M entities, pairs/entity dropped from 55 to 10-13 with WNP pruning. At 30M, WNP achieved 40% pair reduction while maintaining P/E ratio of 7.86. Extrapolation to 252M targets <=5 pairs/entity. Performance: 1M completes in ~12 minutes, 30M in ~4.5 hours. Main bottleneck shifted from blocking to feature materialization at scale -- the batched scoring queries need memory-aware ceiling tuning. Also discovered: at 10M+, the background mergeout optimization becomes critical (saves ~56 seconds per pipeline run by parallelizing ROS container consolidation during feature materialization).
```

### Episode 23 -- Encoding Optimization
**Importance**: 0.6
**Context**: "e2e_revalidation_phase3"

```
Ran the automated encoding audit tool (tools/optimize_encodings/) against all ER pipeline tables to optimize Vertica compression. The tool analyzes column data distributions and recommends encoding changes: RLE for low-cardinality columns (delta_type, entity_type), COMMONDELTA_COMP for sequential IDs, DELTARANGE_COMP for timestamps, AUTO for string columns with variable patterns. Applied encoding changes to 23 columns across 8 tables. Storage reduction: 34% overall compression improvement. Query performance: 15-20% speedup on full-table scans due to reduced I/O. The encoding registry (tools/optimize_encodings/registry.py) is now wired into all DDL generation sites so new tables automatically get optimal encodings.
```

### Episode 24 -- Fellegi-Sunter Gap Analysis
**Importance**: 0.8
**Context**: "e2e_revalidation_phase3"

```
Completed a gap analysis between our current implementation and the full Fellegi-Sunter theoretical model. Key gaps identified: (1) We don't implement the EM algorithm for parameter estimation -- m/u probabilities are currently set via heuristic rules in scoring.yaml rather than learned from data. (2) No Term Frequency Adjustment for common values (high-frequency names like "Smith" get the same weight as rare names). (3) Missing collective entity resolution -- our current approach scores pairs independently without considering transitive consistency (if A=B and B=C, we should infer A=C). (4) The CIA assumption is violated for correlated features like (city, postal_code) and (given_name, gender). Plan to address gaps in priority order: TFA first (highest impact on precision), then EM estimation, then collective ER.
```

### Episode 25 -- Demo Preparation: 252M Pipeline
**Importance**: 0.7
**Context**: "e2e_revalidation_phase3"

```
Preparing for the 252 million entity demo on OKE (Oracle Kubernetes Engine). Configuration in docs/mvp-plan/datawalk-integration/: 48-core Vertica cluster, 384GB RAM, NVMe storage. Pipeline parameters tuned based on 30M benchmark extrapolation: WNP threshold_multiplier=1.2, IC dynamic reference count, Metaphone3 8-char codes, batch_size=50000 for feature materialization, parallel_workers=8 for scoring. Health check framework (52 checks across 7 categories: INFRA, INTEG, LINE, DQ, PERF, STAT, SPACE) validates pipeline integrity before, during, and after execution. Target metrics: F1 >= 90%, pipeline completion <= 24 hours, pairs/entity <= 5. The demo uses kubeconfig from get_oke_kubeconfig_v3.
```

---

## Phase 4: Evolution & Corrections (Mar 2026 late) -- 3 episodes

### Episode 26 -- CORRECTION: Metaphone3 Hybrid Approach
**Importance**: 0.8
**Context**: "e2e_revalidation_phase4_correction"

```
CORRECTION to the previous Metaphone3 decision. After testing with multilingual datasets, the 8-character Metaphone3 codes are too discriminative for non-Latin scripts. Korean, Chinese, and Arabic names transliterated to Latin produce highly variable Metaphone3 codes -- the same name can produce 3-4 different 8-char codes depending on the romanization scheme used. This effectively breaks phonetic blocking for non-Latin names. New decision: HYBRID APPROACH -- use 8-character Metaphone3 for Latin-script names (where the longer codes improve precision) and 4-character Metaphone3 for non-Latin transliterated names (where shorter codes provide necessary recall). Implemented via a language detection step before phonetic encoding. This reverses the blanket "switch to 8-char" decision from Episode 20.
```

### Episode 27 -- Team Change
**Importance**: 0.6
**Context**: "e2e_revalidation_phase4_correction"

```
Team restructuring: Jonas Weber has transferred from the ER backend team to the Security team, effective this week. This was motivated by the SQL injection findings from Episode 10 -- leadership decided to invest more in security infrastructure. Sarah Kim is taking over Jonas's backend engineering responsibilities on the ER project, in addition to her data quality work. Sarah is now the primary owner of the normalization pipeline and blocking rules implementation. Anya Kowalski continues as Vertica infrastructure lead. The team is now three people instead of four, so we're reprioritizing: collective entity resolution (from the gap analysis) is deferred to Q3.
```

### Episode 28 -- Discovery: Exact Duplicate Prevalence
**Importance**: 0.7
**Context**: "e2e_revalidation_phase4_correction"

```
New discovery from production data analysis: the real dataset of 260 million records contains approximately 4x the expected exact duplicate rate. Nearly 15% of records are exact duplicates (compared to the 0.9% rate seen in the Ally Bank benchmark of 187K records). This validates the decision to implement always-on fingerprint deduplication before delta processing. Without dedup, the pipeline would process ~39 million unnecessary pairs. The 64-bit fingerprint upgrade from Episode 15 is critical at this scale -- with 32-bit hashes, we'd see ~3,400 false duplicate groupings. Updated the er_duplicate_groups table partitioning strategy to handle the higher cardinality. The dedup stage now saves approximately 4 hours of pipeline runtime by excluding duplicates before blocking.
```
