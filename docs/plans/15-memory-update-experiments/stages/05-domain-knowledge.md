# Stage 5: Domain Knowledge Accumulation (ER Engine Simulation)

**Goal**: Simulate realistic knowledge accumulation from Plan 36d execution. Test whether the system can support complex domain queries after storing evolving experimental results.

**Dependencies**: Stage 4

---

## Experiment Design

### 5.1 Store foundational ER domain knowledge
```
remember("Entity Resolution (ER) is the process of determining whether different data records refer to the same real-world entity. Our ER engine uses a multi-stage pipeline: normalization, feature extraction, blocking, pruning, scoring, evaluation.", importance=0.9)

remember("Blocking is the most critical ER stage for scalability. It generates candidate pairs that might be matches. The key metric is pairs-per-entity (p/e) — lower is better for performance, but too aggressive blocking hurts recall.", importance=0.9)

remember("Metaphone3 is a phonetic encoding algorithm used in blocking rules. It converts names to phonetic codes so similar-sounding names match. Precision (4-char vs 8-char codes) controls the tradeoff: shorter codes = more matches = higher recall but more pairs.", importance=0.8)
```

### 5.2 Store experimental results (simulating Plan 36d execution)
```
remember("Plan 36d sandbox results: precision-first blocking achieved 4.24 p/e with 81.60% recall. This is below the 84% recall gate but p/e is excellent.", importance=0.8)

remember("Plan 36d 1M corporate benchmark: 6.55 projected p/e at 5M entities. The scaling exponent b=0.57 was fitted from 1M and 5M data points. Pipeline completed in 847 seconds.", importance=0.8)

remember("Plan 36d critical finding: the mixed_person_name_city blocking rule shows super-linear growth — 76x pair increase for 10x entity increase. This rule is the main scalability bottleneck at 252M.", importance=0.9)
```

### 5.3 Store a strategic decision that supersedes prior approach
```
remember("Plan 36d CONDITIONAL GO decision: precision-first blocking unblocks 5M scale (was previously killed at 113.9 p/e in Plan 36c), but 252M production requires additional work in Plan 36e: two-phase pre-scoring, token blocking, and ARCS weighting.", importance=0.9)
```

### 5.4 Complex domain queries
```
recall("What is the current scalability status of the ER engine?")
recall("Why was Plan 36c killed and how does 36d fix it?")
recall("What blocking rules are problematic at scale?")
recall("What is the p/e ratio and why does it matter?")
recall("What needs to happen before 252M production?")
```

**Key question**: Can the system assemble a coherent answer from multiple stored facts?

### 5.5 Update experimental results (simulating plan progression)
```
remember("UPDATE to Plan 36d: After 10M benchmark, the scaling exponent was refined to b=0.62. The mixed_person_name_city rule is confirmed as the bottleneck. Two-phase pre-scoring is estimated to reduce Stage 3 time by 40-70%.", importance=0.9)
```

### 5.6 Recall updated results
```
recall("What is the latest scaling exponent for the ER pipeline?")
recall("Plan 36d benchmark results")
```

**Key question**: Does the updated scaling exponent (0.62) appear above the old one (0.57)?

---

## Verification

- [ ] Foundational knowledge recalled correctly
- [ ] Experimental results recalled with correct values
- [ ] Complex queries return relevant multi-fact results
- [ ] Updated results appear in recall (with what priority?)
- [ ] Cross-fact reasoning possible from recall results

---

## Results

### 5.1-5.3 Knowledge storage
[Log results]

### 5.4 Complex queries
[Log each recall result — note relevance and completeness]

### 5.5-5.6 Updated results
[Log results — critical: does new data supersede old?]

### Analysis
[Can an agent use this recall output to reason about the ER domain?
What's missing for it to be truly useful?]
