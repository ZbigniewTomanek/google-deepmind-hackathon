# Ontology Agent Redesign — Handoff

This document is a handoff for the agent that will redesign Stages 3-4 of Plan 28.
Read this first, then revise the stage files.

---

## Problem

The ontology agent is the weakest link in the extraction pipeline. It runs
Gemini 3 Flash with low thinking, produces structured output in a single pass
(0-shot, no tools), and the pipeline trusts whatever it returns. This produces
hallucinated types, instance-level types, and massive proliferation.

The current plan (Stages 3-4) tries to fix this with better prompts and a
thinking effort bump from "low" to "medium". This is insufficient — the
fundamental architecture is wrong.

## Why prompts alone won't fix this

The ontology agent sees:
- Episode text (raw content)
- Existing type names + descriptions + 5 example entities per type (max 20 types)
- Domain hint (optional free text)

And must produce in one shot:
- A list of new node types (name + description)
- A list of new edge types (name + description)
- A rationale

Problems with this design:
1. **Information deficit**: The agent sees type names but can't explore the graph.
   With 90+ types, it gets a flat list with no understanding of usage patterns,
   frequency, or semantic clusters.
2. **No feedback**: If it proposes "DishGreg", the pipeline persists it silently.
   Stage 1 validation will catch obvious garbage, but subtle issues (redundant types,
   poor granularity choices) pass through.
3. **Wrong framing**: "Propose new types" is a generative task. The correct framing
   is "classify into existing types; identify genuine gaps" — a selective task.
4. **No grounding**: The agent has no way to check "does a type like this already
   exist?" or "how is this type actually used?" It must hold the entire ontology in
   context and reason about it — a task that requires strong models.

## Redesign direction

**Make the ontology agent agentic: give it tools to explore the current ontology
and validate its own proposals before committing.**

### Architecture: classify-then-create with tool access

Replace the current 0-shot structured output with a tool-using agent that follows
a two-phase workflow:

**Phase 1 — Classification (most episodes stop here)**
The agent reads the episode text and the existing type list, then uses tools to
check whether existing types cover all concepts. For each concept it identifies:
- Use `find_similar_types(name)` to check for near-matches
- Use `get_type_usage(type_name)` to see how a type is actually used (example entities)
- Decide: reuse existing type, or flag a genuine gap

**Phase 2 — Type proposal (rare, triggered only for genuine gaps)**
For each gap identified in Phase 1:
- Use `propose_type(name, description)` which runs synchronous validation
  (the Stage 1 heuristics) and returns pass/fail with reason
- If rejected: agent gets feedback and can retry with a different name
- If accepted: type is added to the working set

### Proposed tools for the ontology agent

```python
# Read-only — explore current ontology
find_similar_types(query: str, kind: "node"|"edge") -> list[{name, description, usage_count, example_entities}]
    # Trigram + semantic search across type names and descriptions
    # Returns top 5 matches with usage stats

get_ontology_summary() -> {node_types: [{name, description, usage_count}], edge_types: [...], total_nodes, total_edges}
    # Full ontology snapshot with usage counts, sorted by usage
    # Agent calls this once at the start to orient itself

# Write — propose with validation feedback
propose_type(name: str, description: str, kind: "node"|"edge") -> {accepted: bool, reason: str, similar_existing: list[str]}
    # Runs Stage 1 validation heuristics synchronously
    # Also checks trigram similarity against existing types
    # Returns rejection reason if invalid, or similar types if >0.6 similarity
    # Does NOT persist — just validates and returns feedback

# Final output — commit decisions
commit_ontology_decisions() -> triggers structured output collection
    # Agent calls this when done; pipeline collects all accepted proposals
```

### Why this is better

| Aspect | Current (0-shot) | Proposed (agentic) |
|--------|------------------|-------------------|
| Type reuse | Prompt says "reuse" but model ignores | Agent actively searches for existing types |
| Validation | Post-hoc, silent drop | Inline, with retry opportunity |
| Ontology understanding | Flat list of names | Usage counts, example entities, search |
| Model requirement | Needs strong model for judgment | Weaker model works because tools provide grounding |
| Cost per episode | 1 LLM call | 3-8 tool calls + 1 LLM call (but can use cheaper model) |
| New type rate | ~5-10 per episode | ~0-1 per episode (most reuse existing) |

