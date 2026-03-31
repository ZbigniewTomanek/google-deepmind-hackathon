# Evidence: Root Cause Analysis

Log data and code paths confirming each root cause.

---

## M5 Domain Routing — Permission Gap

### Log Evidence (March 31, 2026)

Classification succeeds for ALL episodes:
```
ep=1  | matched=1 | method=llm | ['work_context']
ep=2  | matched=3 | method=llm | ['work_context', 'technical_knowledge', 'domain_knowledge']
ep=3  | matched=2 | method=llm | ['work_context', 'technical_knowledge']
...all 29 episodes matched 1-3 domains...
```

But routing produces 0 for ALL:
```
ep=1  | domain_count=0 | routed_to=[]
ep=2  | domain_count=0 | routed_to=[]
...all 29 episodes domain_count=0...
```

No `domain_routing_skipped` warnings (domains ARE available).
No `domain_routing_permission_denied` warnings (logged at DEBUG, invisible).

### Code Path

```
router.py:63  — domains = await self._domain_service.list_domains()  → [4 domains] ✓
router.py:75  — classification = await self._classifier.classify(...)  → matched ✓
router.py:98  — matches = [...confidence >= threshold]  → passes ✓
router.py:118 — schema_name = await self._ensure_schema(domain, agent_id)
  router.py:194 — existing = await self._schema_mgr.get_graph(...)  → EXISTS ✓
  router.py:195 — return domain.schema_name  ← NO PERMISSION GRANT ✗
router.py:122 — can_write = await self._permissions.can_write_schema(...)  → False ✗
router.py:124 — logger.debug("permission_denied")  ← DEBUG LEVEL, INVISIBLE ✗
router.py:130 — continue  ← SILENTLY SKIPS
```

### Counter-evidence (March 28)

Earlier in the March 28 session, episodes 31+ DID route successfully (domain_count=2-3).
This was likely the FIRST time those schemas were accessed, triggering the CREATE path
in `_ensure_schema()` which DOES grant permissions. Subsequent sessions hitting the
EXISTING path fail.

---

## M4 Temporal Recall — Merge Destroys Signal

### Observed Behavior

Episode 26 (CORRECTION: hybrid approach) → extractor produces `ExtractedEntity(name="Metaphone3")`
→ librarian calls `find_similar_nodes("Metaphone3")` → finds existing node
→ calls `create_or_update_node("Metaphone3", ...)` → MERGES INTO EXISTING
→ no SUPERSEDES edge created (source=target=same node)

### Result
- 1 SUPERSEDES edge total across 206 nodes (Metaphone3 → Soundex, between algorithms)
- 0 CORRECTS edges
- Temporal queries return oldest content ranked #1 (score gap: 0.797 vs 0.322)

---

## M6 Type Corruption — Regex Gap

### Current Regex
```python
_VALID_NODE_TYPE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")
# No length limit
```

### Why Each Corrupted Type Passes

| Input | After strip | Length | Regex match? | Accepted? |
|-------|-------------|--------|-------------|-----------|
| `DatasetNoteThe...` (440 chars) | Same (all alpha) | 440 | Yes | Yes |
| `EvidencedocumentOceanography` | Same | 29 | Yes | Yes |
| `FeatureMergesWithEntityObjectId167` | Same | 35 | Yes (has digits) | Yes |
| `OperationbrCreateOrUpdate...` (300 chars) | Same | 300 | Yes | Yes |
