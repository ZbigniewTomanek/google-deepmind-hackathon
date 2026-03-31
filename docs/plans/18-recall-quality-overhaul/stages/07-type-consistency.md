# Stage 7: Cross-Extraction Type Consistency

**Goal**: Reduce semantic duplicate nodes by improving the ontology agent's type reuse and expanding the dedup merge-safety heuristic.
**Dependencies**: Stage 5 (type validation must be in place before changing type assignment logic)

---

## Background

E2E testing showed the same entity typed differently across extraction runs:
- "Metaphone3" → Methodology (run 1) vs Tool (run 2)
- "Blocking" → Methodology vs ProcessStage
- "252 Million Entities" → Concept vs Dataset vs Metric
- "Vertica 24.x" → DataStore vs Tool

Root causes:
1. **Ontology agent sees types but doesn't actively reuse them**: The agent receives existing type names (`extraction/pipeline.py:102`) but the prompt says "propose new types" — it's incentivized to create, not reuse.
2. **Dedup merge-safety is too conservative**: `_types_are_merge_safe` only merges a narrow set of known-equivalent pairs. "Methodology" and "Tool" are not in the safe list, so a second extraction creates a duplicate node.
3. **No entity→type anchoring**: If "Metaphone3" was typed as "Tool" in a prior extraction, there's no mechanism to tell the extractor "use Tool for Metaphone3."

**Fix**: Three improvements:
1. Strengthen the ontology agent prompt to prioritize reuse over proposal
2. Pass entity→type mappings (not just type names) to the extractor agent
3. Expand the merge-safety groups in the dedup logic

---

## Steps

1. **Strengthen the ontology agent prompt for type reuse**
   - File: `src/neocortex/extraction/agents.py`, ontology agent system prompt (around lines 82-89)
   - Change from:
     ```
     "Extend conservatively: prefer existing types when possible."
     ```
   - To:
     ```
     "REUSE existing types aggressively. Only propose a new type if NO existing type "
     "covers the concept. When in doubt, reuse the closest existing type rather than "
     "creating a new one. Proposing unnecessary new types fragments the graph."
     ```

2. **Pass entity→type examples to the ontology context injection**
   - File: `src/neocortex/extraction/agents.py`, `inject_context` for ontology agent (around lines 92-131)
   - Currently it passes `existing_node_types` as a flat list of names. Enhance it to include sample entities per type:
     ```python
     # In inject_context for ontology agent:
     # Fetch top 5 nodes per type to show the agent what's already typed
     type_examples = {}
     for t in node_types:
         examples = await repo.browse_nodes(agent_id, type_name=t.name, limit=5, target_schema=target_schema)
         if examples:
             type_examples[t.name] = [n.name for n in examples]

     # Add to context:
     context += "\n\nExisting types with example entities:\n"
     for type_name, examples in type_examples.items():
         context += f"- {type_name}: {', '.join(examples)}\n"
     context += "\nIf the text mentions any of these entities, reuse their existing type.\n"
     ```
   - **Performance concern**: This adds N queries (one per type). Limit to types with `count > 0` and cap at 20 types to bound latency. Use a dedicated efficient query if possible:
     ```sql
     SELECT nt.name as type_name, array_agg(n.name ORDER BY n.importance DESC) as examples
     FROM node_type nt
     JOIN node n ON n.type_id = nt.id AND n.forgotten = false
     GROUP BY nt.name
     LIMIT 20
     ```

3. **Pass entity→type anchoring to the extractor agent**
   - File: `src/neocortex/extraction/agents.py`, extractor agent context injection
   - After the ontology stage produces types, also pass a "known entities" list to the extractor:
     ```python
     # In inject_context for extractor agent:
     context += "\n\nKnown entities and their assigned types:\n"
     for type_name, examples in type_examples.items():
         for entity_name in examples[:3]:
             context += f"- \"{entity_name}\" → {type_name}\n"
     context += "\nWhen extracting these entities, use their assigned types.\n"
     ```

4. **Expand merge-safety groups in dedup logic**
   - File: `src/neocortex/db/adapter.py`, function `_types_are_merge_safe` (find it near the upsert logic)
   - Add new semantic equivalence groups:
     ```python
     _MERGE_SAFE_GROUPS = [
         # Existing groups (keep as-is)
         ...,
         # New groups for commonly-confused types
         {"Tool", "Technology", "Framework", "Library", "Software"},
         {"Methodology", "Method", "Approach", "Strategy", "Technique", "ProcessStage"},
         {"Concept", "Idea", "Theory", "Principle"},
         {"Dataset", "Data", "DataSource", "DataStore"},
         {"Metric", "Measurement", "KPI", "Indicator"},
         {"Person", "TeamMember", "Developer", "Engineer"},
         {"Organization", "Company", "Team", "Group"},
     ]
     ```
   - The function should check if two type names belong to the same group.

5. **Clean up empty types (opportunistic)**
   - File: `src/neocortex/extraction/pipeline.py`
   - After extraction completes (after all 3 agents have run), add an optional cleanup step:
     ```python
     # Remove types with 0 nodes that were created in this extraction run
     # Only delete types created in the last 5 minutes to avoid removing
     # types created by concurrent extractions
     await repo.cleanup_empty_types(agent_id, max_age_minutes=5, target_schema=target_schema)
     ```
   - Implement `cleanup_empty_types` in the adapter:
     ```python
     async def cleanup_empty_types(self, agent_id, max_age_minutes=5, target_schema=None):
         async with schema_scoped_connection(self._pool, schema) as conn:
             deleted = await conn.fetch(
                 "DELETE FROM node_type WHERE id NOT IN (SELECT DISTINCT type_id FROM node) "
                 "AND created_at > now() - interval '$1 minutes' RETURNING name",
                 max_age_minutes,
             )
             if deleted:
                 logger.info("cleaned_empty_types", count=len(deleted),
                            names=[r["name"] for r in deleted])
     ```
   - Add the method to the `MemoryRepository` protocol in `db/protocol.py`.
   - Add a no-op implementation in `db/mock.py`.

6. **Add tests**
   - File: `tests/test_graph_data.py` or a new `tests/test_dedup.py`
   - Add tests:
     ```python
     def test_merge_safe_tool_methodology():
         """Tool and Methodology should NOT be merge-safe (different semantic category)."""
         assert not _types_are_merge_safe("Tool", "Methodology")

     def test_merge_safe_tool_technology():
         """Tool and Technology should be merge-safe."""
         assert _types_are_merge_safe("Tool", "Technology")

     def test_merge_safe_methodology_technique():
         """Methodology and Technique should be merge-safe."""
         assert _types_are_merge_safe("Methodology", "Technique")
     ```

---

## Verification

- [ ] `uv run pytest tests/ -v` — all tests pass
- [ ] Ontology agent prompt contains "REUSE existing types aggressively"
- [ ] Extractor agent receives known entity→type mappings in context
- [ ] `_types_are_merge_safe("Tool", "Technology")` returns `True`
- [ ] `_types_are_merge_safe("Tool", "Person")` returns `False`
- [ ] Empty type cleanup runs after extraction without errors
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

---

## Commit

`feat(extraction): improve cross-extraction type consistency and expand merge-safe groups`