### Cost analysis

Current: 1 ontology call per episode (~1K input tokens, ~200 output tokens)
Proposed: ~5 tool calls average (mostly find_similar_types) + final output
- Tool calls are cheap (DB queries, no LLM)
- LLM calls increase by ~2-3x for the ontology step
- But ontology is <10% of total extraction cost (librarian dominates)
- Net impact: ~5-15% total cost increase, massive quality improvement

## Current pipeline architecture (reference)

Read `pipeline.py` to see the full flow. Key points:

```
Episode.content
    |
    v
[Load ontology] asyncio.gather(get_node_types, get_edge_types, get_type_examples)
    |            Returns: list[TypeInfo(id, name, description)] + {type: [entity_names]}
    v
[Ontology agent] OntologyAgentDeps → OntologyProposal  <-- THIS IS WHAT YOU REDESIGN
    |             Currently: 0-shot structured output, no tools
    |             Persist: repo.get_or_create_node_type/edge_type for each proposed type
    v
[Extractor agent] ExtractorAgentDeps → ExtractionResult
    |              Receives: all types (existing + newly created)
    v
[Librarian agent] LibrarianAgentDeps → CurationSummary (tool mode)
                   Has 9 tools: find_similar_nodes, create_or_update_node, etc.
```

### Key dataclasses (in `src/neocortex/extraction/agents.py`)

**OntologyAgentDeps** (line ~62):
- episode_text, existing_node_types, existing_edge_types
- node_type_descriptions, edge_type_descriptions
- domain_hint, type_examples

**OntologyProposal** (in `src/neocortex/extraction/schemas.py`):
- new_node_types: list[ProposedNodeType]  # name + description
- new_edge_types: list[ProposedEdgeType]
- rationale: str

**AgentInferenceConfig** (line ~34):
- model_name, thinking_effort, use_test_model

### Key files to modify

1. `src/neocortex/extraction/agents.py`
   - `build_ontology_agent()` at line 73 — add tools, revise prompt
   - `OntologyAgentDeps` at line 62 — add `repo` and `agent_id` fields for tool access
   - `inject_context()` at line 95 — simplify; tools replace static context dumps

2. `src/neocortex/extraction/pipeline.py`
   - `run_extraction()` — pass repo + agent_id to ontology deps
   - Handle tool-based output collection (proposals accumulate via tool calls)
   - Keep the existing type merge logic for persisting accepted proposals

3. `src/neocortex/extraction/schemas.py`
   - `OntologyProposal` may need revision if output format changes

4. `src/neocortex/mcp_settings.py`
   - `ontology_thinking_effort` default change still applies
   - Consider adding `ontology_tool_calls_limit` setting

5. `tests/` — extraction tests that mock the ontology agent's output

### Constraints

- **Don't break the extractor/librarian**: They consume the ontology agent's output
  (list of available types). The downstream interface must stay the same:
  after the ontology step, `node_types` and `edge_types` lists are updated and
  passed to the extractor.
- **Keep the structured output**: The final output should still be `OntologyProposal`
  (or equivalent) so the pipeline can persist new types. Tools are for exploration
  and validation; the final commit is structured output.
- **MemoryRepository protocol**: Tools that query the graph must go through `repo`.
  The ontology agent deps will need `repo: MemoryRepository` (same pattern as librarian).
- **Test model compatibility**: `pydantic_ai.models.test.TestModel` must still work
  for unit tests. Tool-using agents work with TestModel — the librarian already does this.
- **Existing validation (Stage 1) stays**: The `propose_type` tool calls normalization
  functions from Stage 1. This is defense-in-depth, not replacement.

### What to produce

Revise `docs/plans/28-ontology-alignment/stages/03-.md` and `stages/04-.md` to
describe the agentic ontology agent. Stage 3 should cover:
- Tool definitions (what each tool does, its signature, what it returns)
- Revised system prompt (workflow instructions for the agent)
- OntologyAgentDeps changes
- Pipeline integration (how to pass repo, collect results)
- How the `propose_type` tool integrates Stage 1 validation inline

Stage 4 should cover:
- Model/thinking config (may be less critical now that tools provide grounding)
- Cost/latency logging
- Any settings changes

Keep Stages 1, 2, 5, 6 unchanged — they still apply as-is.
Update the index.md progress tracker if stage descriptions change.
